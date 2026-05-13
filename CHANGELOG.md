# CHANGELOG

## 2026.05.2 -- 2026-05-13

Plugin management suite, unified CLI UI library, and tooling cleanup.

Features:
- nexus plugins subapp: 13 sub-projects shipped (A-L+E) -- scan, list, info,
  inventory, impact (with cross-scope FK refs), advisories (CVE/EOL/license,
  defer/undo-defer), orphans, diff, updates, drift (named baselines), recommend
  (AI deactivation/explain/roadmap via AgentClient), export (YAML/CSV)
- ui/components library: StatusBadge, KeyValuePanel, DataTable, CommandGuide,
  Hint, Notice, nexus_progress -- wired across all CLI commands
- Themed help panels on bare leaf-command invocation; two-box discovery view
  for sub-app entry (instance, capture, plugins)
- nexus instance: reuse existing nexus-* OAuth app on register
- nexus capture: concurrent scope scan, aggregate API, 50x discover speedup
- scripts/sync_readme.py: auto-updates version, Python req, and test count in
  README on every /primer sync run; warns on stub-list drift vs cli.py
- Release skill: bumps pyproject.toml, __init__.py, README, CHANGELOG before
  tagging; runs tests; computes PEP 440 wheel filename automatically
- Pre-edit hook: blocks emoji/icon chars (U+1F000+, U+2600-U+27BF) while
  explicitly allowing Rich box-drawing (U+2500-U+257F)

Fixes:
- Plugin scanner: pagination via RFC 5988 Link header (was silently truncating
  at 500 rows)
- Plugin scanner: read available_version field; diagnose missing latest_version
- Plugin commands: 7 UAT defects resolved (drift --ack, baselines list, diff
  output, recommend exit codes, export CSV, info error)
- Capture: HTTP 202 handling, concurrent gather cancellation, bearer auth
- Instances: robust version detection, PDI glide.buildtag.last probe

Removals:
- ClaudeAuth and SNAuth dead code deleted (zero production callers; auth
  delegated entirely to claude-agent-sdk)

## 2026.05.1 -- 2026-05-07

Initial scaffolding. Project structure, toolchain, and all module interfaces defined.
MVP scope: setup, status, sync, templates list, assess (health scan).
