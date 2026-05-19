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
  nexus setup -- idempotent first-run wizard: probes OS keychain,
    scans profile dirs, dispatches to clean-slate / inline-reauth /
    already-configured / corrupted-profile branches. All prompts via
    typed PromptSource Protocol (no `unittest.mock` in tests).
  nexus sync -- pulls a manifest from raw.githubusercontent.com to
    ~/.nexus/templates/manifest.json. Fail-fast on missing/malformed
    github_repo. Wire vs cached models split for round-trip safety.
  nexus templates -- DataTable of cached catalog with synced-age
    footer; Hint pointing at `nexus sync` when no prior sync has run.
  nexus assess -- --for <template> (Gate 1 readiness), --job <id>
    (Gate 2 validation), no-flag (standalone health scan),
    --live / --archive source switch, --skip-gate2 ack-skip.
    Verdict-to-exit PASS=0 / BLOCK=2 / ERROR=1.
  nexus apply -- Gate 1 -> ApplyEngine -> Gate 2 orchestrator.
    Flags: --scope X (target scope override), --force (skip Gate 1
    BLOCK only), --skip-gate2 (omit post-apply Gate 2),
    --dry-run (reserved -- exit 1 not-implemented in v1).
    Verdict-to-exit identical to nexus assess.

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

Tests: 1624 passing. All real fakes (incl. httpx.MockTransport,
FakeBatchProgress, FakeServiceNowClient, no unittest.mock). mypy
strict + pyright strict report 0 errors across src/. ruff + black
clean. GitHub: https://github.com/pierregrothe/nexus-sn (public).

CLI UX batch-progress layer (adaptive plugin upgrade display):
  EmaPriorStore -- append-only JSONL at ~/.nexus/cache/eta_prior.jsonl
    recording {family, duration_s, ts: UtcDatetime}. Per-path
    threading.Lock for in-process multi-thread safety; cross-process
    atomicity declared out of scope for v1 (POSIX O_APPEND semantics
    differ from Windows). load() filters by family, caps at 1000
    most-recent entries, silently skips malformed JSONL lines.
  WeightedETAColumn + ema_compute -- pure EMA helper (alpha=0.4
    default) + Rich ProgressColumn that reads task.fields["sn_pct",
    "ema_duration_s"] and renders "ETA: estimating..." (dim) when
    no prior samples exist, or "ETA: MM:SS" computed as
    remaining_full*ema + (1 - sn_pct/100)*ema.
  BatchProgressProtocol (@runtime_checkable) -- start_batch /
    start_item / update_item / finish_item + console property +
    context-manager surface.
  RichBatchProgress -- wraps rich.progress.Progress with brand
    spinner (RICH only), WeightedETAColumn, transient per-item
    tasks. Records successful-item durations to EmaPriorStore on
    finish_item; failure path skips recording.
  PlainBatchProgress -- one line per event via console.print. No
    Live region, no `\r`, multiplexer-safe.
  make_batch_progress(ctx, total, store) -- factory dispatching on
    ctx.profile (RICH/BASIC -> Rich; LEGACY/PLAIN -> Plain).
  PluginExecutor.upgrade + batch_upgrade accept progress kwarg --
    when provided, executor drives start_item / update_item /
    finish_item directly and routes console output through
    progress.console. progress=None preserves today's behaviour.
  InteractiveRequiredError -- cli/errors.py exception with
    exit_code=2 (typer usage-error convention, avoids POSIX `diff`
    exit-3 shadowing). Raised by `nexus plugins upgrade` when
    --yes is absent on PLAIN profile.
  ADR-024 -- FramedViewer (Textual) supersedes pypager for sticky-
    frame paging. pypager + PagedTable + PagerProtocol +
    PypagerPager removed in Story 00 of the batch-progress epic.

Governance enforcement:
  Pre-edit hook (.claude/hooks/pre-edit-validate.py) -- 10 blocking rules
  Coverage ratchet (.ratchet.json) -- 115 per-module entries; per-module
    covered_lines can only increase, never decrease
  Semgrep rules (.semgrep/rules.yml) -- semantic rules with ADR tracing
  Post-edit checks: black + ruff + mypy + pyright (all strict, all blocking)
  Pre-commit hook: 7 hooks via .pre-commit-config.yaml -- black, ruff,
    mypy, pyright, semgrep, pytest, file-size guard
  ADR catalog: 24 ADRs in .primer/adr/. Latest: ADR-024
    (FramedViewer supersedes pypager). ADR-023 (file-size cap:
    800 src / 1000 tests with ratchet enforcement) drove the cli.py
    split into a 22-module cli/ package.
  PRD catalog: 3 PRDs in .primer/prd/ -- PRD-001 (CLI UX wow
    factor), PRD-002 (NEXUS Assessment), PRD-003 (NEXUS Template
    Library). All three at status=draft.

