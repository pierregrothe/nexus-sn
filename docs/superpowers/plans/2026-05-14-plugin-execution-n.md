# Plugin Execution (Sub-project N) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Add `PluginExecutor.deactivate` and `.uninstall` with a mandatory impact gate (local `compute_impact` + live SN `appmanager_dependencies` cross-check), a `--force` bypass that demands typing the plugin id as a second confirmation, and a refusal for uninstalling `source=="servicenow"` base plugins. Wire the two new CLI commands (`nexus plugins deactivate`, `nexus plugins uninstall`) and swap the M-era rollback placeholders for the real deactivate/uninstall paths.

**Architecture:** New CLI surface mirrors install/activate/upgrade. `PluginExecutor` gets two public methods (deactivate/uninstall) plus a private `_check_impact_gate` helper used by both. The gate compares our cached `PluginImpact` (reverse deps + cross-scope refs) against SN's live dependency cascade, and surfaces a unified report. `--force` requires the user to type the plugin id verbatim. The existing private `_force=True` parameter remains for rollback bypass (already in place from sub-project M).

**Tech Stack:** Same as M — Python 3.14 + asyncio + httpx + Pydantic v2 frozen+strict + Rich + Typer.

**Branch:** `feat/plugins-deactivate-uninstall`. Spec stays at `docs/superpowers/specs/2026-05-13-plugin-execution-design.md` (covers M + N; sub-project N section starts after the "## Sub-project N: Destructive operations" heading).

---

## File map

**Modified files:**
- `src/nexus/plugins/errors.py` — add `PluginImpactBlockError` + `PluginUnsupportedError`
- `src/nexus/connectors/servicenow/protocol.py` — add `submit_deactivate` + `submit_uninstall`
- `src/nexus/connectors/servicenow/client.py` — implement the two new methods
- `tests/fakes/fake_sn_client.py` — add canned response queues for the two
- `src/nexus/plugins/executor.py` — add `deactivate`, `uninstall`, `_check_impact_gate`; update `_rollback` to use real endpoints
- `src/nexus/plugins/__init__.py` — re-export the two new errors
- `src/nexus/cli.py` — add `plugins_deactivate`, `plugins_uninstall` commands + help entries
- `scripts/smoke_plugins.py` — add smoke tests for the new commands

**Test files:**
- `tests/test_plugins_errors.py` — extend with tests for new error classes
- `tests/test_servicenow_appmanager.py` — extend with deactivate/uninstall endpoint tests
- `tests/test_fakes_sn_client_appmanager.py` — extend with deactivate/uninstall queue tests
- `tests/test_plugins_executor.py` — extend with deactivate/uninstall + impact-gate tests
- `tests/test_cli_plugins_execute.py` — extend with new CLI command tests

---

## Task 1: Error hierarchy additions

**Files:**
- Modify: `src/nexus/plugins/errors.py`
- Modify: `tests/test_plugins_errors.py`

Add two new error classes inheriting from `PluginExecutionError`:

```python
class PluginImpactBlockError(PluginExecutionError):
    """Raised when the impact gate blocks a destructive operation.

    Attributes:
        plugin_id: Plugin being deactivated/uninstalled.
        local_reverse_deps: Count from compute_impact().
        local_cross_scope_refs: Count from compute_impact().
        sn_dependency_count: Count from SN's appmanager/dependencies.
    """

    def __init__(
        self,
        plugin_id: str,
        local_reverse_deps: int,
        local_cross_scope_refs: int,
        sn_dependency_count: int,
    ) -> None:
        super().__init__(
            f"impact gate blocked operation on {plugin_id}: "
            f"local_reverse_deps={local_reverse_deps}, "
            f"local_cross_scope_refs={local_cross_scope_refs}, "
            f"sn_dependency_count={sn_dependency_count}"
        )
        self.plugin_id = plugin_id
        self.local_reverse_deps = local_reverse_deps
        self.local_cross_scope_refs = local_cross_scope_refs
        self.sn_dependency_count = sn_dependency_count


class PluginUnsupportedError(PluginExecutionError):
    """Raised when an operation is fundamentally unsupported by SN REST.

    Currently used for: uninstalling a base ServiceNow plugin
    (source == "servicenow").

    Attributes:
        plugin_id: The plugin id.
        reason: Human-readable explanation.
    """

    def __init__(self, plugin_id: str, reason: str) -> None:
        super().__init__(f"{plugin_id}: {reason}")
        self.plugin_id = plugin_id
        self.reason = reason
```

Update `__all__` alphabetical sort. Add tests verifying attributes + `isinstance` against `PluginExecutionError`.

Commit: `feat(plugins): add PluginImpactBlockError + PluginUnsupportedError`

---

## Task 2: SN client extensions for deactivate + uninstall

**Files:**
- Modify: `src/nexus/connectors/servicenow/protocol.py`
- Modify: `src/nexus/connectors/servicenow/client.py`
- Modify: `tests/test_servicenow_appmanager.py`

Based on the M-era live-discovery pattern (`GET /api/sn_appclient/appmanager/app/install`, `app/activate`), hypothesised endpoints:
- `GET /api/sn_appclient/appmanager/app/deactivate?app_id=<source_app_id>`
- `GET /api/sn_appclient/appmanager/app/uninstall?app_id=<source_app_id>`

