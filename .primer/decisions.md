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

## Compressed entries (2026-05-07 through 2026-05-09)

Older entries trimmed on 2026-05-19 sync per >150-line cap. Full text
lives in git history at commit `592d525` and earlier.

* 2026-05-07 -- **API-direct architecture (original intent)**: superseded
  by ADR-015. Original plan to call Anthropic API directly was 429-gated;
  claude-agent-sdk subprocess path adopted instead.
* 2026-05-07 -- **Template distribution via GitHub sync**: templates live
  in the same repo under `templates/`; `nexus sync` is a required first
  step after install; offline use requires a prior sync.
* 2026-05-07 -- **Assessment 3-gate model**: Gate 1 readiness + Gate 2
  validation + standalone `nexus assess`; RuleEngine stateless and
  re-runnable; rollback scoped to execution layer.
* 2026-05-07 -- **CalVer versioning (YYYY.0M.PATCH)**: freshness over API
  stability signaling; patch resets monthly; no automated bumping.
* 2026-05-07 -- **Connector plugin system**: ConnectorProtocol +
  ConnectorRegistry; ServiceNow REST built-in; future connectors register
  themselves without core code changes.
* 2026-05-07 -- **Sprint retrospective governance upgrade**: 8 new ADRs
  (006-013) document governance improvements; 10 blocking pre-edit rules
  + coverage ratchet + pyright strict + lean CI introduced.
* 2026-05-07 -- **Pluggable AuthProvider with OAuth-first chain**:
  superseded by ADR-015. OAuth path 429-gated at /v1/messages forced the
  Agent SDK migration; AuthProvider abstraction deleted entirely.
* 2026-05-08 -- **Migrate from anthropic SDK to claude-agent-sdk**:
  Claude Code CLI >= 2.0.0 became a hard runtime dependency; auth chain
  delegated to the SDK; subprocess overhead per call (500ms-30s).
* 2026-05-08 -- **Single canonical caching decorator (@cached, ADR-017)**:
  Layer-0 `src/nexus/cache/` with diskcache backend; Semgrep rules +
  runtime checks enforce the contract; persist mode lazy-resolves backend
  for test isolation.
* 2026-05-08 -- **Tier detection from Claude Code OAuth (ADR-018)**:
  Tier enum + TierDetector reading OAuth subscription claim +
  claudeAiMcpEverConnected list + needs-auth cache; no live MCP probing
  yet.
* 2026-05-08 -- **Lessons from /simplify reviews (ADR-019)**:
  ExternalKeychainClient wrapper for cross-app reads; @cached lazy-resolve
  fix; 3 new Semgrep rules; PR template gates /simplify execution.
* 2026-05-08 -- **NEXUS auto-update from GitHub Releases (ADR-020)**:
  `src/nexus/updater/` checks GitHub Releases every launch (3s timeout);
  pip install + os.execv re-run; NEXUS_AUTO_UPDATE=0 escape hatch.
* 2026-05-08 -- **OAuth auto-provisioning via caller-supplied
  client_secret**: `_provision_oauth()` POSTs to oauth_entity with
  Basic auth + UUID4 secret; falls back to manual 3-step guide on
  failure; PDI token cap remains 30 min.
* 2026-05-09 -- **ServiceNowClientProtocol for DI in capture layer**:
  Protocol typed with `dict[str, object]` returns; FakeServiceNowClient
  satisfies it structurally without inheriting from the concrete class.

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

---

### 2026-05-14 -- Batch plugin upgrade + governance ADRs from the work

**Status:** accepted (ADR-021, ADR-022)

**Context:** Plugin management was assess + write-individually only --
no ergonomic way to upgrade every pending plugin (or every pending
plugin in one or more product families) without scripting a loop. The
work also surfaced three governance gaps: mypy strict's prop-decorator
check fires on @computed_field + @property even with pydantic.mypy
enabled; the project has 15+ deferred-import suppressions in cli.py
that reviewers re-discover on every PR; black was in the pre-commit
config but not the post-edit hook, so the first place we caught
formatting drift was CI.

**Decision:** Three-part landing.

