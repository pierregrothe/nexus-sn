# NEXUS -- Active Work

Last updated: 2026-05-08
Session: Status dashboard visual polish shipped (PR #10). Test suite at 219 passing.

## Current focus

nexus status is fully implemented and end-to-end functional. Recent merges:

  PR #6 (merged) -- Tier detection from Claude Code OAuth + org MCP config (ADR-018)
  PR #7 (merged) -- /simplify lessons learned, semgrep + governance (ADR-019)
  PR #8 (merged) -- NEXUS auto-update from GitHub Releases (ADR-020)
  PR #9 (merged) -- Gradient blue-to-cyan banner + themed Console
  PR #10 (merged, commit 3bb4a55) -- Verbose multi-panel status dashboard:
    src/nexus/ui/gradient_panel.py -- GradientPanel renderable + gradient_text()
    src/nexus/ui/theme.py -- SN_TEXT_START constant (40% teal stop for value text)
    src/nexus/ui/banner.py -- banner now uses SN_BLUE/SN_LIME (matches panels)
    src/nexus/capabilities/status_reporter.py -- 3-row dashboard:
      Row 1: Identity | System (equal height, two columns)
      Row 2: Integrations (full width, only detected MCP servers)
      Row 3: Diagnostics | Auto-update (equal height, two columns)
    src/nexus/capabilities/claude_config.py -- fixed anonymous bug; reads
      oauthAccount.emailAddress + organizationName from ~/.claude.json
    tests/test_ui_gradient_panel.py -- 7 new tests

Focus returns to MVP build order:
  Step 2: src/nexus/templates/sync.py -- GitHubSync.fetch_manifest() +
          download_changed(). Test with tmp_path and a fake manifest fixture.
  Step 3: templates/registry.py -- TemplateRegistry.list() + get()
  Step 4: assessment/scanner.py -- InstanceScanner using ServiceNowClient
  Step 5: assessment/rules.py + reporter.py -- RuleEngine + AssessmentReporter
  Step 6: nexus setup command -- credential wizard, config write, initial sync

## What was completed in the recent sessions

Status dashboard (PR #10, merged 2026-05-08):
  GradientPanel renderable -- panel with left-to-right RGB gradient border.
    Supports title, padding, min_height for equal-height column pairs.
    __rich_measure__ enables Table.grid column sizing.
  gradient_text() helper -- per-character gradient coloring for value text.
  SN_TEXT_START constant -- teal (40% blue-to-lime), start color for values.
  Banner visual update -- SN_BLUE->SN_LIME gradient, blank line before banner.
  StatusReporter rewrite -- 3-row dashboard, dynamic MCP server list.
  Anonymous bug fix -- email + org name now populated from ~/.claude.json
    oauthAccount section (not keychain-only).
  All 4 changed modules at 100% coverage; ratchet baselines updated.

Test suite: 219 passing. All real fakes, no mocks.

## Blockers / open questions

- MCPProbe._check_server() still stubbed (returns False). Real enterprise MCP
  endpoint URLs unknown. With Agent SDK as the LLM layer, MCP probing strategy
  will change -- the SDK exposes MCP via ClaudeAgentOptions(mcp_servers=...);
  separate enterprise MCP probing from the LLM connection.
- knowledge/mastery/ empty. Decision pending: copy from JARVIS or build fresh.
- 8 grandfathered dict[str, Any] usages in src/nexus/connectors/servicenow/client.py
  -- the pre-edit hook still blocks new ones; semgrep rule deferred until those
  are refactored to a typed alias.

## Branch / remote state

main: 3bb4a55 (status dashboard merged)
Next: branch from main and start MVP Step 2 (GitHubSync).
