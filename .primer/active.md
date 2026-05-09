# NEXUS -- Active Work

Last updated: 2026-05-09
Session: nexus.capture layer complete + /simplify in progress. 344 tests passing.

## Current focus

/simplify review found several efficiency and quality issues in the capture layer.
Fixes in progress (uncommitted):

  fetcher.py:
    _row_to_record() extracted -- eliminates 25-line duplication between
    _fetch_table() and _fetch_related().
    New test: test_fetch_records_preserves_ref_field_values -- exercises
    the SnRefField dict branch previously uncovered.

  scope.py:
    Pagination loop added -- fixes silent truncation at 500 scopes.
    asyncio.gather() for count_records -- 5 concurrent calls per scope
    instead of 5 serial calls.

  connectors/servicenow/protocol.py (new):
    ServiceNowClientProtocol -- structural interface used by ConfigFetcher,
    ScopeDiscoverer, UpdateSetWriter so FakeServiceNowClient satisfies the
    type without inheriting from ServiceNowClient.

  Still to apply: AI_AUTOMATION.key constant for "ai_automation" string
  literals in engine.py, protocol.py, cli.py; capture_list YAML warning
  and ArchiveManifest.model_validate improvement.

Next after /simplify:
  Step 2: nexus setup command -- credential wizard, config write, initial sync
  Step 3: GitHubSync.fetch_manifest() + download_changed()
  Step 4: TemplateRegistry.list() + get()

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