(1) `nexus plugins updates` extended with `--family NAME` (repeatable,
case-insensitive), `--apply`, `--yes`, `--out PATH` flags. New pure
helpers `filter_by_family`, `available_families`, `unknown_families`
in `nexus.plugins.filters`. New `PluginExecutor.batch_upgrade` runs
sequentially (SN serializes progress trackers per instance) with
skip-on-fail semantics -- deliberately different from `apply_plan`,
which aborts and rolls back for cross-instance promotion. New
`BatchUpgradeReport` model with stored counts and `@model_validator
(mode="after")` enforcing coherence; rejects construction where
`target_count != len(results)` or `succeeded + failed != target_count`.

(2) ADR-021 codifies the @model_validator pattern as the canonical
approach for derived fields on frozen Pydantic models. @computed_field
+ @property is correct in vacuum but trips mypy strict's
prop-decorator check that the pydantic.mypy plugin does NOT suppress.
Stored fields + after-validator gives clean `model_dump()`
serialization, mypy passes without `# type: ignore`, callers cannot
build an incoherent report.

(3) ADR-022 codifies `# noqa: PLC0415` inside Typer command bodies in
`cli.py` as an accepted exception to the Tier 1 no-deferred-import
rule. Library modules and test code remain blocked. Stops reviewers
from relitigating the suppression.

(4) `.claude/hooks/post-edit-lint.py` now runs `black --check` ahead
of ruff/mypy/pyright. Black was always required (CLAUDE.md, pre-commit
config), but pre-commit hooks only fire when `pre-commit install` has
been run on the checkout -- subagents and fresh worktrees often
haven't. The post-edit hook fires on every Edit/Write tool call.

**Consequences:** +21 tests (911 total). `nexus plugins updates
--apply` brings the "pending updates" count to 0 in one command,
optionally scoped to one or more families. Future frozen Pydantic
aggregate models follow ADR-021 (no more @computed_field churn).
Reviewers consult ADR-022 instead of relitigating CLI suppressions.
Black violations caught at edit time rather than after CI rejects a
push. Spec + plan at
`docs/superpowers/specs/2026-05-14-plugin-batch-upgrade-design.md` and
`docs/superpowers/plans/2026-05-14-plugin-batch-upgrade.md`.

---

### 2026-05-15 -- Exhaustive smoke coverage for `plugins updates` + tests/ type-check cleanup

**Status:** accepted

**Context:** Three pre-existing health gaps surfaced after PR #48
shipped: (a) mypy on `tests/` reported 12 errors across 5 files and
pyright reported 53 (mostly cascading from one unresolved
`sync_readme` import), but CI scoped mypy to `src/nexus/` only so they
stayed silent; (b) the new `plugins updates --family / --apply / --out`
flags were unit-tested but had limited live smoke coverage -- 6 smokes
total, missing multi-family, case-insensitive, combined flags,
explicit --instance, --format text/unknown, and the destructive apply
paths; (c) `sync_readme.py` compared cli.py Python function names
against README user-facing names, which produced a false-positive
"stub mismatch" warning for `templates_cmd` vs the `templates` CLI
subcommand.

**Decision:** Three coordinated PRs / commits:

(1) PR #50 -- clear all mypy/pyright errors in `tests/`. Specific
fixes: `dict` -> `dict[str, str | SnRefField]` in test_xml_builder;
None-guard on `info.record_counts` before indexing; CaptureEngine now
accepts `ServiceNowClientProtocol` (aligns with the 2026-05-09 ADR
intent that other capture-layer types already followed); `_make_result`
returns the FakeServiceNowClient so tests don't reach into
`engine._usw._client`; removed an unused `# type: ignore[misc]` (an
ADR-007 violation); explicit `dict[str, object]` annotations to defeat
pyright's invariance on dict value types; `cast(str, ...)` to narrow
the `in` operator on `dict[str, object]` values; added "scripts" to
pyright's `extraPaths` so `from sync_readme import ...` resolves.

(2) `sync_readme.py` regex now captures the explicit
`@app.command("name")` argument and prefers it over the def function
name. The cli.py function `templates_cmd()` with decorator
`@app.command("templates")` no longer false-positives.

