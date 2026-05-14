# Decision Log

Append-only record of architectural and design decisions.

## Template

```
### YYYY-MM-DD -- [Title]

**Status:** proposed | accepted | superseded by [link]

**Context:** Why this decision was needed.

**Decision:** What was decided.

**Consequences:** What follows from this decision.
```

### 2026-05-07 -- API-direct architecture (original intent)

**Status:** superseded by ADR-015 (2026-05-08)

**Context:** JARVIS required Claude Code + MCP protocol + Node.js, limiting deployment
to developers who had Claude Desktop or Claude Code installed.

**Decision (original):** NEXUS calls the Anthropic API directly using the Python SDK.
No MCP server hosted by NEXUS. Ships as a pip package.

**Why superseded:** The standard Anthropic SDK with OAuth tokens was 429-gated at
/v1/messages. The claude-agent-sdk was adopted instead (ADR-015), which spawns the
Claude Code CLI as a subprocess. Claude Code CLI >= 2.0.0 is now a hard runtime
dependency. NEXUS itself does not host or require an MCP server, which remains true.

**Consequences (corrected):** NEXUS requires Python + Claude Code CLI installed and
authenticated. Enterprise MCP servers are accessed through the Claude Enterprise
account configuration, not via a local MCP host process.

---

### 2026-05-07 -- Template distribution via GitHub sync

**Status:** accepted

**Context:** Four distribution models were evaluated: (A) bundled at install, (B)
versioned PyPI data package, (C) separate templates-only repo, (D) same repo + sync
command. JARVIS used bundled knowledge that went stale between installs.

**Decision:** Option D -- templates live in the same GitHub repo under templates/.
The `nexus sync` command fetches the manifest and downloads changed files to
~/.nexus/templates/. No version pinning required; latest is always authoritative.

**Consequences:** nexus sync is a required first step after install. Offline use
requires a prior sync. The GitHubSync layer must handle rate limiting and partial
downloads gracefully.

---

### 2026-05-07 -- Assessment 3-gate model

**Status:** accepted

**Context:** JARVIS had no validation step -- it applied templates and hoped for
the best. Failed deployments left instances in an unknown state.

**Decision:** Assessment runs in three phases: Gate 1 (readiness check before deploy),
Gate 2 (validation check after deploy), and standalone `nexus assess` (health scan
at any time). Each gate is a separate RuleEngine evaluation pass.

**Consequences:** Every template deployment requires two assessment passes. The
RuleEngine must be stateless and re-runnable. Rollback logic is scoped to the
execution layer, not the assessment layer.

---

### 2026-05-07 -- CalVer versioning (YYYY.0M.PATCH)

**Status:** accepted

**Context:** NEXUS is a ServiceNow tooling project where "how current is this?"
matters more than API stability signaling. SemVer MAJOR bumps would be meaningless
without a stable external API contract.

**Decision:** CalVer format YYYY.0M.PATCH (e.g., 2026.05.0). Patch resets to 0
each month. Breaking changes are documented in CHANGELOG.md.

**Consequences:** Version number encodes freshness. CI release workflow tags from
pyproject.toml version field. No automated version bumping -- Pierre sets the
version manually before tagging.

---

### 2026-05-07 -- Connector plugin system

**Status:** accepted

**Context:** ServiceNow is the first and primary connector, but future connectors
(JIRA, GitHub, Confluence) were anticipated in the JARVIS analysis.

**Decision:** Connectors are registered via ConnectorProtocol. ConnectorRegistry
discovers them by class name. ServiceNow REST is built-in; enterprise MCP is
optional. Plugins can be added without modifying core code.

**Consequences:** ServiceNowClient is not imported directly outside the connectors
layer. All tool calls go through ConnectorRegistry.get(). Future connectors inherit
ConnectorProtocol and register themselves.

---

### 2026-05-07 -- Sprint retrospective governance upgrade

**Status:** accepted

