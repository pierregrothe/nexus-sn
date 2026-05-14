# Plugin Execution -- Design Spec

Date: 2026-05-14 (revised from 2026-05-13)
Status: approved
Revision: live endpoint discovery + 7 gap resolutions

## Problem

The plugin management layer (sub-projects A-L+E) covers the full assess+plan
tier: scan, inventory, impact, advisories, drift, diff, promote-plan. The
missing tier is execution -- NEXUS cannot yet write to a ServiceNow instance
to install, activate, upgrade, deactivate, or uninstall plugins.

The 2026-05-13 draft assumed REST endpoints under `/api/sn_appclient/app_management/`
based on the documented surface. Live browser inspection of the Application
Manager UI on a Yokohama PDI showed the real flow uses a two-call pattern
backed by the SN Batch REST API + the `sn_cicd` progress namespace. This
revision aligns the design with the actual endpoints.

## Goals

- Install, activate, and upgrade plugins via the SN REST API (sub-project M).
- Execute a `PromotionPlan` YAML produced by `nexus plugins promote` (sub-project M).
- Deactivate and uninstall plugins with a mandatory impact gate (sub-project N).
- Block with a Rich progress bar during async SN operations (all ops).
- Roll back partial apply-plan failures in reverse order (best-effort).
- Zero new Python dependencies. Uses existing SN client primitives.

## Non-Goals