(3) Smoke coverage on `nexus plugins updates` extended from 6 to 16
tests. New variants: `--format text|unknown`, `--instance` explicit,
`--family ITSM --family ITOM` (multi), `--family platform` (lowercase),
combined `--family + --format json`, `--family + --queue`, `--queue +
--format json`, `--apply` with declined prompt input, and `--apply
--yes --family BOGUS` (exits 2 before any SN call). All 16 run live
against alectri PDI. Destructive `--apply --yes` was validated against
retail PDI in five progressive levels (declined -> empty target -> 1
plugin -> 3 plugins -> 5 plugins + --out YAML), plus a partial Level 6
(GRC family) that captured a real live skip-on-fail (`sn_grc_advanced`
already-installed; loop continued onto the next plugin).

**Consequences:** Type-check noise eliminated; 0 errors from mypy
strict / pyright strict / ruff / black across src/ AND tests/.
`# type: ignore` is now provably absent across the codebase.
sync_readme false positive resolved with a regression test.
Live smoke proves every option permutation of `plugins updates`,
including the destructive paths bounded by retail PDI as the
disposable target.

### 2026-05-16 -- Brew/apt-style plugin CLI redesign + transparent OAuth refresh

**Status:** accepted

**Context:** User feedback: "I want an experience close to brew, chocolatey,
adp [apt] and others". The pre-existing `plugins updates` command did
double duty -- a read-only listing AND, with `--apply`, the destructive
batch upgrade. The destructive verb (`upgrade`) could only handle one
plugin at a time. brew/apt convention is the opposite: `upgrade` is the
destructive verb (bare = everything, with arg = just that), `outdated`
is the pure read-only listing. Further, real PDI batches (47 plugins)
ran past the 30-min OAuth token cap mid-loop, killing the whole batch
with SNAuthError; and SN's HTTP 400 "Application version is currently
installed" response was being reported as a failure even though it
is the canonical idempotent no-op.

**Decision:**
1. Rename `plugins updates` -> `plugins outdated` (read-only). Drop the
   `--apply` / `--yes` / `--out` flags from it.
2. Make `plugins upgrade` accept a positional id, or `--family X`, or
   `--all`; bare form upgrades every pending plugin. `--to` is single-
   plugin only; `--out` is batch-only. Five mutual-exclusion guards
   exit 2 with a clear message when combinations clash.
3. Add `RefreshTokenCallback` to ServiceNowClient. Proactive refresh
   fires when expiry is within 60s; reactive refresh retries once on
   401. 403 is deliberately not retried (ACL denial cannot be fixed
   by a fresh token).
4. Detect SN's "Application version is currently installed" in both
   the submit and progress-poll exception handlers; return success=True
   with an idempotent message rather than failure.

No backward-compat shim per `~/.claude/rules/no-backward-compat.md`.
Scripts that ran `nexus plugins updates --apply --yes [--family X]`
must update to `nexus plugins upgrade --yes [--family X]`.

**Consequences:** Long-running family batches survive PDI's 30-min
token cap transparently and report already-installed plugins as
green successes. The CLI now has one clear destructive verb and
one clear read-only verb that match brew/apt muscle memory. 1072
tests passing (up from 912 after the volume of new test files
landed across the broader session); all five gates green;
file-size ratchet baseline now empty after cli.py was split into
a 17-module cli/ package (ADR-023 grandfather entry removed).

---

### 2026-05-18 -- Offering-plugin install is structurally unreachable via OAuth/REST

**Status:** accepted

**Context:** Real PDI upgrades against alectri for sn_hs_csc and
sn_hs_env (Healthcare Solutions family) returned a glide-exception
500 wrapping `Offering plugin id must be specified for application`.
Multiple iterations attempted to discover the right parameter name
on the existing `/api/sn_appclient/appmanager/app/install` endpoint:
seven snake_case/camelCase variants tested via a `--probe-params`
diagnostic mode, then six `sysparm_*` variants tested per SN's
reserved-namespace convention. All thirteen returned `param NOT
recognised`. A subsequent `--mine-endpoints` mode queried
`sys_ws_operation` for offering-related Scripted REST APIs and
found 29 hits, all of which were TMF Open API product-catalog
endpoints unrelated to plugin install -- zero entries in
`sn_appclient` or `sn_cicd` scope. Direct script_include reads
against alectri then traced the actual control flow.

