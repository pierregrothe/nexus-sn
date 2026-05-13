# Plugin Execution -- Design Spec

Date: 2026-05-13
Status: approved

## Problem

The plugin management layer (sub-projects A-L+E) covers the full assess+plan
tier: scan, inventory, impact, advisories, drift, diff, promote-plan. The
missing tier is execution -- NEXUS cannot yet write to a ServiceNow instance
to install, activate, upgrade, deactivate, or uninstall plugins.

## Goals

- Install, activate, and upgrade plugins via the SN REST API (sub-project M).
- Execute a PromotionPlan YAML produced by `nexus plugins promote` (sub-project M).
- Deactivate and uninstall plugins with a mandatory impact gate (sub-project N).
- Block with a Rich progress bar during async SN operations (all ops).
- Roll back partial apply-plan failures in reverse order (best-effort).
- Zero new Python dependencies. Uses existing SN client primitives.

## Non-Goals

- Scheduling or cron-style automation of plugin updates.
- Dependency graph resolution (install A's dependencies before A) -- rely on
  SN to surface dependency errors and surface them as PluginProgressError.
- Downgrading a plugin version (not supported by SN REST).

## Sub-project M: Plugin execution core

### New modules

`src/nexus/plugins/executor.py`
  PluginExecutor -- orchestrates operations against a SN instance
  OperationResult -- frozen model (action, plugin_id, success, message,
                     duration_s, worker_id)
  OperationLog -- tuple of OperationResult; returned by apply_plan

`src/nexus/plugins/progress.py`
  ProgressPoller -- polls GET /api/now/progress/{worker_id} every 3s;
                    drives a Rich progress bar; returns OperationResult
  DEFAULT_TIMEOUT_S = 600  # 10 minutes

### SN API routing

PluginExecutor probes sn_appclient on first use (GET /api/sn_appclient/
app_management/health or equivalent lightweight check). If available,
use it for install/activate/upgrade (unified endpoint). If not, fall back:

```
Operation    sn_appclient (preferred)              Fallback
---------    -----------------------               --------
install      POST /api/sn_appclient/               POST /api/now/app-management/
             app_management/apply                  application
             {name, version}                       {name, version}

activate     POST /api/sn_appclient/               PATCH /api/now/table/
             app_management/apply                  v_plugin/<sys_id>
             {name}                                {active: "true"}

upgrade      POST /api/sn_appclient/               POST /api/now/app-management/
             app_management/upgrade                upgrade
             {name, version}                       {name, version}

progress     GET /api/now/progress/<worker_id>     (universal, no fallback)
```

Synchronous responses (PATCH activate returning 200 with no progress link)
are wrapped as a synthetic OperationResult with duration_s from elapsed time.

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

Executor takes a `ServiceNowClientProtocol` and an `InventorySource`
(callable that returns a fresh PluginInventory so it can look up sys_ids
from plugin_ids). Inventory is fetched once per executor lifetime; the
sys_id lookup is a pure dict read.

### apply_plan flow

```
1. Validate all plugin_ids in plan.actions exist in inventory.
   Refuse with PluginNotFoundError on any missing.
2. Display action table: N installs, M activates, K upgrades.
3. Prompt: "Execute N operations against <profile>? [y/N]"
4. Execute in order: installs first, then activates, then upgrades.
   Track undo_stack: list[(action, result)] of completed operations.
5. On success: append result to log, continue.
6. On failure (PluginProgressError or timeout):
   a. Stop forward progress.
   b. Print failure report: completed / failed / pending counts.
   c. Run rollback in reverse (see Rollback section).
   d. Raise PluginExecutionError with partial log.
7. On full success: return OperationLog.
   Caller (CLI) rescans inventory and prints summary.
```

### Rollback on partial failure

Rollback is best-effort. For each completed operation in reverse order:

```
activate  -> deactivate  (PATCH v_plugin active=false)
install   -> uninstall   (DELETE app-management, best-effort)
upgrade   -> warn only   (downgrade not supported via REST; log advisory)
```

Rollback results are appended to the OperationLog with action="rollback_*".
If a rollback step itself fails, log the failure and continue rolling back
remaining steps -- never abort rollback due to a secondary failure.

### New CLI commands (sub-project M)

```
nexus plugins install <plugin-id> [--version X.Y.Z]
nexus plugins activate <plugin-id>
nexus plugins upgrade <plugin-id> [--to X.Y.Z]
nexus plugins apply <plan.yaml>
```

All commands: show instance profile + plugin name before executing,
confirm prompt (skip with --yes), block with progress bar, show result.

### Error hierarchy additions

```python
class PluginExecutionError(NexusError): ...      # base for all exec errors
class PluginProgressError(PluginExecutionError): # SN returned error state
    worker_id: str
    error_message: str
class PluginTimeoutError(PluginExecutionError):  # polling exceeded limit
    worker_id: str
    elapsed_s: float
class PluginNotFoundError(PluginExecutionError): # plugin_id not in inventory
    plugin_id: str
```

## Sub-project N: Destructive operations

### Adds to PluginExecutor

```python
async def deactivate(self, plugin_id: str) -> OperationResult: ...
async def uninstall(self, plugin_id: str) -> OperationResult: ...
```

### Safety gate (mandatory, cannot be disabled without --force)

Before any deactivate or uninstall, `PluginExecutor` calls the existing
`compute_impact()`. If the result has non-zero `reverse_dependencies` or
`cross_scope_refs`, raise `PluginImpactBlockError` with the full impact
report. The CLI surfaces this as the same output as `nexus plugins impact`.

`--force` bypasses the gate after showing the impact report and requiring
a second explicit confirmation: "Impact check found N dependencies. Type
the plugin ID to confirm forced deactivation: "

Uninstall of a base SN plugin (source="servicenow") is refused with
`PluginUnsupportedError` -- SN REST does not support it.

### New CLI commands (sub-project N)

```
nexus plugins deactivate <plugin-id> [--force]
nexus plugins uninstall <plugin-id> [--force]
```

### Error hierarchy additions

```python
class PluginImpactBlockError(PluginExecutionError):
    impact: PluginImpact      # full impact report
class PluginUnsupportedError(PluginExecutionError):
    reason: str               # "base plugin uninstall not supported via REST"
```

## Testing

All tests use `FakeServiceNowClient` with canned responses for each SN
endpoint. `FakeProgressPoller` returns a configurable sequence of progress
states (in_progress x N, then success or error). No subprocess mocking.

Key test scenarios:
- install: success path, SN returns error state, timeout
- activate: synchronous (200, no progress link), async (progress worker)
- upgrade: success path, best-effort rollback warning
- apply_plan: all success, partial failure with rollback, rollback secondary failure
- deactivate: impact gate blocks, --force bypasses, uninstall base plugin refused
- sn_appclient unavailable: falls back to app-management + v_plugin endpoints

## Roadmap placement

Sub-project M and N are both 2026.05.x patches. M ships first (safe ops only),
N ships after M is validated (adds destructive ops + safety gate).

This completes the plugin management tier: assess (A-L+E) -> plan (B promote)
-> execute (M+N). The full lifecycle is then:

  scan -> analyze -> plan -> execute -> rescan -> verify