- Scheduling or cron-style automation of plugin updates.
- Dependency graph resolution (install A's dependencies before A) -- SN's
  `appmanager/dependencies` endpoint surfaces the cascade and we honour it
  for pre-flight reporting only. We do not re-implement the resolver.
- Downgrading a plugin version (not supported by SN REST). SN itself
  exposes a `rollback_version` field which we surface but do not call.

## Live-discovered SN endpoints

All write operations flow through these three endpoints. URLs are paths
only -- the SN client injects host and auth.

```
POST /api/sn_appclient/appmanager/dependencies
  Body:     { sys_id | scope, version }  (exact payload: TBD at impl Task 1)
  Returns:  { result: [ DependencyEntry, ... ] }
  Purpose:  Pre-flight cascade preview. Returns every plugin that will be
            touched by the requested action, with status_value enumerated:
            "will_be_updated" | "will_be_installed" | "will_be_activated" |
            "already_installed" | "not_supported" | etc.

POST /api/now/v1/batch
  Body:     SN Batch REST multipart envelope wrapping the actual operation
            request. Inner request URL: TBD at impl Task 1 (likely
            /api/sn_appclient/appmanager/install or .../upgrade based on
            UI behaviour).
  Returns:  multipart/mixed response. The relevant item contains:
            {
              "result": {
                "status": "0" | "1" | "2" | "3",
                "status_label": "Pending" | "In Progress" | "Success" | "Failed",
                "status_message": str,
                "status_detail": str,
                "error": str,
                "links": { "progress": { "id": "<trackerId>",
                                         "url": "/api/sn_cicd/progress/<trackerId>" } },
                "percent_complete": int,
                "update_set": str | null,
                "rollback_version": str | null,
                "trackerId": str
              }
            }

GET /api/sn_cicd/progress/{trackerId}
  Returns:  Same shape as the batch result. Poll every 3s until
            status_value in {success, failed, cancelled}.
  Purpose:  Drive the Rich progress bar. Final response includes any
            error message.
```

The synchronous "200 with no progress link" path the 2026-05-13 draft
anticipated has not been observed; every captured write returned a
`trackerId`. The executor treats all writes as async until proven
otherwise during implementation.

### DependencyEntry shape

```
{
  "Id":               "Vulnerability Response Common",
  "orig_string":      "sn_vul_cmn:2.16.1",
  "type":             "Application" | "Plugin",
  "minVersion":       "2.16.1",
  "source_app_id":    "f1c37d4e19b515102a18c1c2ee6a60ce",
  "installed":        bool,
  "active":           bool,
  "hide_on_ui":       bool,
  "status":           "Will be Updated",
  "status_value":     "will_be_updated",
  "order":            int,
  "link":             "nav_to.do?uri=...",
  "has_license":      bool,
  "is_allowed_install": bool
}
```

NEXUS treats this as SN's authoritative pre-flight. We cross-validate
against our local `compute_impact()` result and surface mismatches as
warnings (not errors) -- our impact graph is sourced from the captured
inventory; SN's is live.

## Sub-project M: Plugin execution core

### New modules

`src/nexus/plugins/executor.py`
  PluginExecutor -- orchestrates operations against a SN instance
  OperationResult -- frozen model (action, plugin_id, success, message,
                     duration_s, tracker_id, update_set, rollback_version)
  OperationLog -- tuple of OperationResult; returned by apply_plan

`src/nexus/plugins/progress.py`
  ProgressPoller -- polls GET /api/sn_cicd/progress/{trackerId} every 3s;
                    drives a Rich progress bar; returns final result
  DEFAULT_TIMEOUT_S = 600  # 10 minutes

`src/nexus/plugins/dependencies.py`
  fetch_dependencies(client, plugin_id, version) -> tuple[DependencyEntry, ...]
  DependencyEntry -- frozen model matching SN's shape

### PluginExecutor interface

```python
class PluginExecutor:
    async def install(
        self, plugin_id: str, version: str | None = None
    ) -> OperationResult: ...

    async def activate(self, plugin_id: str) -> OperationResult: ...

    async def upgrade(
        self, plugin_id: str, target_version: str | None = None
    ) -> OperationResult: ...

    async def apply_plan(
        self,
        plan: PromotionPlan,
        *,
        console: Console,
    ) -> OperationLog: ...
```

Executor takes a `ServiceNowClientProtocol`, an `InventorySource` callable
(see Inventory refresh policy below), and an `agent_console` for progress.

### Inventory refresh policy (gap 1)

```
Snapshot at executor construction + targeted refresh after install.
```

- On construction: fetch full inventory once. Build `{plugin_id -> PluginInfo}` map.
- On `install` success: issue a single `GET /api/now/table/v_plugin?sysparm_query=name=<plugin_id>&sysparm_limit=1`
  and patch the new row into the in-memory map.
- `activate` and `upgrade` are pure dict reads against the map.

This supports `install com.foo -> activate com.foo` in one plan without
a full rescan after every step.

### apply_plan flow

```
1. Validate all plugin_ids in plan.actions exist in inventory.
   Refuse with PluginNotFoundError on any missing.
   Same-plugin combos (gap 3): only install -> activate of the same
   plugin_id is pre-validated as legal. All other repeat combos pass
   through to SN; its error response propagates as PluginProgressError.
2. Display action table: N installs, M activates, K upgrades.
3. Prompt: "Execute N operations against <profile>? [y/N]"  (skip with --yes)
4. Execute in PromotionPlan.actions order. The order is already
   (install, activate, upgrade) stable-sorted by project_to_promote_plan.
   Track undo_stack: list[(action, result)] of completed operations.
5. For each step:
   a. Call /api/sn_appclient/appmanager/dependencies for the target.
      Show the cascade summary on the progress panel.
   b. Submit the operation via /api/now/v1/batch.
   c. Poll /api/sn_cicd/progress/<trackerId> until terminal status.
   d. On success: targeted inventory refresh (install only). Continue.
6. On failure (PluginProgressError or timeout):
   a. Stop forward progress.
   b. Print failure report: completed / failed / pending counts.
   c. Run rollback in reverse (see Rollback section).
   d. Raise PluginExecutionError with partial log.
7. On full success: return OperationLog.
   Caller (CLI) rescans inventory and prints summary.
```

### Rollback on partial failure

Rollback is best-effort and bypasses the impact gate (gap 2 -- rollback
deactivates restore pre-plan state, so no interactive prompt). For each
completed operation in reverse order:

```
install   -> uninstall   (POST batch with uninstall payload, best-effort)
activate  -> deactivate  (POST batch with deactivate payload; impact gate
                          bypassed via internal _force=True)
upgrade   -> upgrade-to-rollback_version  (use the rollback_version field
                          SN returned in the original upgrade response;
                          no local version tracking required)
```

Rollback results are appended to OperationLog with action="rollback_*".
If a rollback step itself fails, log the failure and continue rolling
back remaining steps -- never abort rollback due to a secondary failure.

### New CLI commands (sub-project M)

```
nexus plugins install <plugin-id> [--version X.Y.Z] [--yes]
nexus plugins activate <plugin-id> [--yes]
nexus plugins upgrade <plugin-id> [--to X.Y.Z] [--yes]
nexus plugins apply <plan.yaml> [--yes]
```

All commands: show instance profile + plugin name + dependency cascade
preview before executing, confirm prompt (skip with --yes), block with
progress bar, show result. `--yes` skips the action confirm only; it
never skips the destructive double-confirm in sub-project N (gap 4).

### Error hierarchy additions

```python
class PluginExecutionError(NexusError): ...      # base for all exec errors
class PluginProgressError(PluginExecutionError): # SN returned error state
    tracker_id: str
    error_message: str
    sn_status: str       # e.g. "3" for Failed
class PluginTimeoutError(PluginExecutionError):  # polling exceeded limit
    tracker_id: str
    elapsed_s: float
class PluginNotFoundError(PluginExecutionError): # plugin_id not in inventory
    plugin_id: str
class PluginBatchError(PluginExecutionError):    # batch envelope failure
    batch_response: str  # raw multipart fragment for debugging
```

## Sub-project N: Destructive operations

### Adds to PluginExecutor

```python
async def deactivate(self, plugin_id: str, *, force: bool = False) -> OperationResult: ...
async def uninstall(self, plugin_id: str, *, force: bool = False) -> OperationResult: ...
```

The internal `_force` keyword used by rollback (gap 2) is not exposed
on the public API; rollback uses a private `_deactivate_internal` path
that skips the gate.

### Safety gate (mandatory)

Before any deactivate or uninstall, `PluginExecutor`:

1. Calls `compute_impact(plugin_id, cross_scope=True)` -- our local cached
   reverse-dependency walk + cross-scope FK count.
2. Calls `fetch_dependencies(plugin_id, version)` -- SN's live cascade.
3. Compares: log a warning if our local impact missed any dependency SN
   flagged, or vice versa.
4. If our impact has non-zero `reverse_dependencies` OR `cross_scope_refs`,
   OR SN's dependency response contains entries with `status_value`
   indicating breakage, raise `PluginImpactBlockError` with the joined
   report.

`--force` bypasses the gate after showing the joined report and requiring
a second explicit confirmation:

```
Impact check found N dependencies. Type the plugin ID to confirm forced
deactivation:
```

This second confirm is never skipped by `--yes` (gap 4).

### Base plugin refusal (gap 5)

Uninstall of `source == "servicenow"` returns `PluginUnsupportedError`
with `reason="base ServiceNow plugins cannot be uninstalled via REST"`.
No `--force` escape -- the API itself rejects the call.

Deactivate of `source == "servicenow"` is **not** specially refused; it
goes through the impact gate, which naturally rejects core plugins
(com.snc.incident has ~500 reverse deps and is blocked there). Power
users can still `--force` for edge cases.

### New CLI commands (sub-project N)

```
nexus plugins deactivate <plugin-id> [--force] [--yes]
nexus plugins uninstall <plugin-id> [--force] [--yes]
```

### Error hierarchy additions

```python
class PluginImpactBlockError(PluginExecutionError):
    impact: PluginImpact                # our local report
    sn_dependencies: tuple[DependencyEntry, ...]  # SN's live cascade
class PluginUnsupportedError(PluginExecutionError):
    reason: str
```

## PromotionPlan (existing)

`PromoteAction.action: Literal["install", "activate", "upgrade"]` and
`PromotionPlan.actions` (stable-sorted in
`(install < activate < upgrade, product_family, plugin_id)` order) are
already defined in `src/nexus/plugins/diff.py`. The executor consumes
them as-is. No new schema work.

## Testing

All tests use `FakeServiceNowClient` with canned responses for the new
endpoints:

- `POST /api/sn_appclient/appmanager/dependencies` -> canned cascade list
- `POST /api/now/v1/batch` -> canned multipart envelope with trackerId
- `GET /api/sn_cicd/progress/{trackerId}` -> sequenced progress states

`FakeProgressPoller` returns a configurable sequence of `(status_value,
percent_complete)` tuples ending in `success`, `failed`, or `timeout`.
No `unittest.mock`. No subprocess mocking.

Key test scenarios:
- install: success path, SN returns failed state, polling timeout
- install -> activate same plugin in one plan: targeted refresh adds new
  sys_id to map; activate succeeds
- upgrade: success path, rollback_version captured and surfaced
- apply_plan: all success, partial failure with rollback bypassing impact
  gate, rollback secondary failure continues
- deactivate: impact gate blocks (local count > 0), --force second-confirm
  required, --yes does not skip second confirm
- uninstall: source=="servicenow" rejected with PluginUnsupportedError
- dependency mismatch: our local impact misses an SN-flagged dep -> warning
  logged, operation continues

## Open items at planning time

These items are clear unknowns. The implementation plan's Task 1 should
capture them via Chrome DevTools on a live PDI before any executor code
is written:

1. Exact inner request URL inside the `/api/now/v1/batch` envelope for
   install / upgrade / activate / deactivate.
2. Exact request payload keys for each operation (likely some combination
   of `sys_id`, `name`, `scope`, `version`, `action`).
3. Exact dependency-check POST body (likely `{sys_id, version}` based on
   UI behaviour).
4. Whether activate and deactivate also use the dependency-check +
   batch pattern, or have a direct path.

These are captured as a single Task 1 in the implementation plan so the
remaining code tasks have authoritative URLs and payload shapes to work
against. Hand-rolled tests are written against `FakeServiceNowClient`
fixtures that match the captured shapes.

## Roadmap placement

Sub-project M and N are both 2026.05.x patches. M ships first (safe ops
only), N ships after M is validated (adds destructive ops + safety gate).

This completes the plugin management tier: assess (A-L+E) -> plan (B promote)
-> execute (M+N). The full lifecycle is then:

  scan -> analyze -> plan -> execute -> rescan -> verify

## Addendum: Live discovery findings (Task 1)

Captured 2026-05-14 on Yokohama PDI demoalectritechzu143890 via in-browser
fetch() interceptor on two app detail pages. Two captures performed:

1. Mitigation Controls Monitoring 4.1.4 -> 4.2.0 -- batch-wrapped path
2. Palo Alto Networks NGFW for Security Operations 10.4.7 -> 10.5.2 -- direct path

The Application Manager uses two different paths depending on whether
dependent applications also need updating. This addendum documents both
because we cannot predict which a given install/upgrade will trigger.

### Endpoint summary (replaces speculative section in main spec)

```
POST /api/sn_appclient/appmanager/dependencies
  Headers:  Content-Type: application/json
  Body:     {"dependencies": "<scope>:<version>"}      # single string field
  Returns:  {"result": [DependencyEntry, ...], "session": {...}}

  Example:
    POST body: {"dependencies": "sn_si:13.9.23"}
    Response:  {"result": [{"orig_string": "sn_si:13.9.23",
                            "Id": "Security Incident Response",
                            "type": "Application",
                            "minVersion": "13.9.23",
                            "source_app_id": "82878663ff123100158bffffffffff67",
                            "installed": true, "active": true, "hide_on_ui": false,
                            "status": "Installed", "status_value": "installed",
                            "order": 2, "link": "nav_to.do?...",
                            "has_license": false, "is_allowed_install": true}],
                "session": {"notifications": []}}

GET  /api/sn_appclient/appmanager/app/install
  Query params (captured from network log; exact key names BLOCKED from display
  by the extension security guard, must be confirmed during Task 4 test fixture
  construction -- the UI source bundle is the canonical reference):
    likely: app_id=<source_app_id>&version=<target_version>
  Returns: install/upgrade kickoff response
    {"result": {"status": "0",                       # numeric string
                "status_label": "Pending",
                "status_message": "", "status_detail": "",
                "error": "",
                "links": {"progress": {"id": "<trackerId>",
                                       "url": "/api/sn_cicd/progress/<trackerId>"}},
                "percent_complete": 0,
                "update_set": null,                  # populated for some upgrades
                "rollback_version": "10.4.7",        # SN tracks rollback target
                "trackerId": "<sys_id>"},
     "session": {"notifications": []}}

  Note: the install/upgrade is a GET with query params, NOT a POST. There is
  no separate /app/upgrade endpoint -- install handles both install (when the
  plugin isn't yet present) and upgrade (when it is, and the version differs).
  This matches Service-Now's "everything is an install" model in the App
  Repository.

GET  /api/sn_appclient/appmanager/progress/{tracker_sys_id}
  Returns: per-poll progress with nested sub-operation tree
    {"result": {"name": "Install from the App Repository",
                "state": "0" | "1" | "2" | "3",
                "message": "Executing queued operation",
                "sys_id": "<trackerId>",
                "percent_complete": "99",            # STRING, not int
                "updated_on": 1778775777000,         # epoch milliseconds
                "results": [<recursive nested sub-operations>]},
     "session": {"notifications": []}}

  Field name divergence from the install response (which used "status" and
  "trackerId"): progress uses "state" and "sys_id". The integration must
  normalise both shapes into one ProgressState model.

POST /api/now/v1/batch                     # FALLBACK PATH, observed once
  When the dependency cascade requires multiple plugins to install/update,
  the UI submits a multipart batch wrapping per-plugin GETs. The response is
  multipart/mixed with one Content-Type: application/json part per inner
  request. Each part body matches the install/upgrade response shape above.

  We do NOT implement the batch path in sub-project M. The direct GET path
  works for single-plugin operations, which is what PromotionPlan emits one
  at a time. Multi-plugin cascades are SN-server-managed by the install
  endpoint itself once it queues the work; we only need to poll progress.
```

### State value enumeration

From the captures plus the install response, SN's state enum is:
```
"0" = Pending      (initial response or pre-execution)
"1" = In Progress  (executing, percent_complete < 100)
"2" = Success      (terminal -- presumed; not yet observed in capture)
"3" = Failed       (terminal; observed once in earlier failed test)
"4" = Cancelled    (terminal; not yet observed)
```

Treat any state >= "2" as terminal. Treat "2" as success, "3" and "4" as
failure for OperationResult.success classification.

### Activate / deactivate / uninstall (NOT captured live)

The captures targeted upgrade (which uses /app/install). The other operations
were not captured because they require finding plugins in specific states on
the PDI. The strongest hypothesis from the URL pattern is:

```
GET /api/sn_appclient/appmanager/app/activate?app_id=...
GET /api/sn_appclient/appmanager/app/deactivate?app_id=...
GET /api/sn_appclient/appmanager/app/uninstall?app_id=...
```

Task 4's implementer SHOULD verify these endpoint paths on a live PDI before
hard-coding them. If the paths are wrong, the captured install response shape
should still match (it's the kickoff envelope, not the operation-specific
body). The poller and the response model are operation-agnostic.

### Plan deltas required (Task 4 + Task 7 substitutions)

When the implementer reaches Task 4, the following plan-as-written changes
apply because the original assumed POST + batch wrapping:

- `submit_install(plugin_id, version)` becomes a `GET` to
  `/api/sn_appclient/appmanager/app/install` with query params, returning
  the `result` object from the response.
- `submit_activate(plugin_id)` becomes a `GET` to
  `/api/sn_appclient/appmanager/app/activate?app_id=<source_app_id>` --
  CONFIRM ON A LIVE PDI before hard-coding.
- `submit_upgrade(plugin_id, target_version)` reuses `submit_install`
  with a target_version query param (SN treats it as an install with a
  newer version).
- No `_submit_via_batch` helper needed. The batch path is fallback-only
  and deferred to a follow-up sub-project if a single-plugin operation
  ever returns a multi-step cascade response.
- Progress polling path is `/api/sn_appclient/appmanager/progress/{tracker}`
  (NOT `/api/sn_cicd/progress/...` despite what the install response says).
- `ProgressState.from_sn` must accept BOTH the install-response shape
  (status/trackerId fields) AND the progress-poll shape (state/sys_id
  fields), normalising into the same model. Update Task 3's model and
  Task 6's poller accordingly.

### sn_si:13.9.23 example (the actual capture)

The Palo Alto NGFW upgrade triggered exactly one dependency POST and one
install GET. The dependency POST body was simply:
```
{"dependencies": "sn_si:13.9.23"}
```
Where `sn_si` is the scope of the Security Incident Response plugin that
NGFW depends on, and `13.9.23` is the minimum version required.

The install GET issued immediately after returned `trackerId =
"9e2bd8e23b3803106c7dfa9aa4e45abd"` and `rollback_version = "10.4.7"`.
Progress was then polled at `/api/sn_appclient/appmanager/progress/9e2bd8e2...`
showing nested sub-operations (Installing application package -> Installing
application sn_sec_panfw:10.5.2 -> Loading data for sn_sec_panfw -> ...).