The conclusive finding: SN's offering install path lives in
`AppUpgradeAjaxProcessor.install` (scope `sn_appclient`), invoked
via `/xmlhttp.do?sysparm_processor=AppUpgradeAjaxProcessor&...`
with parameter `appV2Params` (a JSON string carrying
`{isJumboAppInstall, offering, optional_dependencies}`). The REST
endpoint NEXUS calls dispatches into `AppUpgrader.installAndUpdateApps`
which hardcodes `jumboAppArgs=undefined` on line 1042 -- the offering
id has nowhere to land on that code path regardless of the URL shape.
SN's AJAX endpoints (`/xmlhttp.do`, `/ajax.do`) reject OAuth Bearer
tokens with `401 invalid token` and require session-cookie auth via
`/login.do`. No `sys_ws_operation` row wraps the AJAX processor.

**Decision:** Document offering plugins as unsupported through
NEXUS's OAuth/REST architecture rather than implement session-cookie
auth. Update `OFFERING_PLUGIN_FAILURE_MESSAGE` to
`"Offering plugin (install via SN UI -- AJAX-only path, OAuth/REST
cannot dispatch)"` and capture the full architectural reason on the
constant's docstring so the next contributor does not re-walk the
search. Strip the diagnostic plumbing that proved the conclusion:
the `nexus plugins offerings` command (default mode + --probe-params
+ --mine-endpoints), the `--offering` flag on `nexus plugins upgrade`,
the `offering_id` keyword on `ServiceNowClient.submit_install` /
`submit_upgrade` / the protocol / the fake, the
`submit_install_with_raw_params` diagnostic entry point, and the
`extract_script_reference` / `parse_offering_ids_from_error` helpers
in `error_classification.py`. Keep `is_offering_plugin_error` +
`OFFERING_PLUGIN_FAILURE_MESSAGE` so the executor still surfaces a
clean failure rather than the raw glide stack trace.

**Consequences:** Users running `nexus plugins upgrade sn_hs_csc`
now see a one-line actionable failure pointing at the SN UI rather
than `Cannot find function hasOwnProperty in object
com.glide.cicd.exception.CICDProcessException...`. Offering plugins
are confirmed in the same out-of-OAuth-reach category as plugin
deactivate / uninstall (2026-05-14 decision): forward-compatibility
requires no new code, only an endpoint constant flip if SN ever
publishes a REST wrapper. 1105 tests passing (down 23 from 1128
mid-session as the diagnostic plumbing went away). No spec doc --
the finding is captured here and on the constant docstring; the
empirical receipts (script_include sys_ids, line numbers, scope
names) are in git history at commit 26a0e9e.

### 2026-05-18 -- PromptSource Protocol for testable wizard flows

**Status:** accepted

**Context:** `nexus setup` and `nexus instance register` need
interactive prompts (host, username, password, profile-name retry,
OAuth manual fallback). The project's no-mocks rule prohibits
patching `typer.prompt`; previous tests used a conftest helper
that monkeypatched the module which is mocking under a different
name and would not scale to story 06's six-prompt-deep wizard
flow.

**Decision:** Introduce a runtime-checkable `PromptSource` Protocol
in `src/nexus/cli/prompts.py` with two methods (`ask` and
`confirm`). Ship two impls: `TyperPromptSource` (forwards to
`typer.prompt` / `typer.confirm` with optional `prompt_fn` /
`confirm_fn` callable injection for the rare in-process test) and
`ScriptedPromptSource` (`tests/fakes/scripted_prompt.py`, pops
pre-queued answers from a `deque`; raises `PromptExhaustedError`
on empty so under-specified tests fail loudly rather than hanging
on stdin). All wizard collaborators take the Protocol as a
parameter (`provision_oauth`, `pick_existing_oauth_app`,
`run_instance_setup`, `_setup_main`).

