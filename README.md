# NEXUS

<p align="center">
  <img src="docs/assets/banner.svg" alt="NEXUS" width="900">
</p>

<!-- badges -->
[![Release](https://img.shields.io/github/v/release/pierregrothe/nexus-sn)](https://github.com/pierregrothe/nexus-sn/releases)
[![CI](https://github.com/pierregrothe/nexus-sn/actions/workflows/ci.yml/badge.svg)](https://github.com/pierregrothe/nexus-sn/actions/workflows/ci.yml)
[![License: Source Available](https://img.shields.io/badge/license-Source%20Available-orange)](LICENSE)
[![Python 3.14+](https://img.shields.io/badge/python-3.14%2B-blue)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-887%20passing-brightgreen)](https://github.com/pierregrothe/nexus-sn/actions)
[![LOC](https://img.shields.io/badge/LOC-15%2C496-blue)](https://github.com/pierregrothe/nexus-sn/tree/main/src)
<!-- /badges -->

ServiceNow AI architect agent -- standalone CLI and optional web dashboard.

Uses the Claude Agent SDK. Runs on Windows, macOS, and Linux.

## Architecture

```mermaid
graph TB
    subgraph CLI ["Interface"]
        cmd["nexus &lt;command&gt;"]
    end
    subgraph Domain ["Domain Layer"]
        cap["capture"]
        plug["plugins"]
        tmpl["templates"]
        assess["assessment"]
    end
    subgraph Platform ["Platform Layer"]
        agent["AgentClient\n(claude-agent-sdk)"]
        sn["ServiceNow\nConnector"]
        caps["CapabilitySet\n(MCP probe)"]
    end
    subgraph Foundation ["Foundation"]
        conf["config"]
        auth["auth (keychain)"]
        cache["cache"]
    end
    cmd --> cap & plug & tmpl & assess
    cap & plug & tmpl & assess --> agent & sn
    agent --> caps
    agent & sn & caps --> conf & auth & cache
    caps -.->|"Anthropic API\nenterprise MCP tools"| ext["Value Melody / SSC\nBT1 / Data Analytics"]
    sn -->|"REST API"| sni["ServiceNow Instance"]
```

## Install

Not yet on PyPI. Install from the latest GitHub release wheel or from source.

**From the latest release wheel (recommended):**

```bash
pip install https://github.com/pierregrothe/nexus-sn/releases/download/2026.05.2/nexus_sn-2026.5.2-py3-none-any.whl
```

**From source:**

```bash
git clone https://github.com/pierregrothe/nexus-sn.git
cd nexus-sn
pip install .
```

**With the optional NiceGUI dashboard:**

```bash
pip install "nexus_sn-2026.5.2-py3-none-any.whl[ui]"   # wheel
# or
pip install ".[ui]"                                       # from source
```

## Quick start

```bash
nexus instance register       # add a ServiceNow instance (auto-provisions OAuth)
nexus status                  # verify connection and capability tier
nexus capture discover        # scan AI automation artifacts in your instance
nexus capture pull <scope>    # download scope configuration to local YAML
nexus plugins scan            # inventory all installed plugins
nexus plugins advisories      # CVE, EOL, and license findings
nexus plugins impact <id>     # reverse-dependency and record-count analysis
```

## Roadmap

<!-- gantt -->
```mermaid
gantt
    title NEXUS Development Roadmap
    dateFormat YYYY-MM
    section Foundation
        Foundation                   :done, 2026-03, 2026-05
    section Plugin Execution
        Plugin Execution             :done, 2026-05, 2026-06
    section Setup + Sync
        Setup + Sync                 :active, 2026-05, 2026-06
    section Assessment
        Assessment                   : 2026-06, 2026-07
    section Template Library
        Template Library             : 2026-06, 2026-07
    section Agent Specialists
        Agent Specialists            : 2026-07, 2026-08
    section Distribution
        Distribution                 : 2026-08, 2026-09
```
<!-- /gantt -->

## What is implemented

<!-- tests -->887 tests passing, all real fakes, no mocks.<!-- /tests -->

The following commands are fully functional:

- `nexus status` -- tier detection, MCP capability probe, auto-update check
- `nexus instance` -- register, connect, refresh, list, delete, use
- `nexus capture` -- discover, pull, list, push (bidirectional SN config transport)
- `nexus plugins` -- scan, list, info, impact, advisories, orphans, diff,
  updates, drift, baselines, recommend, export, promote, install, activate,
  upgrade, apply (full lifecycle including PromotionPlan execution against
  ServiceNow's discovered sn_appclient endpoints)
- `nexus reauth` -- OAuth token refresh helper
- `nexus update` -- manual update check

The following commands are stubs (not yet implemented):

- `nexus setup` -- credential wizard (2026.05)
- `nexus sync` -- pull latest templates from GitHub (2026.05)
- `nexus templates` -- browse and apply templates (2026.05)
- `nexus assess` -- instance health scan (2026.06)
- `nexus apply` -- deploy a template (2026.06)
- `nexus run` -- free-form AI orchestration (2026.07)
- `nexus rollback` -- undo a previous deployment (2026.07)

## Plugin management

The `nexus plugins` subapp covers the full lifecycle of ServiceNow application plugins -- inventory and analysis on the read side, install / upgrade / apply on the write side:

```mermaid
flowchart LR
    scan["nexus plugins scan\n(v_plugin + sys_store_app)"]
    --> inv["PluginInventory\n(frozen snapshot)"]
    inv --> adv["advisories\n(CVE / EOL / license)"]
    inv --> imp["impact\n(reverse deps +\ncross-scope refs)"]
    inv --> upd["updates\n(store catalog diff)"]
    inv --> drift["drift\n(vs named baseline)"]
    inv --> diff["diff\n(cross-instance)"]
    adv --> defer["defer finding\n(per-instance override)"]
    imp --> rec["recommend\n(AI deactivation plan)"]
    inv --> export["export\n(YAML / CSV)"]
    diff --> promote["promote\n(generate PromotionPlan YAML)"]
    promote --> apply["apply\n(execute against target instance)"]
    inv --> exec["install / activate /\nupgrade"]
    exec --> poll["ProgressPoller\n(sn_appclient/progress)"]
    apply --> poll
    poll --> result["OperationResult\n(rollback on partial failure)"]
```

Read-side commands (analysis):

```bash
nexus plugins scan                        # full inventory (v_plugin + sys_store_app)
nexus plugins list --source store         # filter by source
nexus plugins advisories --strict         # exit 1 if findings found
nexus plugins impact <plugin-id>          # impact analysis with cross-scope refs
nexus plugins drift --baseline prod       # compare against a named baseline
nexus plugins diff <instance-a> <instance-b>  # cross-instance comparison
nexus plugins recommend deactivate <id>   # AI-generated deactivation plan
nexus plugins export --format csv         # export inventory to CSV
```

Write-side commands (execution):

```bash
nexus plugins install <plugin-id>         # install with dependency-cascade preview
nexus plugins upgrade <plugin-id> --to X.Y.Z   # upgrade to a specific version
nexus plugins activate <plugin-id>        # activate an installed plugin
nexus plugins promote dev --to prod --out plan.yaml  # generate PromotionPlan
nexus plugins apply plan.yaml             # execute the plan; rolls back on partial failure
```

Note: `nexus plugins deactivate` and `nexus plugins uninstall` exist as
forward-compatible stubs but fail loudly on live ServiceNow. ServiceNow does
not expose deactivation or uninstall via any programmatic API on Yokohama --
the `AppsAjaxProcessor` is flagged "not public" and only the SN UI can
invoke it. Use the ServiceNow Application Manager UI for those operations.

## Requirements

- Python 3.14+
- ServiceNow instance with REST API access
- Claude Code installed and authenticated (OAuth credentials are read automatically),
  or `ANTHROPIC_API_KEY` env var set as a fallback for CI / scripted use

## Contributing templates

See `docs/CONTRIBUTING.md`.

## Version

CalVer: 2026.05.2

## License

NEXUS Source License v1.0 (Apache 2.0 + Commons Clause).
Free for personal, internal, demo, POC, and production use on your own instances.
Commercial use -- consulting, partner billing, managed services -- is prohibited.
See [LICENSE](LICENSE) and [NOTICE](NOTICE) for full terms.