Assessment layer (2026.06-assessment epic shipped 2026-05-19):
  AssessmentRule + Ruleset Pydantic schemas (frozen+strict+extra=forbid)
    with discriminated-union RuleConstraint variants per operator:
    record_exists, field_equals, field_in, count_gte, count_lte.
    Author-declared required_tables + phase + logic + applies_to.
  ConstraintResult + filter_records + record_field_value helpers in
    nexus.assessment.dsl. Missing record fields treated as failure,
    not raised.
  RuleEngine.evaluate(rules, ctx) -- pure function with capture-
    completeness pre-check (no silent false-PASS), phase filter,
    scope dispatch (TableScope / CrossTableScope), AND_ALL / OR_ANY
    composition. Returns tuple[Finding, ...].
  GateContext(capture, apply_result | None, phase) +
    GateReport(verdict: PASS|BLOCK|ERROR, findings, summary).
    .from_findings() classmethod derives verdict (ERROR on any
    error finding; BLOCK on warning in PRE_APPLY; PASS otherwise).
  GateProtocol + 3 frozen @dataclass implementations:
    Gate1Readiness, Gate2Validation (requires apply_result),
    HealthScan. Each filters rules by phase and delegates to engine.
  AssessmentReporter.render_report(report, ctx) -- reuses existing
    ui/components/ (DataTable, KeyValuePanel, StatusBadge, Notice,
    Hint). Severity-sorted finding rows, template_id conditional
    summary, message truncation, PLAIN-profile line-per-event mode.
  nexus assess CLI -- --for <template> (Gate 1), --job <id>
    (Gate 2), no flags (HealthScan), --live / --archive PATH source
    switch, --skip-gate2 acknowledged-skip. Verdict-to-exit mapping
    PASS=0 / BLOCK=2 / ERROR=1.
  3 example rulesets in templates/assessments/ + per-template
    readiness rulesets (one per shipped template) + CI validator
    via scripts/validate_assessment_rulesets.py.