**Consequences:** Zero `unittest.mock` introduced for the setup
epic's nine test files. Tests can drive arbitrary-depth wizard
conversations by listing the answers in order. The five legacy
`pick_existing_oauth_app` tests in `test_cli_instance.py` were
migrated from `monkeypatch.setattr(typer, "prompt", ...)` to
`ScriptedPromptSource`; the conftest `scripted_prompt` helper
stays for any other callers but is no longer used by the new
code. Story 01 of the setup epic; commits 1eca36f + fd0f0df.

### 2026-05-18 -- Wire vs cached manifest model split (sync v1)

**Status:** accepted

**Context:** `nexus sync` fetches a manifest from GitHub and
caches it with a `cached_at` UTC stamp. The initial single-model
design carried `cached_at` on a `TemplateManifest` with
`extra="forbid"` config. The adversarial reviewer caught that
this breaks round-trip in both directions: the wire payload
lacks `cached_at` (Pydantic rejects on extra=forbid via the
inverse path -- write to cache adds it, read from wire fails;
write to cache as cached, read as wire fails).

**Decision:** Split into two models. `TemplateManifest` is the
pure wire shape (`version`, `generated`, `templates`).
`CachedManifest` composes it: `wire: TemplateManifest`, `source:
SyncSource` (records the repo/branch/path used to fetch), and
`cached_at: UtcDatetime`. The registry reads/writes
`CachedManifest`; the GitHub client returns `TemplateManifest`;
the orchestrator stamps `cached_at` at save time.

**Consequences:** Two classes instead of one (~20 LOC extra) in
exchange for genuine round-trip safety. The wire payload stays
forward-compatible with any future Pydantic schema growth without
touching the cache shape; the cached file can evolve independently
of the manifest format SN serves. The pattern generalizes to any
future "fetched + stamped" cache (e.g. plugins inventory if
that ever moves to a wire/cache split). Story 01 of the sync
epic; commit 1021038.

### 2026-05-18 -- Idempotent provision_oauth on deterministic name

**Status:** accepted

**Context:** A Ctrl-C between `provision_oauth` POSTing a new SN
`oauth_entity` record and `SNOAuthClient.exchange` writing tokens
to keychain left an orphan on the SN side -- next run created
another one, accumulating duplicates without bound. SN's Table
API masks `client_secret` (password2 field) so the user could
not recover the secret of the orphan to reuse it.

**Decision:** Make `provision_oauth` idempotent on a deterministic
entity name (`nexus-<profile>`). Before any create, GET
`oauth_entity?sysparm_query=name=<deterministic>`. On exactly one
match, PATCH the record with a freshly-generated `client_secret`
UUID (which becomes the new secret -- SN echoes it masked but we
keep the value we sent). On no match, fall through to the
existing POST-create flow.

**Consequences:** Re-running `nexus setup` after an interrupted
prior run reuses the SN entity, returning the same `client_id`
with a rotated secret. The SN instance never accumulates more
than one `nexus-<profile>` record per profile. The old
`fetch_existing_nexus_oauth_apps` listing flow stays in place
for cross-install reuse (a user pasting their secret from another
machine) but is no longer the primary orphan-recovery path.
Tested via `test_provision_oauth_rotates_secret_when_orphan_found`
and `test_setup_resumes_after_oauth_entity_orphan` (story 05 +
story 07 of the setup epic). Commit fd0f0df.

---

### 2026-05-19 -- FramedViewer (Textual) supersedes pypager for sticky-frame paging (ADR-024)

**Status:** accepted

**Context:** PRD-001 v1 (2026-05-15) explicitly banned Textual in
Out-of-Scope and proposed pypager + PagedTable as the sticky-frame
paging path. The same commit `8528230` (2026-05-16) that introduced
PRD-001 ALSO added `textual = "^8.2.6"` and shipped a full FramedViewer
Textual App that became the canonical paging path for `nexus plugins
list` and `nexus plugins outdated`. PagedTable + pypager +
PagerProtocol + PypagerPager shipped at 100% coverage but never
gained a consumer (dead code). Caught by the 2026-05-18 brainstorm +
adversarial review.

