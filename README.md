# NEXUS

ServiceNow AI architect agent -- standalone CLI and optional web dashboard.

Uses the Anthropic API directly. No Claude Code or Claude Desktop required.
Runs on Windows, macOS, and Linux.

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

```bash
pip install nexus-sn          # CLI only
pip install nexus-sn[ui]      # CLI + NiceGUI dashboard
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

```mermaid
gantt
    title NEXUS Development Roadmap
    dateFormat YYYY-MM
    section Foundation
        Config / auth / capabilities        :done, 2026-03, 2026-04
        Instance management                 :done, 2026-04, 2026-05
        Capture layer                       :done, 2026-04, 2026-05
        Plugin management (13 sub-projects) :done, 2026-05, 2026-05
        CLI UI component library            :done, 2026-05, 2026-05
    section 2026.05 -- Setup and Sync
        nexus setup (credential wizard)     :active, 2026-05, 2026-06
        GitHubSync + TemplateRegistry       :2026-05, 2026-06
    section 2026.06 -- Assessment
        RuleEngine + nexus assess           :2026-06, 2026-07
        Template schemas + apply engine     :2026-06, 2026-07
    section 2026.07 -- Agent Specialists
        8 domain specialist agents          :2026-07, 2026-08
        Multi-step orchestration            :2026-07, 2026-08
    section 2026.08 -- Distribution
        PyPI publish (nexus-sn)             :2026-08, 2026-09
```

## What is implemented

<!-- tests -->832 tests passing, all real fakes, no mocks.<!-- /tests -->

The following commands are fully functional:

- `nexus status` -- tier detection, MCP capability probe, auto-update check
- `nexus instance` -- register, connect, refresh, list, delete, use
- `nexus capture` -- discover, pull, list, push (bidirectional SN config transport)
- `nexus plugins` -- scan, list, info, inventory, impact, advisories, orphans,
  diff, updates, drift, baselines, recommend, export
- `nexus reauth` -- OAuth token refresh helper
- `nexus update` -- manual update check

The following commands are stubs (not yet implemented):

- `nexus setup` -- credential wizard (2026.05)
- `nexus sync` -- pull latest templates from GitHub (2026.05)
- `nexus templates` -- browse and apply templates (2026.05)
- `nexus assess` -- instance health scan (2026.06)

## Plugin management

The `nexus plugins` subapp covers the full lifecycle of ServiceNow application plugins:

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
```

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

## Requirements

- Python 3.14+
- ServiceNow instance with REST API access
- Claude Enterprise API key (Anthropic)

## Contributing templates

See `docs/CONTRIBUTING.md`.

## Version

CalVer: 2026.05.1

## License

MIT