Template Library layer (2026.06-template-library epic shipped 2026-05-19):
  NowAssistSkill + Workflow Pydantic schemas (frozen+strict+
    extra=forbid). NowAssistSkill maps to ai_skill (one record).
    Workflow maps to sys_hub_flow + N WorkflowInput children
    (sys_hub_flow_input) + M WorkflowLogic children
    (sys_hub_flow_logic).
  `{{ env.X }}` field-validator in
    nexus.templates.schemas._env -- resolves env-var references in
    every string field at parse time. Unset variables raise
    ValueError with the literal var name; Pydantic wraps to
    ValidationError. resolve_env_in_dict_values helper for
    WorkflowLogic.inputs dict-typed fields.
  TemplateDocument = NowAssistSkill | Workflow discriminated union
    (kind field). load_template_document(path) loader with
    TemplateLoadError wrapping OSError / yaml.YAMLError /
    ValidationError + path.
  render_to_records(document, scope_sys_id, captured_at) -- pure
    function producing tuple[ConfigRecord, ...]. NowAssistSkill ->
    1 record. Workflow -> parent + children. Deterministic
    SHA-256 sys_ids from (template_id, version, role[, child_name])
    -- INSERT_OR_UPDATE noop on re-apply.
  ApplyEngine (frozen @dataclass(slots=True)) -- async orchestrator:
    load -> resolve target_scope slug to sys_id (or "global"
    sentinel) -> render -> pre-create sys_update_set with
    NEXUS-apply-<id>-<ts> name + structured JSON description
    (template_id, template_version, nexus_version, git_sha,
    applied_at) -> UpdateSetWriter.push -> append local apply.jsonl
    under paths.jobs_dir/<update_set_sys_id>/ -> return ApplyResult.
  ApplyResult (populates Assessment's placeholder) -- frozen
    Pydantic with update_set_sys_id, update_set_name, template_id,
    template_version, target_scope_sys_id, applied_records,
    instance_id, started_at, completed_at. AppliedAction enum =
    REQUESTED | FAILED (WARNED deferred). AppliedRecord per
    ConfigRecord; UpdateSetError marks the offending record FAILED
    with the SN error text; siblings retain REQUESTED.
  ScopeNotFoundError raised when target_scope slug has no
    matching sys_scope record (per-template scope-readiness ruleset
    catches this in Gate 1).
  nexus apply <template> [--scope X] [--force] [--skip-gate2]
    [--dry-run] CLI orchestrator -- wires Gate 1 -> ApplyEngine ->
    Gate 2 with verdict-to-exit mapping. --force skips BLOCK only
    (ERROR aborts). --skip-gate2 ack-and-skip. --dry-run reserved
    (exit 1 with not-implemented Notice in v1).
  3 example templates under templates/ -- nowassist-incident-
    triage, nowassist-tier1-rephrase (NowAssistSkill);
    simple-approval-flow (Workflow with 2 inputs + 2 logic steps).
    Each ships with per-template manifest.yaml and
    templates/assessments/<id>-readiness.yaml ruleset.
  templates/manifest.json refreshed listing the 3 new templates;
    GitHubSync consumes unchanged.
  scripts/validate_template_documents.py CI validator + workflow
    step in validate-templates.yml.

Setup wizard layer (credential management):
  PromptSource Protocol + TyperPromptSource + ScriptedPromptSource
    (tests/fakes/) -- typed prompt abstraction, no-mocks compliant.
  KeychainClient.check_available() -- distinguishes fail / null /
    locked / no-backend keyring backends; emits platform-specific
    distro hints (Darwin / Windows / Linux) for `nexus setup` to
    show as actionable errors. KeychainUnavailableError carries
    a reason slug + hint for opinionated rendering.
  validate_profile_name -- rejects path traversal, separators,
    leading dot, length >64, whitespace, control bytes, non-ASCII,
    ASCII punctuation. Raises InvalidProfileNameError mirroring
    validate_baseline_name.
  InstanceRegistry.scan_profile_dirs() -- returns ScanResult
    (frozen dataclass) splitting profile dirs into valid +
    CorruptedProfile entries so the wizard can surface malformed
    meta.json paths instead of mistaking corruption for an empty
    registry. list_all() stays unchanged (silent-skip).
  Idempotent provision_oauth -- deterministic `nexus-<profile>`
    entity name + PATCH-rotate on retry. A Ctrl-C between OAuth
    entity creation and local token write no longer accumulates
    duplicate oauth_entity records on the SN instance.
  run_instance_setup helper (cli/wizard.py) -- shared by `instance
    register` + `setup`. Synchronous; loops on profile-name
    validation when called without a CLI-supplied profile.

Templates layer (catalog sync + cache):
  TemplateEntry / TemplateManifest -- wire-shape Pydantic models
    (frozen, strict, extra=forbid). TemplateEntry has
    template_type to avoid the `type` keyword.
  SyncSource + CachedManifest -- on-disk wrapper models. Round-trip
    safe (separate models = no extra=forbid break). cached_at is
    UtcDatetime.
  validate_github_repo + InvalidGitHubRepoError -- rejects URLs
    (https://, http://, git@), normalizes trailing slashes, requires
    canonical <owner>/<name> shape.
  GitHubTemplateClient -- anonymous GET to raw.githubusercontent.com,
    never raises, returns None on every failure path with `info` or
    `warning` log. Optional httpx.Client injection for tests with
    MockTransport. 429 logged distinguishably as rate-limit.
  TemplateRegistry -- atomic tempfile + Path.replace save; load
    returns None on missing / unreadable / malformed-JSON / schema-
    mismatch (corrupted file left in place for inspection).
  GitHubSync orchestrator + SyncReport -- typed frozen dataclass with
    outcome in {"ok", "no-config", "invalid-repo", "fetch-failed"},
    manifest, reason. Command layer renders the report.

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
- Template schemas now_assist_skill + workflow shipped (Story 01-02
  of 2026.06-template-library); remaining stubs (ai_agent,
  catalog_item, recipe, project) deliberately deferred to later
  epics.
- `nexus run`, `nexus rollback` still raise NotImplementedError.
- `nexus apply` and `nexus assess --live` capture-runner and
  ApplyEngine factory in default_*_collaborators() raise
  NotImplementedError until a configured ServiceNowClient +
  CaptureEngine pairing is wired at process boot. Test fakes
  cover the contracts end-to-end.
- Stub modules at 0% coverage (agents/specialists/*, connectors/servicenow/*,
  assessment, execution, knowledge).
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