**Decision:** PRD-001 revised to v2 (2026-05-18): Textual ban removed,
FramedViewer declared canonical, pypager surface declared dead and
scheduled for deletion. ADR-024 records the architectural reversal.
Story 00 of the batch-progress epic deletes:
* `pypager` runtime dep
* `src/nexus/ui/components/paged_table.py`
* `src/nexus/ui/components/pager.py`
* `tests/fakes/pager.py`
* `tests/test_paged_table.py`
* Ratchet baselines for the removed modules
* "Pager: pypager" label in `nexus status` Terminal panel (now "framed")

**Consequences:** One runtime dep removed. ~250 LOC dead code gone.
Single canonical paging path eliminates the long-term risk of parallel
implementations diverging. Textual is locked in as a NEXUS runtime
dep -- future TUI features can build on it without a new ADR. PRD-vs-
code divergences must now be caught during the brainstorm flow; the
anti-creep fence only matters if reconciled when code lands. Commit
363c1cb.

---

### 2026-05-19 -- BatchProgressProtocol with adaptive RICH/PLAIN implementations

**Status:** accepted

**Context:** Long plugin upgrades (30s-15min each) on PDI gave the
user no feedback during `nexus plugins upgrade --family X`. Earlier
on_plugin_start/progress/complete callbacks on `PluginExecutor.
batch_upgrade` worked for one Rich Progress shape but did not adapt
to LEGACY / PLAIN profiles. PRD-001 specified a single Protocol with
RICH/BASIC + LEGACY/PLAIN implementations driven by a factory.

**Decision:** `BatchProgressProtocol` (@runtime_checkable) declares
`start_batch / start_item / update_item / finish_item + console`
property + context-manager methods. `RichBatchProgress` wraps
`rich.progress.Progress` with `WeightedETAColumn` + brand spinner
(RICH only) + transient per-item tasks; records successful-item
durations to `EmaPriorStore` for future EMA seeding. `PlainBatchProgress`
prints one line per event (no Live, no `\r`, multiplexer-safe).
`make_batch_progress(ctx, total, store)` dispatches on `ctx.profile`.
`PluginExecutor.upgrade` + `batch_upgrade` accept `progress:
BatchProgressProtocol | None`; when provided, the executor drives
the protocol calls directly and routes console output through
`progress.console` so it interleaves correctly with the Live region.
`progress=None` preserves the existing callback path byte-for-byte.

**Consequences:** Adds 4 new modules under `src/nexus/ui/components/`
(eta_store.py, eta.py, batch_progress.py + the FakeBatchProgress in
tests/fakes/). EmaPriorStore safe under in-process multi-thread
writes via per-path module-level lock; cross-process atomicity
out of scope for v1 (POSIX O_APPEND vs Windows WriteFile divergence
documented in the docstring + PRD Out-of-Scope). InteractiveRequired
Error (cli/errors.py) raises with `exit_code=2` -- matches typer
usage-error convention, avoids POSIX `diff` exit-3 shadowing. Commit
bfd8cb9.

---

### 2026-05-19 -- Drop --cov-fail-under=100 in favour of per-file ratchet

**Status:** accepted