**Context:** MVP Step 1 sprint revealed 23 issues across 6 categories. Most were
type safety failures, test quality gaps, and broken hook infrastructure. Cataloged
in docs/superpowers/specs/2026-05-07-governance-enforcement-design.md.

**Decision:** 8 new ADRs (006-013) document the governance improvements. Plan 1
fixed the critical issues (broken hooks, Python 3.14, type enforcement). Plan 2
adds the ratchet baseline, lean CI, pre-commit hook, and formal ADR documents.

**Consequences:** The codebase now has 10 blocking pre-edit rules, a coverage ratchet
in .ratchet.json, pyright strict alongside mypy, and lean CI (<30s feedback).
Pre-commit hook enforces full test suite locally before every commit. CI cross-platform
testing only runs on release tags.

---

### 2026-05-07 -- Pluggable AuthProvider with OAuth-first chain

**Status:** superseded by ADR-015 (2026-05-08)

**Context:** Original design assumed users would have Anthropic API keys or could
use Claude Code's stored OAuth token via the standard anthropic SDK (auth_token=).
Both paths were policy-gated at /v1/messages and returned 429 in practice.

**Decision (deleted):** AnthropicClient + AuthProvider abstraction -- entirely removed
in ADR-015. All auth code in auth/claude.py and the AuthProvider chain was deleted.

**Consequences:** Superseded without replacement -- ADR-015 delegates all auth to
claude-agent-sdk, which handles the credential chain internally. Spec at
docs/superpowers/specs/2026-05-07-pluggable-auth-design.md (PR #1, code since removed).

---

### 2026-05-08 -- Migrate from anthropic SDK to claude-agent-sdk

**Status:** accepted (supersedes the AuthProvider OAuth path from 2026-05-07)

**Context:** PR #1 introduced a Pluggable AuthProvider abstraction so users
could authenticate via Claude Code's stored OAuth credentials, bypassing the
API-key-acquisition process. Empirical testing showed the OAuth path is
policy-gated at /v1/messages: the standard anthropic SDK with auth_token=
returns 429 on every call. The Claude Agent SDK -- using the same OAuth
credentials -- succeeds.

**Decision:** Replace the anthropic SDK with claude-agent-sdk. Add an
AgentClient async wrapper. Delete the AuthProvider abstraction (Agent SDK
handles auth internally). Drop the anthropic package dependency.

**Consequences:** Claude Code CLI >= 2.0.0 is a hard runtime dependency --
the SDK raises CLINotFoundError if the CLI is absent. NEXUS cannot function
without it. Auth chain inside the SDK: ANTHROPIC_API_KEY env >
CLAUDE_CODE_OAUTH_TOKEN env > ~/.claude/.credentials.json > macOS Keychain.
Subprocess overhead per call (~500ms-30s including SessionStart hooks).
PR-#1's AuthProvider work deleted (~250 lines removed, ~150 lines added).
ADR-001 partially superseded; AuthProvider entry superseded by ADR-015.
Spec at docs/superpowers/specs/2026-05-08-agent-sdk-migration-design.md.


---

### 2026-05-08 -- Single canonical caching decorator (@cached)

**Status:** accepted (ADR-017)

**Context:** Four families of operations in NEXUS benefit from caching
(Agent SDK calls, ServiceNow API responses, capability probes, config
lookups). Without a canonical decorator, each would invent its own layer
with different semantics.

**Decision:** Layer-0 utility `src/nexus/cache/` exports `@cached(ttl,
persist, namespace, key_fn)` and `clear_cache(target)`. Three Semgrep rules
plus runtime TypeError/ValueError enforce the contract.

**Consequences:** Adds diskcache as a runtime dep. Instances must be
hashable (slots+frozen dataclasses use an id-keyed strong-dict fallback;
documented in ADR-017). Function exceptions never cached. Initial adoption:
ConfigManager.load and NexusPaths.from_env. Spec at
docs/superpowers/specs/2026-05-08-cached-decorator-design.md; plan at
docs/superpowers/plans/2026-05-08-cached-decorator.md.


---

### 2026-05-08 -- Tier detection from Claude Code OAuth + org MCP config

**Status:** accepted (ADR-018)

**Context:** Capabilities layer was scaffolded but `_check_server` was a
stub. Real detection needed. Investigation found three usable signals:
OAuth subscription claim, claudeAiMcpEverConnected list, and the
mcp-needs-auth-cache file. No email heuristic needed.

**Decision:** Add Tier enum + TierDetector to capabilities. `nexus status`
renders a Rich panel; `nexus reauth` prints the one-shot command. Detection
caches per-instance in-memory (cross-invocation disk caching deferred --
the @cached(persist=True) path captures the disk backend at decoration
time, preventing test isolation). No live MCP probing in this PR;
deferred until the Agent SDK exposes a clean tool-list query.

**Consequences:** Cross-platform via keyring (macOS Keychain / Linux/Windows
file fallback). Static SN MCP name table; new servers without table updates
appear unrecognized but don't break anything. Re-auth is print-only (no
subprocess invocation). `_CLAUDE_AI_NAME_TO_SERVER` renamed to public
`CLAUDE_AI_NAME_TO_SERVER` so tier.py can import it without violating
pyright strict's reportPrivateUsage. Spec at
docs/superpowers/specs/2026-05-08-tier-detection-design.md.


