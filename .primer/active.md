# NEXUS -- Active Work

Last updated: 2026-05-08
Session: instance management UX + OAuth auto-provisioning shipped. 296 tests passing.

## Current focus

nexus instance register is now end-to-end functional with zero OAuth knowledge required.
Recent commits on main (all direct, no open PRs):

  e817e27 fix(instance): probe glide.buildtag.last for version on PDI instances
  8aa8dc0 fix(instance): skip unavailable tables in scanner; improve version detection
  5ab3be0 fix(instance): re-detect version on connect; extract _detect_sn_version helper
  84e6fb6 fix(instance): robust version detection + 8h OAuth token lifetime
  8c39b3e feat(instance): auto-provision OAuth credentials from username + password
  7ecdb77 ux(cli): concrete error messages, quickstart guide for instance management
  ecf7f9f ux(cli): accept bare subdomain in register
  831101a feat(cli): instance list + command guide when called without subcommand

Focus returns to MVP build order:
  Step 2: src/nexus/templates/sync.py -- GitHubSync.fetch_manifest() +
          download_changed(). Test with tmp_path and a fake manifest fixture.
  Step 3: templates/registry.py -- TemplateRegistry.list() + get()
  Step 4: assessment/scanner.py -- InstanceScanner using ServiceNowClient
  Step 5: assessment/rules.py + reporter.py -- RuleEngine + AssessmentReporter
  Step 6: nexus setup command -- credential wizard, config write, initial sync

## What was completed in the recent sessions

instance management UX (8 commits, 2026-05-08):

  OAuth auto-provisioning:
    _provision_oauth() -- POSTs to /api/now/table/oauth_entity via Basic auth,
      generates client_secret (UUID4), extracts client_id from response.
      Falls back to _print_oauth_setup() + manual prompts on any failure.
    Register wizard now asks only: Instance URL, Username, Password.
    Auto-provisioned OAuth apps request token_lifetime=28800 (8h).

  Version detection:
    _detect_sn_version() extracted as shared helper (register + connect).
    Probes glide.buildtag, then glide.buildtag.last (PDIs store value there),
      then falls back to nameLIKEbuildtag search.
    instance_connect now re-detects and persists version/build/instance_name.
    Visible warning printed when version cannot be detected.

  Scanner resilience:
    InstanceScanner._fetch() now treats HTTP 400/404 as table-not-available
      and returns [] instead of raising SnapshotError.
    Fixes nexus instance refresh on PDIs without ai_skill (NowAssist) table.

  instance_callback with invoke_without_command=True:
    Shows registered instances table or full quickstart when no subcommand given.
    Command guide always shown at the bottom.

  CLI helpers:
    _resolve_profile(), _oauth_for(), _set_default_profile() extracted.
    TokenExpiredError message now shows delete + re-register steps.

Test suite: 296 passing. All real fakes, no mocks.

## Blockers / open questions

- MCPProbe._check_server() still stubbed (returns False). Enterprise MCP
  endpoint URLs unknown. Probing strategy will revisit once Agent SDK
  MCP wiring is designed.
- PDI access token cap: glide.oauth.access_token.expire_in.system_max_seconds
  overrides token_lifetime on the OAuth app record. Token stays at 30 min
  on PDIs regardless of what we request. Needs SN admin to raise the cap.
- knowledge/mastery/ empty. Decision pending: copy from JARVIS or build fresh.
- 8 grandfathered dict[str, Any] in src/nexus/connectors/servicenow/client.py.

## Branch / remote state

main: e817e27 (instance UX + fixes merged)
Next: branch from main and start MVP Step 2 (GitHubSync).