**Context:** `pyproject.toml` carried `--cov-fail-under=100` since the
initial scaffolding commit (2026-05-07). The codebase has stub modules
(agents/specialists/*, knowledge/, assessment/, execution/) that never
get above 0%, and many cli/ modules sit in the 30-80% range. TOTAL
coverage has been at 85-86% throughout, so the global gate has been
broken (always failing) for over a week. The real enforcement is the
per-file ratchet at `.ratchet.json` enforced by `.claude/hooks/post-
edit-lint.py` -- it blocks any module whose covered_lines decreases
from its baseline.

**Decision:** Remove `--cov-fail-under=100` from pyproject.toml
`addopts`. Keep `--cov=nexus`, `--cov-report=term-missing`, and add
`--cov-report=json` (the ratchet hook needs the JSON report). Per-
file ratchet remains the only coverage gate.

**Consequences:** `pytest` now exits 0 on the full suite. Stub modules
no longer block test runs. New code still must hit 100% (ratchet
baselines are set high when modules ship). Existing modules below
100% are grandfathered at their current baseline and may only
increase. Commit 363c1cb.


## 2026-05-19 -- 2026.06 phase closed: Assessment + Template Library shipped end-to-end

Both 2026.06 phases delivered the same session. Assessment (commits
5bb9081..b733de2, 7 stories, +130 tests) introduced the
declarative-YAML RuleEngine with capture-completeness pre-check + flat
AND_ALL/OR_ANY composition + per-table / cross-table scope dispatch.
GateProtocol unifies Gate1Readiness / Gate2Validation / HealthScan
behind one structural interface. `nexus assess` ships with three
modes (--for, --job, no-flag) and a 3-valued verdict (PASS/BLOCK/
ERROR -> exit 0/2/1) distinguishing "we evaluated and found failures"
from "we could not evaluate" -- closes the silent-false-PASS hole
identified in the brainstorm's adversarial round.

Template Library (commits 471cbbf..87a73c4, 7 stories + planning,
+127 tests) ships NowAssistSkill + Workflow schemas with Pydantic-
native `{{ env.X }}` substitution at parse time (no Jinja2). Render
pipeline produces deterministic SHA-256 sys_ids -- INSERT_OR_UPDATE
becomes a noop in target state on re-apply. ApplyEngine bundles
records via UpdateSetWriter into sys_update_set with structured JSON
description metadata (template_id + version + nexus_version + git_sha
+ applied_at). `nexus apply` wires Gate 1 -> ApplyEngine -> Gate 2
with verdict-to-exit mapping; --force skips BLOCK only (ERROR always
aborts), --skip-gate2 ack-and-skip, --dry-run reserved.

ApplyResult populated (replaces Assessment's empty placeholder).
AppliedAction = REQUESTED | FAILED in v1 (WARNED deferred).
ScopeNotFoundError raised when target_scope slug has no matching
sys_scope record. 3 example templates + 3 per-template readiness
rulesets in templates/, with CI validator (validate_template_documents.py).

**Consequences:** Test count 1367 -> 1624. PRD count 1 -> 3 (PRD-002,
PRD-003 added). All five quality gates remain green. Next:
2026.07-agent-specialists OR 2026.08-distribution.

## 2026-05-19 -- sys_update_xml ACL block on live PDIs (production gap)

Live-smoke run of `nexus apply` against alectri (commit 6fc6e33) returned
HTTP 403 "ACL Exception Insert Failed due to security constraints" on the
`sys_update_xml` POST inside UpdateSetWriter. Initial reading flagged it as
an OAuth user permissions issue (`anna.mancini` had 0 role bindings via
sys_user_has_role). Further probing inverted that conclusion.

**Findings**:
* The OAuth token's actual principal -- via `gs.getUserID()` JS evaluator --
  is `admin` / sys_id `6816f79cc0a8016401c5a33be04be441` (System
  Administrator). Not anna.mancini. The OAuth grant maps to a separate
  service account, not the user who owned the OAuth registry record.
* admin gets the same 403 on direct REST POST to `sys_update_xml`. The
  parent `sys_update_set` POST succeeds (HTTP 201). Only the per-record
  XML bundling step is blocked.
* `sys_security_acl` has active rows for `name=sys_update_xml` with
  `operation in {write, create}` and empty `script` -- a pure role-gate
  ACL that blocks direct inserts as platform policy.
* **The existing `nexus capture push` hits the identical 403** against
  the same instance. Same UpdateSetWriter code path, same outcome. The
  "capture push works against retail/alectri" claim in `.primer/progress.md`
  was carried forward without ever being live-validated under OAuth.

**Root cause**: ServiceNow treats `sys_update_xml` as a platform-managed
table. Records are auto-generated when modifications happen inside an
update set context (via `gs.setCurrentUpdateSet()` + standard CRUD on the
target table). Direct REST POSTs to `sys_update_xml` are blocked by ACL
even for admin -- this is a security pattern, not a misconfiguration.

**Impact**: The bundle-via-update-set architecture chosen for PRD-003 v1
(Template Library) and inherited by PRD-002 (Assessment Gate 2's apply_result
consumer) cannot complete writes through OAuth Bearer auth on standard PDIs.
Every layer ApplyEngine owns works correctly: scope resolution,
deterministic sys_ids, sys_update_set creation with provenance metadata,
UpdateSetWriter reuse-existing path, failure-mode classification (HTTP 403
-> AppliedAction.FAILED with error context). The break is at the very last
hop where the bundled write would land.

**Options for v2** (Template Library follow-up epic):
1. Direct-write path: ApplyEngine writes to the target tables (ai_skill,
   sys_hub_flow, etc.) via plain REST CRUD. Lose the in-NEXUS audit-trail
   bundling; rely on whatever update-set context ServiceNow has active
   server-side (typically Default).
2. Update Set Import API: post a full XML update-set archive to
   `/api/now/import/now_update_set_xml`. Requires constructing a full
   sys_remote_update_set + sys_update_xml payload via SN's import format.
3. Scripted REST endpoint: ship a NEXUS-side scripted-REST resource that
   uses `gs.setCurrentUpdateSet()` then writes the target records normally.
   Requires SN admin to import the scripted REST -- adds setup friction
   but unlocks the bundle-via-update-set behavior.
4. Basic auth fallback: switch to session-based auth where the user's
   admin role is fully active. Drops the OAuth Bearer convenience.

**Status**: PRD-003 anti-creep fence is NOT re-opened -- bundle semantics
were the chosen v1 design and the design is internally consistent. The gap
is a separate "live integration" deferred work item. Add to roadmap as
2026.08 or backlog: "ApplyEngine v2 -- direct-write or import-API path
for OAuth Bearer environments". Same fix applies to `nexus capture push`.

Live smoke artefact: `sys_update_set` named
`NEXUS-apply-nowassist-tier1-rephrase-20260519T212449Z`
(sys_id `e23057c43b0503946c7dfa9aa4e45a6d`) remains on alectri as
audit-trail evidence; delete via SN UI when ready.

---

### 2026-06-29 -- Project charter created (charter.md)

**Status:** accepted

**Context:** PRD-002 and PRD-003 carried `charter_link: charter.md` but no
charter file ever existed -- a dangling governance reference. Promoting the
replatform-checklist feature to a milestone surfaced the gap (the primer PRD
flow guards on a charter).

**Decision:** Author `.primer/charter.md` from brief.md / product.md / CLAUDE.md
and the fences already implied by the ADRs/PRDs. Seven Hard Product Limits
(NEVER) confirmed by the user: no Claude Code/Desktop/Node.js dependency; never
hosts an MCP server; no secrets in config files; no instance mutation without a
human approval checkpoint (assessment/diff/analysis layers are advisory); no
self-modification without a validation gate; no install-time static knowledge;
no hardcoded product/license/scope specifics.

**Consequences:** Every future PRD anchors to a real charter section. The
dangling `charter_link` references in PRD-002/003 now resolve. Charter is
user-owned; sync never overwrites it.

---

### 2026-06-29 -- Replatform checklist promoted to 2026.07 (ADR-025, PRD-004)

**Status:** accepted

**Context:** A customer replatform (acquisition onto a clean instance) needs a
bi-directional use-case/workflow checklist comparing two instances. The shipped
`nexus assess` is a single-instance gate validator and PRD-002 explicitly fences
out cross-instance comparison, so this is a new capability, not a stub fill-in.
Scoped in `.primer/brainstorming/2026-06-29-nexus-assess-migration.md` and
hardened by a 2x adversarial pass (which overturned one false blocker about
CaptureResult.table_group and pinned the ScopeManifest requirement + natural-key
normalization).

**Decision:** New `src/nexus/replatform/` package (separate from the rule-engine),
consuming CaptureResult + ScopeManifest + PluginInventory. Cross-instance identity
uses a normalized `(scope, type, name)` natural key, never sys_id. Surfaced under
`nexus assess` (converted leaf->group, gate behavior preserved) as `inventory` +
`migration` subcommands. Advisory only; deterministic v1; AI enrichment is v2 on
the 2026.07 specialists. Recorded as ADR-025 + PRD-004 + epic
`2026.07-nexus-replatform-checklist` (6 stories). PRD-002's cross-instance fence
is consciously lifted for `assess migration` only (gate semantics unchanged).

**Consequences:** assess now spans single-instance gates AND cross-instance
migration. Fidelity is bounded by current capture coverage (AI_AUTOMATION group);
the reporter flags empty/thin coverage so a clean checklist is never misread.
First story: `01-replatform-models`.