These will be smoke-verified post-implementation. If a path differs, only one constant changes.

Add to protocol:

```python
async def submit_deactivate(self, source_app_id: str) -> dict[str, object]:
    """Submit a deactivate via /api/sn_appclient/appmanager/app/deactivate (GET)."""
    ...

async def submit_uninstall(self, source_app_id: str) -> dict[str, object]:
    """Submit an uninstall via /api/sn_appclient/appmanager/app/uninstall (GET)."""
    ...
```

Implement on ServiceNowClient mirroring `submit_activate`:

```python
_APPMANAGER_DEACTIVATE = "/api/sn_appclient/appmanager/app/deactivate"
_APPMANAGER_UNINSTALL = "/api/sn_appclient/appmanager/app/uninstall"

async def submit_deactivate(self, source_app_id: str) -> dict[str, object]:
    params: dict[str, str | int] = {"app_id": source_app_id}
    response = await self._get(self._APPMANAGER_DEACTIVATE, params=params)
    return cast(dict[str, object], response.get("result", {}))

async def submit_uninstall(self, source_app_id: str) -> dict[str, object]:
    params: dict[str, str | int] = {"app_id": source_app_id}
    response = await self._get(self._APPMANAGER_UNINSTALL, params=params)
    return cast(dict[str, object], response.get("result", {}))
```

Tests via httpx.MockTransport, mirroring `test_submit_activate_uses_get_with_app_id`.

Commit: `feat(connectors): add submit_deactivate + submit_uninstall to SN client`

---

## Task 3: FakeServiceNowClient queues for deactivate + uninstall

**Files:**
- Modify: `tests/fakes/fake_sn_client.py`
- Modify: `tests/test_fakes_sn_client_appmanager.py`

Add `self._deactivate_responses` and `self._uninstall_responses` lists in `__init__`. Add setters `queue_deactivate_response` and `queue_uninstall_response`. Add async methods `submit_deactivate(source_app_id)` and `submit_uninstall(source_app_id)` that pop from the respective queue (raise RuntimeError when empty).

Add minimal tests confirming FIFO behaviour and "raises when empty".

Commit: `test(fakes): add canned responses for deactivate + uninstall`

---

## Task 4: PluginExecutor.deactivate + uninstall + impact gate

**Files:**
- Modify: `src/nexus/plugins/executor.py`
- Modify: `tests/test_plugins_executor.py`

Add `_check_impact_gate(plugin_id, *, force) -> None` private helper. It:

1. Calls `compute_impact(inventory, plugin_id, client, cross_scope=True)` from `nexus.plugins.impact`. Capture `reverse_deps_count = len(impact.reverse_dependencies)` and `cross_scope_count = len(impact.cross_scope_refs)`.
2. Calls `fetch_dependencies(self._client, plugin_id, info.version)` to get SN's live cascade.
3. If `force=False` AND (any of the three counts > 0): raise `PluginImpactBlockError` with the three counts.

Add public methods:

```python
async def deactivate(self, plugin_id: str, *, force: bool = False) -> OperationResult:
    """Deactivate plugin_id with mandatory impact gate.

    Raises:
        PluginImpactBlockError: When force is False and the gate detects
            non-zero reverse-deps, cross-scope refs, or SN-cascade entries.
    """
    started = time.monotonic()
    try:
        info = self.lookup(plugin_id)
    except PluginNotFoundError as exc:
        return _failure_result("deactivate", plugin_id, str(exc), started)
    try:
        await self._check_impact_gate(plugin_id, force=force)
    except PluginImpactBlockError as exc:
        return _failure_result("deactivate", plugin_id, str(exc), started)
    # ... submit_deactivate + ProgressPoller (same pattern as activate)


async def uninstall(self, plugin_id: str, *, force: bool = False) -> OperationResult:
    """Uninstall plugin_id with mandatory impact gate + base-plugin refusal.

    Raises:
        PluginUnsupportedError: When source == 'servicenow' (no --force escape).
        PluginImpactBlockError: When force is False and the gate trips.
    """
    started = time.monotonic()
    try:
        info = self.lookup(plugin_id)
    except PluginNotFoundError as exc:
        return _failure_result("uninstall", plugin_id, str(exc), started)
    if info.source == "servicenow":
        # No --force escape: SN REST doesn't expose uninstall for base plugins.
        return _failure_result(
            "uninstall", plugin_id,
            "base ServiceNow plugins cannot be uninstalled via REST",
            started,
        )
    try:
        await self._check_impact_gate(plugin_id, force=force)
    except PluginImpactBlockError as exc:
        return _failure_result("uninstall", plugin_id, str(exc), started)
    # ... submit_uninstall + ProgressPoller
```

