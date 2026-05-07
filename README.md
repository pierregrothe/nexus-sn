# NEXUS

ServiceNow AI architect agent -- standalone CLI and optional web dashboard.

Uses the Anthropic API directly. No Claude Code or Claude Desktop required.
Runs on Windows, macOS, and Linux.

## Install

```bash
pip install nexus-sn          # CLI only
pip install nexus-sn[ui]      # CLI + NiceGUI dashboard
```

## Quick start

```bash
nexus setup                   # configure credentials and sync templates
nexus status                  # verify connections
nexus templates list          # browse available templates
nexus assess                  # health scan your SN instance
nexus apply <template>        # deploy a template
nexus run "build ITSM demo"   # free-form AI orchestration
```

## Template sync

Templates live in the public GitHub repo. Pull the latest:

```bash
nexus sync
```

## Requirements

- Python 3.12+
- ServiceNow instance with REST API access
- Claude Enterprise API key (Anthropic)

## Contributing templates

See `docs/CONTRIBUTING.md`.

## Version

CalVer: YYYY.0M.PATCH

## License

MIT
