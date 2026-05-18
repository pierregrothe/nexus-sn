# Progress

## What Works

Config layer:
  NexusPaths -- XDG-compliant path resolution (~/.nexus/*, ~/.config/nexus/*)
  NexusConfig -- Pydantic model (frozen) for config.yaml
  ConfigManager -- read/write with env var override support

Auth layer:
  KeychainClient + FakeKeychainClient -- OS keychain via keyring
  ExternalKeychainClient -- cross-app keychain reads (e.g., Claude Code credentials)
  AuthError hierarchy
  LLM auth delegated entirely to claude-agent-sdk (no NEXUS-owned credential)

Capabilities layer:
  FeatureFlag, MCPServer enums
  FEATURE_MAP -- maps features to required MCP servers
  ProbeResult, CapabilitySet -- startup capability state
  TierDetector + Tier enum -- detects enterprise/pro/free from Claude Code OAuth
    signals (subscription claim, mcpEverConnected list, needs-auth cache file)
  ClaudeCodeConfig dataclass -- reads ~/.claude.json: email, org name, subscription
    type, detected MCP servers (oauthAccount + claudeAiMcpEverConnected)

Connectors layer:
  ConnectorProtocol -- plugin interface
  ConnectorRegistry -- dynamic connector loading
  ServiceNowClient + FakeServiceNowClient -- REST API
  ServiceNowConnector -- protocol implementation
  Full error hierarchy (SNAuthError, SNNotFoundError, SNRateLimitError, SNClientError)
  RefreshTokenCallback wiring -- proactive refresh within 60s of expiry +
    reactive single retry on 401 (403 left alone since ACL denial cannot
    be fixed by token refresh). Long-running batch upgrades survive PDI's
    30-min access-token cap transparently.

API layer:
  AgentClient -- async wrapper around claude_agent_sdk.query(). Auth handled
    internally by the SDK (env var > Claude Code stored creds > macOS Keychain).
  AgentClientProtocol -- structural interface for agents and CLI commands
  AnthropicError -- typed exception (status_code, message)
  configure_logging -- TimedRotatingFileHandler with 7-day rotation
  FakeAgentClient -- @dataclass(slots=True) test double

Caching layer:
  @cached(ttl, persist, namespace, key_fn) -- canonical caching decorator
  CacheBackend -- in-memory (default) + disk (diskcache, persist=True)
  clear_cache(target) -- invalidation utility

Updater layer:
  UpdateChecker -- GitHub Releases API, 24h TTL check
  WheelDownloader -- downloads wheel from release assets
  Installer + Runner -- pip install + os.execv re-exec on update
  NEXUS_AUTO_UPDATE=0 escape hatch; editable installs skip silently

UI layer:
  NEXUS_THEME + themed Console -- ServiceNow brand colors
  Semantic tokens: label/value/ok/warn/error/border.* styles
  GradientPanel -- Rich renderable with left-to-right RGB gradient border
  gradient_text() -- per-character RGB gradient coloring for value strings
  SN_BLUE, SN_LIME, SN_TEXT_START -- ServiceNow brand gradient stops
  banner_text() / print_banner() -- SN_BLUE->SN_LIME gradient NEXUS ASCII art
  StatusReporter -- 3-row dashboard (Identity | System, Integrations, Diagnostics | Auto-update)
  ui.components/ -- unified CLI component library (wired across all commands):
    StatusBadge -- ok/warn/error styled label-value chip
    KeyValuePanel, two_col -- key-value panel with optional two-column layout
    DataTable (DataColumn) -- typed Rich table with column definitions
    CommandGuide -- themed help panel (badge + description + option rows + examples)
    Hint -- contextual inline tip rendered below panels
    Notice -- info/warn/error/success notice boxes with classmethod constructors
    default_marker, nexus_progress -- marker glyph + progress bar factories

Agents base:
  AgentProtocol, ExecutionContext, AgentResult

Instances layer (fully functional end-to-end):
  InstanceMeta + InstanceSnapshot + ArtifactRecord -- Pydantic frozen models
  InstanceRegistry -- profile directory read/write, snapshot persistence
  token_badge() -- StatusBadge factory for token expiry display
  SNOAuthClient -- OAuth2 Password Grant exchange + keychain token lifecycle
    _Account StrEnum -- typed keychain account keys
    UtcDatetime alias -- shared UTC validator
  InstanceScanner -- parallel REST scan of 4 SN tables (ai_skill, sys_hub_flow,
    sys_script, sys_script_include); 400/404 treated as table-not-available
  Instance CLI commands: register (auto-provision OAuth), connect, refresh,
    status, list, delete, use, diagnose-roles
  diagnose-roles -- probes a fixed set of admin-only tables (sys_store_app,
    sys_plugin, sys_app, sys_scope, etc.) and reports 200/403/404 per table
    so users can self-diagnose ACL denials. Backed by TableProbe /
    TableProbeResult frozen Pydantic models in nexus.instances.role_probe.
  _provision_oauth() -- auto-creates OAuth app via Basic auth, falls back to
    manual instructions if SN returns non-201
  _detect_sn_version() -- probes glide.buildtag, glide.buildtag.last, LIKE
    fallback; re-runs on connect and persists result to meta.json

Capture layer (bidirectional SN config transport):
  CaptureProtocol -- structural interface (CLI/TUI/Web UI bind to this)
  ScopeDiscoverer -- paginated sys_scope fetch + count_records per table
  ConfigFetcher -- paginated Table API, related child records, custom-only filter
  ArchiveWriter/Reader -- YAML on disk with nested related record layout
  UpdateSetXmlBuilder -- ElementTree-based SN update set XML generation
  UpdateSetWriter -- create/reuse sys_update_set + inject via sys_update_xml
  CaptureEngine -- orchestrates all components, DI via ServiceNowClientProtocol
  AI_AUTOMATION table group: ai_skill, sys_hub_flow (+input/logic),
    sys_hub_action_type_definition, virtual_agent_conversation_topic (+block),
    sys_ai_agent (+capability)
  config/types.py -- UtcDatetime shared across instances and capture layers

Plugins layer (plugin management roadmap A-N, 15 sub-projects):
  PluginScanner -- paginated REST scan of sys_plugin + sys_store_app with
    RFC 5988 Link-header pagination
  PluginInventory + PluginInfo -- frozen models with record_counts breakdown
    per scope and total_records helper
  compute_impact -- transitive reverse-dependency walk + per-table record
    counts + cross-scope FK references (cross_scope=True default)
  compute_advisories -- CVE / EOL / license findings with severity sort
  apply_overrides + AdvisoryOverride -- per-instance deferred findings
  batch_upgrade -- BatchUpgradeReport (frozen + model_validator
    coherence check per ADR-021) + skip-on-fail loop; filter_by_family
    + available_families + unknown_families helpers; surfaced via
    `nexus plugins upgrade [--family X] [--all] --yes --out report.yaml`.
    Bare `upgrade` upgrades every pending plugin (brew/apt style).
    SN's "Application version is currently installed" HTTP 400 is
    treated as an idempotent no-op success at both submit and
    progress-poll phases.
  orphan_candidates -- zero-deps + zero-records detection
  diff_inventories -- cross-instance plugin diff
  detect_updates -- comparison against store catalog
  detect_drift + named-baseline registry -- multi-baseline drift detection
  build_deactivation_context / build_explain_context / build_roadmap_context --
    AI prompt builders fed into AgentClient (claude-haiku-4-5)
  PluginExecutor (sub-project M+N) -- install / activate / upgrade / apply_plan
    against the discovered sn_appclient/appmanager endpoints; mandatory
    impact gate combining local reverse_dependencies BFS + live SN
    appmanager/dependencies cascade; --force second-confirm; base-plugin
    refusal; cached snapshot for repeated gate checks; targeted v_plugin
    refresh after install so install->activate combos in one plan resolve
    sys_ids; rollback in reverse on partial apply_plan failure
  ProgressPoller -- async polling of /api/sn_appclient/appmanager/progress/{id}
    with dual-shape normalisation (kickoff response status/trackerId vs
    progress-poll response state/sys_id)
  fetch_dependencies + DependencyEntry -- typed pre-flight cascade preview
  OperationResult + OperationLog -- frozen result models
  PluginExecutionError hierarchy -- PluginProgressError, PluginTimeoutError,
    PluginNotFoundError, PluginBatchError, PluginImpactBlockError,
    PluginUnsupportedError
  nexus.plugins.error_classification -- pattern matchers that convert SN
    response bodies into typed outcomes: is_already_installed_error
    (HTTP 400 idempotent no-op), is_offering_plugin_error (offering plugin
    refusal), OFFERING_PLUGIN_FAILURE_MESSAGE (user-facing message
    documenting why the offering install path is unreachable via
    OAuth/REST -- AppUpgrader.installAndUpdateApps hardcodes
    jumboAppArgs=undefined; the real path is AppUpgradeAjaxProcessor
    reachable only via /xmlhttp.do with session cookies).

CLI:
  nexus status -- fully implemented (banner + tier detection + StatusReporter)
  nexus instance -- full subapp; bare invocation shows two-box discovery view
    (list + CommandGuide); all subcommands have themed help on bare invocation
  nexus capture -- discover, pull, list, push; bare invocation shows discovery view
  nexus plugins -- scan, list, info, inventory, impact (incl. --no-cross-scope,
    --live, --format json), advisories (incl. defer/undo-defer/list-deferred,
    --strict), orphans, diff, outdated (--queue file output, --family filter,
    --format json, --refresh; auto-refreshes inventory > 15 min stale and
    footers a humanised captured-at via humanize_age in nexus.cli.utils),
    drift (--ack, --strict, --baseline, --format json), baselines list/delete,
    recommend deactivate/explain/roadmap, export (yaml/csv), promote, install,
    activate, upgrade (single <id>, --family X, or --all for batch), apply
    (PromotionPlan YAML; defaults target to plan.target_profile), deactivate /
    uninstall (forward-compatible stubs -- SN does not expose these via any
    programmatic API; see spec addendum 2026-05-14e); bare invocation shows
    two-box discovery view. Offering plugins (sn_hs_*, sn_fs_*) fail cleanly
    with the install-via-SN-UI message rather than the raw glide stack trace.
  nexus reauth -- prints one-shot command for servers needing re-auth
  nexus update / --refresh -- manual update check + cache clear
  Every leaf command shows themed help panel (badge + options + examples) on bare
    invocation (no arguments), replacing generic Typer default help
  setup, sync, templates, assess -- stubs (raise NotImplementedError)

Governance enforcement:
  Pre-edit hook (.claude/hooks/pre-edit-validate.py) -- 10 blocking rules
  Coverage ratchet (.ratchet.json) -- per-module covered_lines can only increase
  Semgrep rules (.semgrep/rules.yml) -- semantic rules with ADR tracing
  Post-edit checks: black + ruff + mypy + pyright (all strict, all blocking)
  Pre-commit hook: black + ruff + mypy + pyright + semgrep + pytest
  ADR catalog: 23 ADRs in .primer/adr/. Latest: ADR-023 (file-size
    cap: 800 src / 1000 tests with ratchet enforcement). cli.py
    (4478 lines) was split into a 17-module cli/ package as the
    first beneficiary; ratchet baseline is now empty.

Infrastructure:
  pyproject.toml -- Python 3.14, Poetry in-project venv, ruff/black/mypy/pyright
  pyrightconfig.json -- strict, py314
  .ratchet.json -- coverage baseline for all implemented modules
  .github/workflows/ci.yml + release.yml -- lean CI + GitHub Releases auto-update
  scripts/sync_readme.py -- auto-updates version, Python req, test count in
    README.md on every /primer sync; warns on stub-list drift vs cli.py
  scripts/dump_sn_api_catalog.py -- mines sys_ws_operation for the full SN
    scripted-REST catalog (120 services / 218 ops); used to discover the
    sn_appclient action endpoints
  scripts/smoke_plugins.py -- live smoke suite for nexus plugins
    (discovery, help, list/info/export filters, install/activate/upgrade/
    apply/deactivate/uninstall happy + cancellation + missing-arg + unknown-
    plugin + force-confirm-rejection paths; cross-instance diff +
    promote->apply round-trip). `plugins outdated` has 16 dedicated
    smokes covering every documented option combination; the
    destructive `upgrade --yes [--family BOGUS]` paths have 2
    smokes that exercise prompt-decline and family-validation exits.
    Destructive batch upgrade was validated against retail PDI in 5
    progressive levels plus live SPM family run (6 fresh + 3 already-
    installed treated as success, 1 timeout).

Tests: 1105 passing. All real fakes, no mocks. mypy strict + pyright
strict report 0 errors across src/. One pre-existing UP043 ruff error
in src/stubs/pypager/source.pyi:8 (unrelated to feature work).
GitHub: https://github.com/pierregrothe/nexus-sn (public).

## Known Issues

- MCPProbe._check_server() returns False (stub). Enterprise MCP endpoint URLs
  unknown. Probing strategy will revisit when Agent SDK MCP wiring is designed.
- PDI token lifetime cap: glide.oauth.access_token.expire_in.system_max_seconds
  overrides token_lifetime on OAuth app records; tokens stay at 30 min on PDIs.
  Mitigated for plugin batch operations via ServiceNowClient's
  RefreshTokenCallback (transparent proactive + reactive refresh).
- _rescan_plugin_inventory uses the original `token` variable captured at the
  top of `_upgrade_batch`; if the live client refreshed mid-batch the rescan
  uses a stale token. Not user-visible today because the OAuth refresh is
  also re-invoked by `_acquire_token` on the next CLI invocation, but worth
  cleaning up.
- knowledge/mastery/ empty. Decision pending: copy from JARVIS or rebuild.
- Template schemas (templates/schemas/*.py) are stubs.
- setup, sync, templates, assess commands raise NotImplementedError.
- Stub modules at 0% coverage (agents/specialists/*, connectors/servicenow/*,
  templates, assessment, execution, knowledge).
- nexus plugins deactivate / uninstall fail loudly against live SN -- platform
  does not expose these via Bearer REST, session AJAX, or any other
  programmatic API. CLI commands present as forward-compatible stubs; will
  start working without code changes if SN ever exposes them. See spec
  addendum docs/superpowers/specs/2026-05-13-plugin-execution-design.md
  (Update 2026-05-14e) for the full 8-source confirmation.
- nexus plugins install / upgrade for offering plugins (sn_hs_* Healthcare
  Solutions family, sn_fs_* Financial Services family) is SN-platform-blocked
  at the OAuth/REST boundary. AppUpgrader.installAndUpdateApps (the function
  the REST endpoint dispatches to) hardcodes jumboAppArgs=undefined on
  line 1042; the real path is AppUpgradeAjaxProcessor.install in sn_appclient
  scope reachable only via /xmlhttp.do with session-cookie auth, which OAuth
  Bearer cannot obtain (401 invalid token). Zero sys_ws_operation entries
  wrap the AJAX processor with a REST bridge. NEXUS detects the SN refusal
  and surfaces the install-via-SN-UI message rather than the raw glide stack
  trace. Architectural finding documented on OFFERING_PLUGIN_FAILURE_MESSAGE
  in nexus.plugins.error_classification.
- One pre-existing UP043 ruff error in src/stubs/pypager/source.pyi:8
  ("Unnecessary default type arguments") -- third-party stub file, unrelated
  to feature work, fixable with `ruff check --fix`.