Extract a `_failure_result(action, plugin_id, message, started)` helper to keep the methods compact — install/activate/upgrade can adopt it in a follow-up cleanup pass (don't refactor them in this task).

Update `_rollback` to use the real endpoints:
- `rollback_install` -> `submit_uninstall(info.sys_id)` (was `submit_install`)
- `rollback_activate` -> `submit_deactivate(info.sys_id)` (was `submit_activate`)
- `rollback_upgrade` unchanged (already uses submit_upgrade with rollback_version)

The rollback path bypasses the impact gate by calling the client's `submit_uninstall` / `submit_deactivate` directly — NOT through `self.deactivate` / `self.uninstall`. This preserves the design rule from gap 2 in the spec.

Tests cover:
- deactivate success path (no impact, no force needed)
- deactivate blocked by impact gate (reverse_deps > 0, no force)
- deactivate with force=True bypasses gate
- deactivate of unknown plugin returns failure result
- uninstall success path (non-base plugin, no impact)
- uninstall of source=='servicenow' refused (no force escape)
- uninstall blocked by impact gate
- uninstall with force=True bypasses gate
- _rollback now uses submit_uninstall (queue an uninstall response in the test)

Commit: `feat(plugins): add PluginExecutor.deactivate + .uninstall with mandatory impact gate`

---

## Task 5: CLI commands deactivate + uninstall

**Files:**
- Modify: `src/nexus/cli.py`
- Modify: `tests/test_cli_plugins_execute.py`

Add two new commands following the install/activate pattern, with extra logic for `--force` second-confirm:

```python
@plugins_app.command("deactivate")
def plugins_deactivate(
    plugin_id: Annotated[str, typer.Argument(help="Plugin ID to deactivate")],
    instance: Annotated[str, typer.Option("--instance", help="Instance profile")] = "",
    force: Annotated[bool, typer.Option("--force", help="Bypass impact gate (requires type-id confirm)")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the action confirmation prompt")] = False,
) -> None:
    """Deactivate a plugin on the resolved instance.

    Blocks when impact gate detects reverse-deps or cross-scope refs unless
    --force is given. --force always requires typing the plugin id at the
    second prompt; --yes never skips that.
    """
    import asyncio
    from nexus.plugins.executor import PluginExecutor

    resolved = _plugins_for(instance)
    if resolved is None:
        console.print(Notice.warn("Plugin inventory empty."))
        console.print(Hint(label="Refresh", command="nexus instance refresh"))
        raise typer.Exit(1)
    meta, inventory = resolved
    _, _, token, _ = _acquire_token(meta.profile)

    async def _run() -> None:
        async with ServiceNowClient(instance_url=meta.url, token=token) as client:
            if not yes and not typer.confirm(f"Deactivate {plugin_id} on {meta.profile}?"):
                raise typer.Exit(0)
            if force:
                typed = typer.prompt(
                    f"--force bypasses the impact gate. Type the plugin id "
                    f"({plugin_id}) to confirm"
                )
                if typed != plugin_id:
                    err_console.print(Notice.error("Confirmation mismatch; aborting."))
                    raise typer.Exit(2)
            executor = PluginExecutor(client=client, inventory=inventory)
            result = await executor.deactivate(plugin_id, force=force)
            console.print(_result_panel(result))
            if not result.success:
                raise typer.Exit(1)

    asyncio.run(_run())
```

Same shape for `plugins_uninstall`. Add two help entries in `_PLUGINS_HELP`.

Tests:
- deactivate --help exists
- uninstall --help exists
- deactivate without --force, with inventory having reverse-deps → exit 1 (gate blocks)
- uninstall on source=='servicenow' → exit 1 with PluginUnsupportedError message

Commit: `feat(cli): add nexus plugins deactivate + uninstall with --force second-confirm`

---

## Task 6: Re-exports + smoke suite + final sweep

**Files:**
- Modify: `src/nexus/plugins/__init__.py`
- Modify: `scripts/smoke_plugins.py`
- Modify: `.ratchet.json`

Update `__init__.py` `__all__` to add `PluginImpactBlockError` + `PluginUnsupportedError`.

Add smoke tests:
- `deactivate --help` (sanity)
- `uninstall --help` (sanity)
- `deactivate <plugin> --yes` (cancelled by impact gate against a plugin known to have reverse-deps; expect exit 1)
- `uninstall <base-plugin>` (expect "cannot be uninstalled" message)
- `uninstall --help` shows --force option

Run full pytest. Run linters. Rebaseline ratchet for plugins/executor.py + plugins/errors.py (covered_lines may have moved). Push, open PR, wait for CI, merge.

Commit: `feat(plugins): re-export sub-project N error types + rebaseline ratchet + extend smoke suite`

---

## Self-review checklist

- [ ] Spec coverage: every "Sub-project N" requirement in `docs/superpowers/specs/2026-05-13-plugin-execution-design.md` has a task. The five rules (mandatory gate, --force escape with type-id confirm, --yes never skips force confirm, base-plugin uninstall refused, rollback bypasses gate) are all implemented.
- [ ] No placeholders: every code block is complete; the only "discovery" item (endpoint URL confirmation) is handled by smoke testing rather than a separate task because we already have one live capture and the pattern is firm.
- [ ] Type consistency: `submit_deactivate(source_app_id)` and `submit_uninstall(source_app_id)` mirror `submit_activate(source_app_id)`. `_failure_result` helper is named identically wherever introduced.