---

### 2026-05-08 -- Lessons from /simplify reviews (ADR-019)

**Status:** accepted

**Context:** Three /simplify sessions (PRs #2, #5, #6) caught real issues
every time, including a CRITICAL keychain-prefix bug in PR #6 that pre-
commit and tests missed. Recurring style smells (enum-shadowing dict,
stub "See" docstrings, hot-path attribute access) appeared across PRs.
The @cached(persist=True) decoration-time backend capture broke test
isolation in PR #6, forcing a fallback to ttl=None.

**Decision:** Bundled PR codifies four threads: ExternalKeychainClient
wrapper for cross-app keychain reads, @cached(persist=True) lazy-resolve
fix, three new Semgrep rules, and a PR template gating /simplify
execution.

**Consequences:** The keychain pattern bug class is closed. @cached
persist mode is test-friendly (AgentClient adoption unblocked). Three
new lint rules trace to ADR-019. PR template is a soft gate; the
unchecked /simplify checkbox is review-visible. Spec at
docs/superpowers/specs/2026-05-08-simplify-lessons-design.md.


---

### 2026-05-08 -- NEXUS auto-update from GitHub Releases (ADR-020)

**Status:** accepted

**Context:** Last of the user's original three-feature ask. Earlier deferral
was correct -- no PyPI release existed to update against. This PR closes the
gap by switching the release pipeline to GitHub-Releases-only (no PyPI yet)
and implementing the auto-update logic.

**Decision:** Layer 7 `src/nexus/updater/` package with check_and_maybe_update
orchestrator invoked by the CLI callback. Every-launch GitHub API call,
wheel download + pip install + os.execv re-run on update. Editable installs
detected via importlib.metadata.distribution().origin.dir_info.editable;
skipped silently. NEXUS_AUTO_UPDATE=0 escape hatch.

**Consequences:** ~200-500ms per launch (3s timeout). pip install + re-exec
on update (~5-10s one-time). Rollback via env var + manual pip downgrade.
Wheel hash verification skipped for v1 (HTTPS sufficient). PyPI publication
deferred. Spec at docs/superpowers/specs/2026-05-08-auto-update-design.md.

---

### 2026-05-08 -- OAuth auto-provisioning via caller-supplied client_secret

**Status:** accepted

**Context:** nexus instance register originally required users to supply an
OAuth Client ID and Client Secret from the SN Application Registry -- a
multi-step manual task invisible to most ServiceNow admins. Users only know
their instance URL, username, and password.

**Decision:** _provision_oauth() POSTs to /api/now/table/oauth_entity using
HTTP Basic auth (username + password). NEXUS generates client_secret as a
UUID4 and includes it in the POST body. SN encrypts it on save; the caller
retains the plaintext. If the POST returns 201 with a client_id, registration
proceeds with no OAuth prompts. On any failure (403 no admin role, 400 policy,
network error), _print_oauth_setup() shows a 3-step manual guide and prompts
for both values.

**Consequences:** Register wizard reduced to three prompts (URL, username,
password) for all instances where the admin user can create OAuth apps.
The SN oauth_entity table requires the user to have admin or oauth_admin role.
PDI token lifetime remains at 30 min regardless of token_lifetime field due
to system-wide cap (glide.oauth.access_token.expire_in.system_max_seconds).

---

### 2026-05-09 -- ServiceNowClientProtocol for DI in capture layer

**Status:** accepted

**Context:** ConfigFetcher, ScopeDiscoverer, and UpdateSetWriter all take a
ServiceNow client parameter. Typed as the concrete ServiceNowClient class,
FakeServiceNowClient (which does not inherit from it) caused mypy/pyright
errors when passed from tests. The unsanctioned workaround of dict[str, Any]
in a protocol file was blocked by the pre-edit hook.

**Decision:** ServiceNowClientProtocol defined in
connectors/servicenow/protocol.py using dict[str, object] return types
(allowed since the hook only blocks dict[str, Any] in public signatures of
Pydantic models). Capture layer components annotate their client parameter
with ServiceNowClientProtocol. CaptureEngine continues to accept the concrete
ServiceNowClient as the DI entry point. FakeServiceNowClient satisfies the
protocol structurally without inheriting from ServiceNowClient.

**Consequences:** All type errors in capture test files resolved. The protocol
is minimal -- only the 4 methods used by the capture layer. Future connectors
that satisfy the protocol can be injected without code changes.

---

### 2026-05-13 -- README sync via injectable-runner script (scripts/)

**Status:** accepted

**Context:** README.md version, Python requirement, and test count were
hand-maintained and frequently stale between milestones. The primer skill
had no mechanism to update the README as part of /primer sync.

**Decision:** `scripts/sync_readme.py` -- a stdlib-only standalone script
with an injectable pytest runner (`Callable[[Path], str] | None`) so tests
never spawn subprocesses. Two anchor strategies: line-match for version and
Python req, HTML comment anchors (`<!-- tests -->`) for test count. Stub
mismatch detection always runs (not gated on changes). Exit code 1 on
missing README; 0 including warnings. Primer skill SKILL.md extended with
Step 8 that runs the script if present (no-op on other projects).

**Consequences:** /primer sync auto-updates three README fields. The zero-
count guard prevents silently writing "0 tests" on pytest failure. The cli_found
bool from _find_cli_stubs prevents false-positive warnings when cli.py is absent.

---

### 2026-05-13 -- Plugin execution full lifecycle in 2026.05.x (sub-projects M + N)

**Status:** accepted

**Context:** Plugin management layer (A-L+E) was assess+plan only -- no command
could write to a SN instance. PromotionPlan YAML existed but could not be
executed. Plugin installs, activates, and upgrades required manual SN work.

**Decision:** Two sub-projects in 2026.05.x. M: additive ops (install/activate/
upgrade/apply-plan) with ProgressPoller, sn_appclient probe + fallback, and
best-effort rollback on partial apply failure. N: destructive ops (deactivate/
uninstall) with mandatory impact gate (compute_impact blocks on non-zero deps;
--force requires typing the plugin ID as second confirmation). Base plugin
uninstall refused via REST (PluginUnsupportedError).

**Consequences:** Full plugin lifecycle managed by NEXUS. assess -> plan ->
execute -> rescan flow complete. Deactivation safety relies on the existing
reverse-dependency graph from sub-project D2.

---

### 2026-05-13 -- Gantt diagram synced from roadmap.md via sync_readme.py

**Status:** accepted

**Context:** README.md Gantt was hand-maintained and drifted from roadmap.md
on every roadmap change. Running /primer sync did not update the diagram.

**Decision:** scripts/sync_readme.py now parses .primer/roadmap.md sections,
infers date ranges from YYYY.MM prefixes, and regenerates the Mermaid Gantt
between <!-- gantt --> HTML comment anchors. Runs automatically as Step 8 of
/primer sync. No-op if anchors absent or roadmap.md missing.

**Consequences:** Roadmap changes are reflected in README within one sync run.
Foundation section uses hardcoded 2026-03/2026-05 dates. Backlog section
skipped. Item text abbreviated at first ' -- ' separator, capped at 44 chars.

---

### 2026-05-13 -- README badge row synced from live project data

**Status:** accepted

**Context:** README had no visual project health indicators. Version, Python
requirement, and test count were text-only. LOC was not tracked anywhere.
Badges are standard in open-source Python projects (see google/adk-python).

**Decision:** Six shields.io badges added below the # NEXUS title, wrapped in
<!-- badges --> HTML comment anchors. Three are static GitHub badges that
auto-update (Release version from github/v/release, CI status from Actions,
License). Three are computed by scripts/sync_readme.py on every /primer sync:
Python version (from pyproject.toml), test count (from pytest --collect-only),
LOC (counted from src/nexus/**/*.py with _count_loc()). Special characters in
shield URLs are percent-encoded (+ -> %2B, , -> %2C, space -> %20).

**Consequences:** Badge row stays current without manual maintenance. LOC is
now a tracked metric visible at a glance. /primer sync Step 8 handles all
updates; no new dependencies required (pure stdlib).

---

### 2026-05-14 -- Plugin deactivate/uninstall is platform-blocked by SN

**Status:** accepted

**Context:** Sub-project N added `nexus plugins deactivate` and `nexus plugins
uninstall` CLI commands. Smoke testing against a live PDI revealed the
hypothesised `/api/sn_appclient/appmanager/app/<action>` endpoints return
HTTP 400 -- SN interprets the action name as a sourceAppId path parameter.

Exhaustive investigation followed: mining `sys_ws_operation` (30 ops total
under sn_appclient; install/update/repair/activate/rollback exist; uninstall
and deactivate do NOT), reading `AppManagerHandler` and `PluginsData` script
includes (6 + 22 methods; no uninstall handler anywhere), attempting
session-cookie auth via `/login.do` + `g_ck` CSRF (returns
`<xml error="com.snc.apps.AppsAjaxProcessor is not public"/>`), probing
`/api/now/v1/processor/`, GraphQL introspection (no mutations), and direct
table operations (HTTP 403 ACL). Web research confirmed via SN KB0716414,
official docs, community forums, the official SN SDK, and pysnow/aiosnow
library surveys: ServiceNow has consciously designed plugin uninstall as a
UI-only operation with no programmatic API path.

**Decision:** Keep the CLI commands as forward-compatible stubs. Live SN
operation fails loudly with a clear error message pointing at the spec
addendum. Unit tests pass against FakeServiceNowClient. The executor wiring,
impact gate, --force second-confirm, base-plugin refusal, and rollback path
all remain in place. If SN ever exposes these via REST (a /plugin/uninstall
or /app/uninstall operation appearing in sys_ws_operation), the executor
needs no changes -- only the SN client's `submit_deactivate` / `submit_uninstall`
methods would need their endpoint constants updated.

**Consequences:** NEXUS plugin lifecycle is complete for everything SN
exposes (install, upgrade, activate, apply, diff, promote, drift,
advisories, impact, AI recommendations). Deactivate and uninstall are
documented as out-of-scope due to platform limitations. Users perform
those operations via the SN App Manager UI. Spec addendum
`docs/superpowers/specs/2026-05-13-plugin-execution-design.md` documents
the eight independent confirmation sources.
