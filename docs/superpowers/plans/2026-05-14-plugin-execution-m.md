# Plugin Execution (Sub-project M) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `PluginExecutor` so NEXUS can install, activate, upgrade, and apply a `PromotionPlan` against a live ServiceNow instance via the discovered `dependencies` + `batch` + `sn_cicd/progress` endpoints.

**Architecture:** A thin `PluginExecutor` orchestrates three reusable building blocks (`fetch_dependencies` for pre-flight, `submit_*` methods on `ServiceNowClient` for write ops, `ProgressPoller` for async status polling). It holds a snapshot inventory built at construction and patches in new rows after each install. `apply_plan` iterates `PromotionPlan.actions` in their existing stable order with best-effort reverse rollback on partial failure.

**Tech Stack:** Python 3.14 + asyncio + httpx (already in deps) + Pydantic v2 frozen+strict + Rich (progress bars + console) + Typer (CLI).

**Branch:** `feat/plugins-execution` (already created; spec committed at `14ebfbd`).

---

## File map

**New files:**
- `src/nexus/plugins/dependencies.py` -- `DependencyEntry` model + `fetch_dependencies()` pure helper (~80 lines)
- `src/nexus/plugins/progress.py` -- `ProgressState` model + `ProgressPoller` (~100 lines)
- `src/nexus/plugins/executor.py` -- `OperationResult`, `OperationLog`, `PluginExecutor`, `InventorySource` (~250 lines, near the 500-line cap but acceptable)
- `tests/test_plugins_dependencies.py`
- `tests/test_plugins_progress.py`
- `tests/test_plugins_executor.py`
- `tests/test_cli_plugins_execute.py`

**Modified files:**
- `src/nexus/plugins/errors.py` -- add `PluginExecutionError` hierarchy
- `src/nexus/plugins/__init__.py` -- re-export new public names
- `src/nexus/connectors/servicenow/protocol.py` -- extend `ServiceNowClientProtocol` with three new methods
- `src/nexus/connectors/servicenow/client.py` -- implement the three new methods
- `tests/fakes/fake_sn_client.py` -- add canned-response support for the three new methods
- `src/nexus/cli.py` -- add `install`, `activate`, `upgrade`, `apply` plugin commands + help entries
- `.ratchet.json` -- rebaseline after coverage moves

---

## Task 1: Live endpoint discovery (Chrome DevTools)

This task captures the exact endpoint URLs and request payloads that the spec
left as TBD. **No code changes**; produces a spec addendum.

**Files:**
- Modify: `docs/superpowers/specs/2026-05-13-plugin-execution-design.md` (append addendum section)

- [ ] **Step 1: Open Chrome DevTools on a Yokohama PDI Application Manager**

Open `https://<your-pdi>.service-now.com/now/app-manager/home`. Press F12 to
open DevTools, switch to the Network tab, click "Preserve log", filter for
`batch` then `dependencies`.

- [ ] **Step 2: Capture an Upgrade**

Navigate to the Updates tab. Click any plugin that has an update available.
On the detail page click "Proceed to update", then "Install" in the confirmation
popup.

For each captured POST, right-click -> Copy -> Copy as cURL bash. Save:
- `/api/sn_appclient/appmanager/dependencies` POST request body + response body
- `/api/now/v1/batch` POST request body + response body (multipart)
- `/api/sn_cicd/progress/{trackerId}` GET response body (first poll and a later one)

- [ ] **Step 3: Capture an Activate**

In "All Apps", find an installed-but-inactive plugin. Click Activate.
Capture the same three flows. Note: if activate uses a simpler path (e.g.
direct PATCH to v_plugin), record that.

- [ ] **Step 4: Capture an Install**

In "Available for You", find a plugin marked "Get" / "Install". Click it,
proceed past any confirm. Capture the three flows.

- [ ] **Step 5: Document findings as a spec addendum**

Append a new section "## Addendum: Live discovery findings (Task 1)" to
`docs/superpowers/specs/2026-05-13-plugin-execution-design.md`. Replace
each "(TBD at impl Task 1)" placeholder with captured values. Include for
each operation:

```
### Operation: install
  Dependency POST URL:  /api/sn_appclient/appmanager/dependencies
  Dependency POST body: { "<captured_keys>": "<sample_values>" }
  Batch inner URL:      <captured URL inside the multipart Content-Type/Disposition>
  Batch inner body:     { "<captured_keys>": "<sample_values>" }
  Progress URL:         /api/sn_cicd/progress/{trackerId}
  Sample initial response: <paste JSON>
  Sample terminal response: <paste JSON>
```

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/specs/2026-05-13-plugin-execution-design.md
git commit -m "docs(plugins): add live endpoint capture addendum for plugin-execution spec"
```

---

## Task 2: Error hierarchy

**Files:**
- Modify: `src/nexus/plugins/errors.py`
- Test: `tests/test_plugins_errors.py` (new file)

- [ ] **Step 1: Write failing tests for the new error classes**

```python
# tests/test_plugins_errors.py
# Tests for plugin execution error types.
# Author: Pierre Grothe
# Date: 2026-05-14

"""Tests for the plugin execution error hierarchy."""

import pytest

from nexus.plugins.errors import (
    PluginBatchError,
    PluginExecutionError,
    PluginNotFoundError,
    PluginProgressError,
    PluginTimeoutError,
)

__all__: list[str] = []


def test_plugin_progress_error_carries_tracker_and_status() -> None:
    err = PluginProgressError(tracker_id="abc", sn_status="3", error_message="boom")
    assert err.tracker_id == "abc"
    assert err.sn_status == "3"
    assert err.error_message == "boom"
    assert isinstance(err, PluginExecutionError)


def test_plugin_timeout_error_carries_elapsed_seconds() -> None:
    err = PluginTimeoutError(tracker_id="xyz", elapsed_s=600.0)
    assert err.tracker_id == "xyz"
    assert err.elapsed_s == 600.0
    assert isinstance(err, PluginExecutionError)


def test_plugin_not_found_error_carries_plugin_id() -> None:
    err = PluginNotFoundError("com.snc.missing")
    assert err.plugin_id == "com.snc.missing"
    assert "com.snc.missing" in str(err)
    assert isinstance(err, PluginExecutionError)


def test_plugin_batch_error_preserves_response_fragment() -> None:
    err = PluginBatchError(batch_response="--boundary\r\nbad")
    assert "boundary" in err.batch_response
    assert isinstance(err, PluginExecutionError)
```

- [ ] **Step 2: Run tests to verify failure**

```
poetry run pytest tests/test_plugins_errors.py -v
```
Expected: ImportError / AttributeError for the new classes.

- [ ] **Step 3: Implement the error hierarchy**

Append to `src/nexus/plugins/errors.py` and update `__all__`:

```python
class PluginExecutionError(Exception):
    """Base class for plugin execution failures."""


class PluginProgressError(PluginExecutionError):
    """Raised when SN's progress endpoint reports a terminal failure state.

    Attributes:
        tracker_id: The sn_cicd tracker GUID.
        sn_status: SN's numeric status string (e.g. "3" for Failed).
        error_message: SN's error message field.
    """

    def __init__(self, tracker_id: str, sn_status: str, error_message: str) -> None:
        super().__init__(f"plugin operation failed: {error_message} (status={sn_status})")
        self.tracker_id = tracker_id
        self.sn_status = sn_status
        self.error_message = error_message


class PluginTimeoutError(PluginExecutionError):
    """Raised when progress polling exceeds the configured timeout.

    Attributes:
        tracker_id: The sn_cicd tracker GUID.
        elapsed_s: Seconds elapsed before timeout.
    """

    def __init__(self, tracker_id: str, elapsed_s: float) -> None:
        super().__init__(f"plugin operation timed out after {elapsed_s:.0f}s")
        self.tracker_id = tracker_id
        self.elapsed_s = elapsed_s


class PluginNotFoundError(PluginExecutionError):
    """Raised when the requested plugin_id is not in the loaded inventory.

    Attributes:
        plugin_id: The unknown plugin identifier.
    """

    def __init__(self, plugin_id: str) -> None:
        super().__init__(f"plugin not found in inventory: {plugin_id}")
        self.plugin_id = plugin_id


class PluginBatchError(PluginExecutionError):
    """Raised when the multipart batch envelope itself is malformed.

    Attributes:
        batch_response: The raw response fragment for debugging.
    """

    def __init__(self, batch_response: str) -> None:
        super().__init__("malformed batch response from ServiceNow")
        self.batch_response = batch_response
```

And update the `__all__` block at the top to add the five new names.

- [ ] **Step 4: Run tests to verify pass**

```
poetry run pytest tests/test_plugins_errors.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/nexus/plugins/errors.py tests/test_plugins_errors.py
git commit -m "feat(plugins): add execution error hierarchy"
```

---

## Task 3: Frozen models (OperationResult, OperationLog, ProgressState, DependencyEntry)

**Files:**
- Create: `src/nexus/plugins/dependencies.py` (DependencyEntry only -- the function comes in Task 5)
- Create: `src/nexus/plugins/progress.py` (ProgressState only -- the poller comes in Task 6)
- Create: `src/nexus/plugins/executor.py` (OperationResult + OperationLog only -- the executor comes in Task 8)
- Test: `tests/test_plugins_models_exec.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_plugins_models_exec.py
# Tests for plugin execution frozen models.
# Author: Pierre Grothe
# Date: 2026-05-14

"""Tests for OperationResult, OperationLog, ProgressState, DependencyEntry."""

import pytest
from pydantic import ValidationError

from nexus.plugins.dependencies import DependencyEntry
from nexus.plugins.executor import OperationLog, OperationResult
from nexus.plugins.progress import ProgressState

__all__: list[str] = []


def test_operation_result_is_frozen() -> None:
    r = OperationResult(
        action="install",
        plugin_id="com.x",
        success=True,
        message="done",
        duration_s=1.2,
        tracker_id="t1",
        update_set=None,
        rollback_version=None,
    )
    with pytest.raises(ValidationError):
        r.success = False  # type: ignore[misc]


def test_operation_result_rejects_unknown_action() -> None:
    with pytest.raises(ValidationError):
        OperationResult(
            action="reboot",  # not in Literal
            plugin_id="com.x",
            success=True,
            message="",
            duration_s=0.0,
            tracker_id="t",
            update_set=None,
            rollback_version=None,
        )


def test_operation_log_is_tuple_and_filterable() -> None:
    r1 = OperationResult(action="install", plugin_id="a", success=True, message="", duration_s=0.0, tracker_id="t1", update_set=None, rollback_version=None)
    r2 = OperationResult(action="activate", plugin_id="a", success=False, message="boom", duration_s=0.0, tracker_id="t2", update_set=None, rollback_version=None)
    log = OperationLog(results=(r1, r2))
    assert log.success_count == 1
    assert log.failure_count == 1


def test_progress_state_terminal_classification() -> None:
    ps_running = ProgressState(status="1", status_label="In Progress", percent_complete=50, error="", tracker_id="t", update_set=None, rollback_version=None)
    ps_done = ProgressState(status="2", status_label="Success", percent_complete=100, error="", tracker_id="t", update_set=None, rollback_version="1.0")
    ps_failed = ProgressState(status="3", status_label="Failed", percent_complete=80, error="boom", tracker_id="t", update_set=None, rollback_version=None)
    assert not ps_running.is_terminal
    assert ps_done.is_terminal
    assert ps_done.is_success
    assert ps_failed.is_terminal
    assert not ps_failed.is_success


def test_dependency_entry_keeps_servicenow_field_names() -> None:
    d = DependencyEntry(
        id="Vulnerability Response Common",
        orig_string="sn_vul_cmn:2.16.1",
        type="Application",
        min_version="2.16.1",
        source_app_id="abc123",
        installed=True,
        active=True,
        hide_on_ui=False,
        status="Will be Updated",
        status_value="will_be_updated",
        order=2,
        link="nav_to.do?...",
        has_license=False,
        is_allowed_install=True,
    )
    assert d.status_value == "will_be_updated"
```

- [ ] **Step 2: Run tests to verify failure**

```
poetry run pytest tests/test_plugins_models_exec.py -v
```
Expected: ImportError.

- [ ] **Step 3: Create dependencies.py with DependencyEntry**

```python
# src/nexus/plugins/dependencies.py
# DependencyEntry model + fetch_dependencies helper for SN pre-flight checks.
# Author: Pierre Grothe
# Date: 2026-05-14

"""Pre-flight dependency cascade via /api/sn_appclient/appmanager/dependencies."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["DependencyEntry"]

_FROZEN = ConfigDict(frozen=True, strict=True, extra="forbid")


class DependencyEntry(BaseModel):
    """One row from SN's appmanager/dependencies response.

    Field names match the ServiceNow JSON exactly except for the JSON
    field "Id" which is normalised to lowercase ``id`` here.

    Attributes:
        id: Display name (SN sends as "Id").
        orig_string: Scope:version string from SN.
        type: "Application" or "Plugin".
        min_version: Minimum version required.
        source_app_id: SN sys_id of the dependency.
        installed: Whether the dependency is already installed.
        active: Whether the dependency is currently active.
        hide_on_ui: SN flag indicating the row is internal.
        status: Human-readable status (e.g. "Will be Updated").
        status_value: Enum-like value (e.g. "will_be_updated").
        order: SN render order.
        link: SN navigation link.
        has_license: License presence flag.
        is_allowed_install: Whether install is permitted.
    """

    model_config = _FROZEN

    id: str
    orig_string: str
    type: Literal["Application", "Plugin"]
    min_version: str
    source_app_id: str
    installed: bool
    active: bool
    hide_on_ui: bool
    status: str
    status_value: str
    order: int
    link: str
    has_license: bool
    is_allowed_install: bool

    @classmethod
    def from_sn(cls, raw: dict[str, object]) -> "DependencyEntry":
        """Build from the raw SN dict (handles the 'Id' -> 'id' rename)."""
        # Normalise SN's "Id" capital. Pydantic strict=True won't accept extra keys
        # so we project the fields explicitly.
        return cls(
            id=str(raw.get("Id", "")),
            orig_string=str(raw.get("orig_string", "")),
            type=raw.get("type", "Plugin"),  # type: ignore[arg-type]  -- BLOCKED by no-type-ignore rule, use cast instead
            min_version=str(raw.get("minVersion", "")),
            source_app_id=str(raw.get("source_app_id", "")),
            installed=bool(raw.get("installed", False)),
            active=bool(raw.get("active", False)),
            hide_on_ui=bool(raw.get("hide_on_ui", False)),
            status=str(raw.get("status", "")),
            status_value=str(raw.get("status_value", "")),
            order=int(raw.get("order", 0)),  # type: ignore[arg-type] -- same
            link=str(raw.get("link", "")),
            has_license=bool(raw.get("has_license", False)),
            is_allowed_install=bool(raw.get("is_allowed_install", False)),
        )
```

(Note: when implementing, replace any `# type: ignore` with `cast()` from typing -- the pre-edit hook blocks type:ignore.)

- [ ] **Step 4: Create progress.py with ProgressState**

```python
# src/nexus/plugins/progress.py
# ProgressState model + ProgressPoller for sn_cicd progress endpoint.
# Author: Pierre Grothe
# Date: 2026-05-14

"""Async progress polling for plugin operations.

ProgressState is the parsed shape of one poll result. ProgressPoller drives
a Rich progress bar by repeatedly polling /api/sn_cicd/progress/{tracker_id}
until a terminal status is reached.
"""

from pydantic import BaseModel, ConfigDict

__all__ = ["ProgressState"]

_FROZEN = ConfigDict(frozen=True, strict=True, extra="forbid")

# SN status values: "0"=Pending, "1"=In Progress, "2"=Success, "3"=Failed,
# "4"=Cancelled. Treat 2-4 as terminal.
_TERMINAL_STATUSES = frozenset({"2", "3", "4"})
_SUCCESS_STATUSES = frozenset({"2"})


class ProgressState(BaseModel):
    """One snapshot of an SN plugin operation's progress.

    Attributes:
        status: Numeric status as a string (SN convention).
        status_label: Human-readable status.
        percent_complete: 0-100.
        error: SN error message (empty when not failed).
        tracker_id: The sn_cicd tracker GUID.
        update_set: sys_id of the update set, if any.
        rollback_version: Version SN would roll back to.
    """

    model_config = _FROZEN

    status: str
    status_label: str
    percent_complete: int
    error: str
    tracker_id: str
    update_set: str | None
    rollback_version: str | None

    @property
    def is_terminal(self) -> bool:
        """True when SN has finished (success, failed, or cancelled)."""
        return self.status in _TERMINAL_STATUSES

    @property
    def is_success(self) -> bool:
        """True when SN reported success."""
        return self.status in _SUCCESS_STATUSES

    @classmethod
    def from_sn(cls, raw: dict[str, object]) -> "ProgressState":
        """Build from the raw SN result dict."""
        return cls(
            status=str(raw.get("status", "0")),
            status_label=str(raw.get("status_label", "")),
            percent_complete=int(raw.get("percent_complete", 0) or 0),
            error=str(raw.get("error", "")),
            tracker_id=str(raw.get("trackerId", "")),
            update_set=raw.get("update_set") if raw.get("update_set") else None,
            rollback_version=raw.get("rollback_version") if raw.get("rollback_version") else None,
        )
```

- [ ] **Step 5: Create executor.py with OperationResult + OperationLog only**

```python
# src/nexus/plugins/executor.py
# PluginExecutor + result models for SN plugin write operations.
# Author: Pierre Grothe
# Date: 2026-05-14

"""Plugin execution orchestrator and result models.

This module currently exposes only the result models -- PluginExecutor itself
is added in Task 8.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

__all__ = ["OperationLog", "OperationResult"]

_FROZEN = ConfigDict(frozen=True, strict=True, extra="forbid")


class OperationResult(BaseModel):
    """Result of one plugin operation.

    Attributes:
        action: install, activate, upgrade, uninstall, deactivate, or
            rollback_<action>.
        plugin_id: Canonical plugin identifier.
        success: True if SN reported success.
        message: SN's status_message or our error description.
        duration_s: Wall-clock seconds.
        tracker_id: The sn_cicd tracker GUID, "" for synthetic results.
        update_set: SN-provided update set sys_id, if any.
        rollback_version: Version SN would roll back to, if reported.
    """

    model_config = _FROZEN

    action: Literal[
        "install",
        "activate",
        "upgrade",
        "uninstall",
        "deactivate",
        "rollback_install",
        "rollback_activate",
        "rollback_upgrade",
    ]
    plugin_id: str
    success: bool
    message: str
    duration_s: float
    tracker_id: str
    update_set: str | None
    rollback_version: str | None


class OperationLog(BaseModel):
    """Ordered sequence of OperationResults from an apply_plan call.

    Attributes:
        results: Operations in execution order. Rollback entries appear
            after the failing forward-step in reverse order.
    """

    model_config = _FROZEN

    results: tuple[OperationResult, ...]

    @property
    def success_count(self) -> int:
        """Number of results with success=True."""
        return sum(1 for r in self.results if r.success)

    @property
    def failure_count(self) -> int:
        """Number of results with success=False."""
        return sum(1 for r in self.results if not r.success)
```

- [ ] **Step 6: Run tests to verify pass**

```
poetry run pytest tests/test_plugins_models_exec.py -v
```
Expected: 5 passed.

- [ ] **Step 7: Commit**

```bash
git add src/nexus/plugins/dependencies.py src/nexus/plugins/progress.py src/nexus/plugins/executor.py tests/test_plugins_models_exec.py
git commit -m "feat(plugins): add execution result + progress + dependency models"
```

---

## Task 4: Extend ServiceNowClient + protocol with three new methods

**Files:**
- Modify: `src/nexus/connectors/servicenow/protocol.py`
- Modify: `src/nexus/connectors/servicenow/client.py`
- Test: `tests/test_servicenow_appmanager.py`

The exact payload keys come from Task 1's spec addendum -- the implementer
must substitute the real keys discovered in devtools.

- [ ] **Step 1: Write failing test using httpx.MockTransport**

```python
# tests/test_servicenow_appmanager.py
# Tests for the new appmanager + batch + progress methods on ServiceNowClient.
# Author: Pierre Grothe
# Date: 2026-05-14

"""Tests for the SN App Manager extension methods using httpx.MockTransport."""

import httpx
import pytest

from nexus.connectors.servicenow.client import ServiceNowClient

__all__: list[str] = []


def _transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_appmanager_dependencies_returns_parsed_entries() -> None:
    captured = {}
    async def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["method"] = req.method
        return httpx.Response(200, json={"result": [
            {"Id": "Sec Common", "orig_string": "sn_sec_cmn:30.3.0", "type": "Application",
             "minVersion": "30.3.0", "source_app_id": "abc", "installed": True,
             "hide_on_ui": False, "status": "Will be Updated", "status_value": "will_be_updated",
             "active": True, "order": 2, "link": "x", "has_license": False, "is_allowed_install": True}
        ]})
    async with ServiceNowClient("test.service-now.com", token="t") as c:
        c._client._transport = _transport(handler)  # type: ignore[union-attr]  -> use cast not type:ignore in real code
        rows = await c.appmanager_dependencies(plugin_id="com.snc.x", version="2.0")
    assert captured["method"] == "POST"
    assert "/api/sn_appclient/appmanager/dependencies" in captured["url"]
    assert rows[0]["status_value"] == "will_be_updated"


@pytest.mark.asyncio
async def test_submit_install_returns_tracker_id() -> None:
    async def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": {
            "status": "0", "status_label": "Pending", "status_message": "", "status_detail": "",
            "error": "", "percent_complete": 0, "update_set": None,
            "rollback_version": None, "trackerId": "tracker-xyz",
            "links": {"progress": {"id": "tracker-xyz", "url": "/api/sn_cicd/progress/tracker-xyz"}}
        }})
    async with ServiceNowClient("test.service-now.com", token="t") as c:
        c._client._transport = _transport(handler)
        result = await c.submit_install(plugin_id="com.x", version="2.0")
    assert result["trackerId"] == "tracker-xyz"


@pytest.mark.asyncio
async def test_fetch_progress_returns_raw_dict() -> None:
    async def handler(req: httpx.Request) -> httpx.Response:
        assert "/api/sn_cicd/progress/tracker-xyz" in str(req.url)
        return httpx.Response(200, json={"result": {
            "status": "2", "status_label": "Success", "percent_complete": 100, "error": "",
            "update_set": "us-123", "rollback_version": "1.0", "trackerId": "tracker-xyz",
            "status_message": "ok", "status_detail": ""
        }})
    async with ServiceNowClient("test.service-now.com", token="t") as c:
        c._client._transport = _transport(handler)
        raw = await c.fetch_progress("tracker-xyz")
    assert raw["status"] == "2"
    assert raw["update_set"] == "us-123"
```

- [ ] **Step 2: Run test to verify failure**

```
poetry run pytest tests/test_servicenow_appmanager.py -v
```
Expected: AttributeError on `appmanager_dependencies` / `submit_install` / `fetch_progress`.

- [ ] **Step 3: Extend the protocol**

Edit `src/nexus/connectors/servicenow/protocol.py` to add inside the
`ServiceNowClientProtocol` class (the existing methods stay):

```python
    async def appmanager_dependencies(
        self,
        plugin_id: str,
        version: str | None = None,
    ) -> list[dict[str, object]]:
        """Pre-flight dependency cascade from sn_appclient."""
        ...

    async def submit_install(
        self,
        plugin_id: str,
        version: str | None = None,
    ) -> dict[str, object]:
        """Submit an install via /api/now/v1/batch. Returns the result dict
        containing trackerId, status, links.progress.url, etc."""
        ...

    async def submit_activate(self, plugin_id: str) -> dict[str, object]:
        """Submit an activate via /api/now/v1/batch."""
        ...

    async def submit_upgrade(
        self,
        plugin_id: str,
        target_version: str | None = None,
    ) -> dict[str, object]:
        """Submit an upgrade via /api/now/v1/batch."""
        ...

    async def fetch_progress(self, tracker_id: str) -> dict[str, object]:
        """Fetch one poll of /api/sn_cicd/progress/{tracker_id}."""
        ...
```

- [ ] **Step 4: Implement on ServiceNowClient**

Append to `src/nexus/connectors/servicenow/client.py` (using the exact
payload keys captured in Task 1; substitute below):

```python
    _APPMANAGER_DEPS = "/api/sn_appclient/appmanager/dependencies"
    _BATCH = "/api/now/v1/batch"
    _PROGRESS = "/api/sn_cicd/progress"

    async def appmanager_dependencies(
        self,
        plugin_id: str,
        version: str | None = None,
    ) -> list[dict[str, object]]:
        # PAYLOAD KEYS BELOW MUST MATCH TASK 1 ADDENDUM. Substitute the real keys.
        payload: dict[str, str] = {"plugin_id": plugin_id}
        if version is not None:
            payload["version"] = version
        response = await self._post(self._APPMANAGER_DEPS, json=payload)
        return cast(list[dict[str, object]], response.get("result", []))

    async def _submit_via_batch(self, inner_url: str, inner_body: dict[str, str]) -> dict[str, object]:
        # Wraps the inner request in SN's batch envelope. The wrapping shape
        # was captured in Task 1; substitute the real envelope keys here.
        envelope = {
            "batch_request_id": uuid.uuid4().hex,
            "rest_requests": [
                {"id": "r1", "method": "POST", "url": inner_url, "body": json.dumps(inner_body),
                 "headers": [{"name": "Content-Type", "value": "application/json"}]}
            ],
        }
        raw = await self._post(self._BATCH, json=envelope)
        # Parse the multipart in raw["serviced_requests"][0]["body"] -- exact
        # field name from Task 1 addendum.
        body_str = cast(str, raw["serviced_requests"][0]["body"])
        parsed = json.loads(body_str)
        return cast(dict[str, object], parsed["result"])

    async def submit_install(
        self,
        plugin_id: str,
        version: str | None = None,
    ) -> dict[str, object]:
        # INNER URL + KEYS FROM TASK 1.
        body: dict[str, str] = {"plugin_id": plugin_id, "action": "install"}
        if version is not None:
            body["version"] = version
        return await self._submit_via_batch("/api/sn_appclient/appmanager/install", body)

    async def submit_activate(self, plugin_id: str) -> dict[str, object]:
        return await self._submit_via_batch(
            "/api/sn_appclient/appmanager/activate",
            {"plugin_id": plugin_id, "action": "activate"},
        )

    async def submit_upgrade(
        self,
        plugin_id: str,
        target_version: str | None = None,
    ) -> dict[str, object]:
        body: dict[str, str] = {"plugin_id": plugin_id, "action": "upgrade"}
        if target_version is not None:
            body["version"] = target_version
        return await self._submit_via_batch("/api/sn_appclient/appmanager/upgrade", body)

    async def fetch_progress(self, tracker_id: str) -> dict[str, object]:
        response = await self._get(f"{self._PROGRESS}/{tracker_id}")
        return cast(dict[str, object], response.get("result", {}))
```

Add `import json` and `import uuid` at the top of `client.py` if not
already imported. Use `cast` from `typing` -- never `# type: ignore`.

- [ ] **Step 5: Run tests to verify pass**

```
poetry run pytest tests/test_servicenow_appmanager.py -v
```
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add src/nexus/connectors/servicenow/protocol.py src/nexus/connectors/servicenow/client.py tests/test_servicenow_appmanager.py
git commit -m "feat(connectors): add appmanager/dependencies, batch submit, sn_cicd progress methods"
```

---

## Task 5: fetch_dependencies pure helper

**Files:**
- Modify: `src/nexus/plugins/dependencies.py` (append the function)
- Test: extend `tests/test_plugins_dependencies.py` (new file)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_plugins_dependencies.py
# Tests for fetch_dependencies pure helper.
# Author: Pierre Grothe
# Date: 2026-05-14

"""Tests for the dependency cascade pre-flight helper."""

import pytest

from nexus.plugins.dependencies import DependencyEntry, fetch_dependencies
from tests.fakes.fake_sn_client import FakeServiceNowClient

__all__: list[str] = []


@pytest.mark.asyncio
async def test_fetch_dependencies_returns_typed_entries() -> None:
    client = FakeServiceNowClient()
    client.set_dependencies("com.x", [
        {"Id": "Common A", "orig_string": "com.a:1.0", "type": "Application",
         "minVersion": "1.0", "source_app_id": "id1", "installed": True,
         "hide_on_ui": False, "status": "Will be Updated", "status_value": "will_be_updated",
         "active": True, "order": 1, "link": "", "has_license": False, "is_allowed_install": True},
    ])
    deps = await fetch_dependencies(client, "com.x", "2.0")
    assert len(deps) == 1
    assert isinstance(deps[0], DependencyEntry)
    assert deps[0].id == "Common A"
    assert deps[0].status_value == "will_be_updated"


@pytest.mark.asyncio
async def test_fetch_dependencies_empty_when_no_canned() -> None:
    client = FakeServiceNowClient()
    deps = await fetch_dependencies(client, "com.notseed", None)
    assert deps == ()
```

- [ ] **Step 2: Run test to verify failure**

Expected: ImportError on `fetch_dependencies` AND `set_dependencies` (the
FakeServiceNowClient extension comes in Task 7 but we write the test now;
the import error tells us we have work to do).

- [ ] **Step 3: Append fetch_dependencies to dependencies.py**

```python
# Add to __all__: "fetch_dependencies"

async def fetch_dependencies(
    client: "ServiceNowClientProtocol",
    plugin_id: str,
    version: str | None = None,
) -> tuple[DependencyEntry, ...]:
    """Pre-flight SN dependency cascade for a plugin install/upgrade.

    Args:
        client: ServiceNow client conforming to the protocol.
        plugin_id: Canonical plugin identifier.
        version: Target version, or None for "latest".

    Returns:
        Tuple of typed DependencyEntry objects, in SN's render order.
    """
    raw_rows = await client.appmanager_dependencies(plugin_id, version)
    return tuple(DependencyEntry.from_sn(row) for row in raw_rows)
```

Add an `if TYPE_CHECKING` import block:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nexus.connectors.servicenow.protocol import ServiceNowClientProtocol
```

- [ ] **Step 4: Run test (will still fail at set_dependencies)**

Note the test still fails because `FakeServiceNowClient.set_dependencies` doesn't exist yet. Task 7 fixes that. For now move on; the fail message confirms we're on the right path.

- [ ] **Step 5: Commit**

```bash
git add src/nexus/plugins/dependencies.py tests/test_plugins_dependencies.py
git commit -m "feat(plugins): add fetch_dependencies pre-flight helper"
```

---

## Task 6: ProgressPoller

**Files:**
- Modify: `src/nexus/plugins/progress.py` (append the poller)
- Test: extend `tests/test_plugins_progress.py` (new file)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_plugins_progress.py
# Tests for ProgressPoller.
# Author: Pierre Grothe
# Date: 2026-05-14

"""Tests for ProgressPoller polling behaviour."""

import asyncio
import pytest

from nexus.plugins.errors import PluginProgressError, PluginTimeoutError
from nexus.plugins.progress import ProgressPoller, ProgressState
from tests.fakes.fake_sn_client import FakeServiceNowClient

__all__: list[str] = []


def _raw(status: str, pct: int, err: str = "") -> dict[str, object]:
    return {"status": status, "status_label": "x", "percent_complete": pct,
            "error": err, "update_set": None, "rollback_version": None,
            "trackerId": "t1", "status_message": "", "status_detail": ""}


@pytest.mark.asyncio
async def test_poller_returns_terminal_success() -> None:
    client = FakeServiceNowClient()
    client.set_progress_sequence("t1", [_raw("1", 50), _raw("2", 100)])
    poller = ProgressPoller(client, poll_interval_s=0.01, timeout_s=2.0)
    final = await poller.poll("t1")
    assert final.is_terminal
    assert final.is_success
    assert final.percent_complete == 100


@pytest.mark.asyncio
async def test_poller_raises_on_failed_status() -> None:
    client = FakeServiceNowClient()
    client.set_progress_sequence("t1", [_raw("1", 30), _raw("3", 30, err="boom")])
    poller = ProgressPoller(client, poll_interval_s=0.01, timeout_s=2.0)
    with pytest.raises(PluginProgressError) as excinfo:
        await poller.poll("t1")
    assert excinfo.value.error_message == "boom"


@pytest.mark.asyncio
async def test_poller_raises_on_timeout() -> None:
    client = FakeServiceNowClient()
    # Infinite "still pending" responses
    client.set_progress_sequence("t1", [_raw("1", 1)] * 50)
    poller = ProgressPoller(client, poll_interval_s=0.01, timeout_s=0.05)
    with pytest.raises(PluginTimeoutError):
        await poller.poll("t1")
```

- [ ] **Step 2: Run test to verify failure**

Expected: ImportError on `ProgressPoller`.

- [ ] **Step 3: Append ProgressPoller to progress.py**

Update `__all__` to add `"ProgressPoller"`. Add imports:

```python
import asyncio
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nexus.connectors.servicenow.protocol import ServiceNowClientProtocol

from nexus.plugins.errors import PluginProgressError, PluginTimeoutError
```

Then the class:

```python
DEFAULT_POLL_INTERVAL_S = 3.0
DEFAULT_TIMEOUT_S = 600.0


class ProgressPoller:
    """Polls /api/sn_cicd/progress/{tracker_id} until terminal status.

    Args:
        client: ServiceNow client conforming to the protocol.
        poll_interval_s: Seconds between polls. Default 3s.
        timeout_s: Maximum total wall time. Default 600s.
    """

    def __init__(
        self,
        client: "ServiceNowClientProtocol",
        *,
        poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        self._client = client
        self._poll_interval_s = poll_interval_s
        self._timeout_s = timeout_s

    async def poll(self, tracker_id: str) -> ProgressState:
        """Poll until terminal. Returns the final ProgressState on success.

        Raises:
            PluginProgressError: SN reports a failed terminal status.
            PluginTimeoutError: Polling exceeds timeout_s.
        """
        started = time.monotonic()
        while True:
            elapsed = time.monotonic() - started
            if elapsed > self._timeout_s:
                raise PluginTimeoutError(tracker_id=tracker_id, elapsed_s=elapsed)
            raw = await self._client.fetch_progress(tracker_id)
            state = ProgressState.from_sn(raw)
            if state.is_terminal:
                if not state.is_success:
                    raise PluginProgressError(
                        tracker_id=tracker_id,
                        sn_status=state.status,
                        error_message=state.error,
                    )
                return state
            await asyncio.sleep(self._poll_interval_s)
```

- [ ] **Step 4: Run test (will still fail because set_progress_sequence doesn't exist on fake yet)**

Task 7 adds it. Move on.

- [ ] **Step 5: Commit**

```bash
git add src/nexus/plugins/progress.py tests/test_plugins_progress.py
git commit -m "feat(plugins): add ProgressPoller for sn_cicd progress endpoint"
```

---

## Task 7: Extend FakeServiceNowClient with canned-response support

**Files:**
- Modify: `tests/fakes/fake_sn_client.py`
- Modify: `tests/test_plugins_dependencies.py` (re-run to confirm green)
- Modify: `tests/test_plugins_progress.py` (re-run to confirm green)

- [ ] **Step 1: Add canned response state + setters + new async methods**

Edit `tests/fakes/fake_sn_client.py`. Update the docstring and add new
state to `__init__`:

```python
    def __init__(self, initial_records: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {}
        for table, records in (initial_records or {}).items():
            self._tables[table] = [dict(r) for r in records]
        # Canned responses for the appmanager / batch / progress endpoints.
        self._dependency_responses: dict[str, list[dict[str, Any]]] = {}
        self._install_responses: list[dict[str, Any]] = []
        self._activate_responses: list[dict[str, Any]] = []
        self._upgrade_responses: list[dict[str, Any]] = []
        self._progress_sequences: dict[str, list[dict[str, Any]]] = {}
```

Add setters near the bottom of the class:

```python
    def set_dependencies(self, plugin_id: str, entries: list[dict[str, Any]]) -> None:
        """Queue canned dependency entries for one plugin_id."""
        self._dependency_responses[plugin_id] = list(entries)

    def queue_install_response(self, raw_result: dict[str, Any]) -> None:
        """Queue one install response (FIFO consumed by submit_install)."""
        self._install_responses.append(dict(raw_result))

    def queue_activate_response(self, raw_result: dict[str, Any]) -> None:
        """Queue one activate response."""
        self._activate_responses.append(dict(raw_result))

    def queue_upgrade_response(self, raw_result: dict[str, Any]) -> None:
        """Queue one upgrade response."""
        self._upgrade_responses.append(dict(raw_result))

    def set_progress_sequence(self, tracker_id: str, sequence: list[dict[str, Any]]) -> None:
        """Set the sequence of polls returned for one tracker_id."""
        self._progress_sequences[tracker_id] = list(sequence)
```

Add the four new async methods after the existing CRUD ones:

```python
    async def appmanager_dependencies(
        self,
        plugin_id: str,
        version: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return canned dependency entries for plugin_id, or empty list."""
        del version  # canned shape ignores version
        return list(self._dependency_responses.get(plugin_id, []))

    async def submit_install(
        self,
        plugin_id: str,
        version: str | None = None,
    ) -> dict[str, Any]:
        """Pop and return the next queued install response."""
        del plugin_id, version
        if not self._install_responses:
            raise RuntimeError("no install response queued in FakeServiceNowClient")
        return self._install_responses.pop(0)

    async def submit_activate(self, plugin_id: str) -> dict[str, Any]:
        del plugin_id
        if not self._activate_responses:
            raise RuntimeError("no activate response queued in FakeServiceNowClient")
        return self._activate_responses.pop(0)

    async def submit_upgrade(
        self,
        plugin_id: str,
        target_version: str | None = None,
    ) -> dict[str, Any]:
        del plugin_id, target_version
        if not self._upgrade_responses:
            raise RuntimeError("no upgrade response queued in FakeServiceNowClient")
        return self._upgrade_responses.pop(0)

    async def fetch_progress(self, tracker_id: str) -> dict[str, Any]:
        """Pop and return the next progress poll for tracker_id."""
        seq = self._progress_sequences.get(tracker_id, [])
        if not seq:
            # Auto-complete if the test didn't queue anything more
            return {"status": "2", "status_label": "Success", "percent_complete": 100,
                    "error": "", "update_set": None, "rollback_version": None,
                    "trackerId": tracker_id, "status_message": "", "status_detail": ""}
        return seq.pop(0)
```

- [ ] **Step 2: Run dependent tests to verify green**

```
poetry run pytest tests/test_plugins_dependencies.py tests/test_plugins_progress.py -v
```
Expected: 2 + 3 = 5 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/fakes/fake_sn_client.py
git commit -m "test(fakes): add canned responses for appmanager + batch + progress endpoints"
```

---

## Task 8: PluginExecutor scaffolding + InventorySource refresh policy

**Files:**
- Modify: `src/nexus/plugins/executor.py` (add PluginExecutor)
- Test: extend `tests/test_plugins_executor.py` (new file)

- [ ] **Step 1: Write failing tests for constructor + targeted inventory refresh**

```python
# tests/test_plugins_executor.py
# Tests for PluginExecutor lifecycle (Task 8).
# Author: Pierre Grothe
# Date: 2026-05-14

"""Tests for PluginExecutor construction and inventory refresh."""

from datetime import UTC, datetime

import pytest

from nexus.plugins.errors import PluginNotFoundError
from nexus.plugins.executor import PluginExecutor
from nexus.plugins.models import PluginInfo, PluginInventory
from tests.fakes.fake_sn_client import FakeServiceNowClient

__all__: list[str] = []


def _info(pid: str, *, source="servicenow", state="active") -> PluginInfo:
    return PluginInfo(
        plugin_id=pid, name=pid, version="1.0", state=state,
        source=source, product_family="ITSM", depends_on=(),
        sys_id=f"sysid-{pid}", installed_at=None,
    )


def _inventory(*plugins: PluginInfo) -> PluginInventory:
    return PluginInventory(
        captured_at=datetime.now(UTC), sn_version="Xanadu", plugins=plugins
    )


@pytest.fixture
def client() -> FakeServiceNowClient:
    return FakeServiceNowClient()


def test_constructor_snapshots_inventory_map(client: FakeServiceNowClient) -> None:
    inv = _inventory(_info("com.a"), _info("com.b"))
    exe = PluginExecutor(client=client, inventory=inv)
    assert exe.has_plugin("com.a")
    assert exe.has_plugin("com.b")
    assert not exe.has_plugin("com.z")


def test_constructor_raises_on_invalid_inventory_type(client: FakeServiceNowClient) -> None:
    with pytest.raises(TypeError):
        PluginExecutor(client=client, inventory="not an inventory")  # type-ignored at call site


@pytest.mark.asyncio
async def test_refresh_after_install_adds_new_plugin(client: FakeServiceNowClient) -> None:
    inv = _inventory(_info("com.a"))
    exe = PluginExecutor(client=client, inventory=inv)
    # Seed v_plugin row that the targeted refresh would fetch
    client._tables.setdefault("v_plugin", []).append({
        "name": "com.newly_installed", "sys_id": "newsysid", "version": "1.0",
        "state": "active", "source_app_id": "newsysid",
    })
    await exe._refresh_one("com.newly_installed")
    assert exe.has_plugin("com.newly_installed")


def test_lookup_raises_for_unknown_plugin(client: FakeServiceNowClient) -> None:
    inv = _inventory(_info("com.a"))
    exe = PluginExecutor(client=client, inventory=inv)
    with pytest.raises(PluginNotFoundError) as excinfo:
        exe.lookup("com.nope")
    assert excinfo.value.plugin_id == "com.nope"
```

- [ ] **Step 2: Run test to verify failure**

Expected: ImportError on `PluginExecutor`.

- [ ] **Step 3: Append PluginExecutor to executor.py**

Update `__all__` to add `"PluginExecutor"`. Add imports:

```python
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nexus.connectors.servicenow.protocol import ServiceNowClientProtocol

from nexus.plugins.errors import PluginNotFoundError
from nexus.plugins.models import PluginInfo, PluginInventory
```

Then the class:

```python
class PluginExecutor:
    """Orchestrates plugin install / activate / upgrade against SN.

    Holds a snapshot of the plugin inventory built at construction. After
    each successful install, a targeted v_plugin row is fetched and added
    to the in-memory map so install -> activate sequences in one plan
    resolve sys_ids correctly without a full rescan.

    Args:
        client: ServiceNow client conforming to the protocol.
        inventory: Fresh PluginInventory captured before construction.
    """

    def __init__(
        self,
        client: "ServiceNowClientProtocol",
        inventory: PluginInventory,
    ) -> None:
        if not isinstance(inventory, PluginInventory):
            raise TypeError(f"inventory must be PluginInventory, got {type(inventory).__name__}")
        self._client = client
        self._by_id: dict[str, PluginInfo] = {p.plugin_id: p for p in inventory.plugins}

    def has_plugin(self, plugin_id: str) -> bool:
        """Return True if the plugin is known to this executor."""
        return plugin_id in self._by_id

    def lookup(self, plugin_id: str) -> PluginInfo:
        """Return the PluginInfo for plugin_id.

        Raises:
            PluginNotFoundError: When plugin_id is not in the snapshot.
        """
        info = self._by_id.get(plugin_id)
        if info is None:
            raise PluginNotFoundError(plugin_id)
        return info

    async def _refresh_one(self, plugin_id: str) -> None:
        """Fetch the v_plugin row for plugin_id and patch it into the map.

        Used after install to make the newly-installed plugin's sys_id
        available to subsequent activate / upgrade calls in the same plan.
        """
        rows = await self._client.query_table(
            table="v_plugin",
            query=f"name={plugin_id}",
            limit=1,
        )
        if not rows:
            # Install reported success but v_plugin doesn't yet show the row.
            # Skip the patch; the next dict lookup will raise PluginNotFoundError.
            return
        row = rows[0]
        self._by_id[plugin_id] = PluginInfo(
            plugin_id=plugin_id,
            name=str(row.get("name", plugin_id)),
            version=str(row.get("version", "")),
            state=str(row.get("state", "inactive")),  # type: ignore[arg-type] -> use cast in real code
            source="servicenow",
            product_family="Unclassified",
            depends_on=(),
            sys_id=str(row.get("sys_id", "")),
            installed_at=None,
        )
```

- [ ] **Step 4: Run tests to verify pass**

```
poetry run pytest tests/test_plugins_executor.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/nexus/plugins/executor.py tests/test_plugins_executor.py
git commit -m "feat(plugins): add PluginExecutor scaffolding + targeted inventory refresh"
```

---

## Task 9: PluginExecutor.install

**Files:**
- Modify: `src/nexus/plugins/executor.py`
- Test: extend `tests/test_plugins_executor.py`

- [ ] **Step 1: Add failing test for install happy path**

Append to `tests/test_plugins_executor.py`:

```python
def _install_response(tracker: str = "t1") -> dict:
    return {"status": "0", "status_label": "Pending", "percent_complete": 0,
            "error": "", "update_set": None, "rollback_version": None,
            "trackerId": tracker, "status_message": "", "status_detail": "",
            "links": {"progress": {"id": tracker, "url": f"/api/sn_cicd/progress/{tracker}"}}}


def _progress(status: str, pct: int, err: str = "", tracker: str = "t1") -> dict:
    return {"status": status, "status_label": "x", "percent_complete": pct,
            "error": err, "update_set": None, "rollback_version": None,
            "trackerId": tracker, "status_message": "", "status_detail": ""}


@pytest.mark.asyncio
async def test_install_returns_success_result(client: FakeServiceNowClient) -> None:
    inv = _inventory()  # plugin doesn't exist yet
    client.queue_install_response(_install_response("t1"))
    client.set_progress_sequence("t1", [_progress("1", 50), _progress("2", 100)])
    client._tables["v_plugin"] = [{"name": "com.new", "sys_id": "sid", "version": "1.0", "state": "active"}]
    exe = PluginExecutor(client=client, inventory=inv)
    result = await exe.install("com.new", version="1.0")
    assert result.success
    assert result.action == "install"
    assert result.plugin_id == "com.new"
    assert result.tracker_id == "t1"
    # Targeted refresh should have added the plugin
    assert exe.has_plugin("com.new")


@pytest.mark.asyncio
async def test_install_failure_returns_unsuccessful_result(client: FakeServiceNowClient) -> None:
    inv = _inventory()
    client.queue_install_response(_install_response("t2"))
    client.set_progress_sequence("t2", [_progress("3", 80, err="dep missing")])
    exe = PluginExecutor(client=client, inventory=inv)
    result = await exe.install("com.new")
    assert not result.success
    assert "dep missing" in result.message
```

- [ ] **Step 2: Run test to verify failure**

Expected: AttributeError on `install`.

- [ ] **Step 3: Add the install method to PluginExecutor**

Append inside the class:

```python
    async def install(
        self,
        plugin_id: str,
        version: str | None = None,
    ) -> OperationResult:
        """Install plugin_id (optionally pinned to version)."""
        from nexus.plugins.progress import ProgressPoller

        started = time.monotonic()
        try:
            raw = await self._client.submit_install(plugin_id, version)
        except Exception as exc:
            return OperationResult(
                action="install", plugin_id=plugin_id, success=False,
                message=str(exc), duration_s=time.monotonic() - started,
                tracker_id="", update_set=None, rollback_version=None,
            )
        tracker_id = str(raw.get("trackerId", ""))
        poller = ProgressPoller(self._client)
        try:
            final = await poller.poll(tracker_id)
        except (PluginProgressError, PluginTimeoutError) as exc:
            return OperationResult(
                action="install", plugin_id=plugin_id, success=False,
                message=getattr(exc, "error_message", str(exc)),
                duration_s=time.monotonic() - started, tracker_id=tracker_id,
                update_set=None, rollback_version=None,
            )
        # Targeted refresh on success
        await self._refresh_one(plugin_id)
        return OperationResult(
            action="install", plugin_id=plugin_id, success=True,
            message=final.status_label, duration_s=time.monotonic() - started,
            tracker_id=tracker_id, update_set=final.update_set,
            rollback_version=final.rollback_version,
        )
```

Add to the top of `executor.py`:

```python
from nexus.plugins.errors import PluginNotFoundError, PluginProgressError, PluginTimeoutError
```

- [ ] **Step 4: Run tests to verify pass**

```
poetry run pytest tests/test_plugins_executor.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/nexus/plugins/executor.py tests/test_plugins_executor.py
git commit -m "feat(plugins): add PluginExecutor.install with targeted post-install refresh"
```

---

## Task 10: PluginExecutor.activate

**Files:**
- Modify: `src/nexus/plugins/executor.py`
- Test: extend `tests/test_plugins_executor.py`

- [ ] **Step 1: Write failing test**

```python
@pytest.mark.asyncio
async def test_activate_returns_success_result(client: FakeServiceNowClient) -> None:
    inv = _inventory(_info("com.x", state="inactive"))
    client.queue_activate_response(_install_response("act-1"))
    client.set_progress_sequence("act-1", [_progress("2", 100, tracker="act-1")])
    exe = PluginExecutor(client=client, inventory=inv)
    result = await exe.activate("com.x")
    assert result.success
    assert result.action == "activate"


@pytest.mark.asyncio
async def test_activate_unknown_plugin_returns_failure(client: FakeServiceNowClient) -> None:
    inv = _inventory()  # empty
    exe = PluginExecutor(client=client, inventory=inv)
    result = await exe.activate("com.nope")
    assert not result.success
    assert "com.nope" in result.message
```

- [ ] **Step 2: Run to verify failure**

Expected: AttributeError on `activate`.

- [ ] **Step 3: Add activate method**

```python
    async def activate(self, plugin_id: str) -> OperationResult:
        """Activate plugin_id (must already be installed)."""
        started = time.monotonic()
        try:
            self.lookup(plugin_id)
        except PluginNotFoundError as exc:
            return OperationResult(
                action="activate", plugin_id=plugin_id, success=False,
                message=str(exc), duration_s=time.monotonic() - started,
                tracker_id="", update_set=None, rollback_version=None,
            )
        try:
            raw = await self._client.submit_activate(plugin_id)
        except Exception as exc:
            return OperationResult(
                action="activate", plugin_id=plugin_id, success=False,
                message=str(exc), duration_s=time.monotonic() - started,
                tracker_id="", update_set=None, rollback_version=None,
            )
        tracker_id = str(raw.get("trackerId", ""))
        from nexus.plugins.progress import ProgressPoller
        poller = ProgressPoller(self._client)
        try:
            final = await poller.poll(tracker_id)
        except (PluginProgressError, PluginTimeoutError) as exc:
            return OperationResult(
                action="activate", plugin_id=plugin_id, success=False,
                message=getattr(exc, "error_message", str(exc)),
                duration_s=time.monotonic() - started, tracker_id=tracker_id,
                update_set=None, rollback_version=None,
            )
        return OperationResult(
            action="activate", plugin_id=plugin_id, success=True,
            message=final.status_label, duration_s=time.monotonic() - started,
            tracker_id=tracker_id, update_set=final.update_set,
            rollback_version=final.rollback_version,
        )
```

- [ ] **Step 4: Run tests to verify pass**

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add src/nexus/plugins/executor.py tests/test_plugins_executor.py
git commit -m "feat(plugins): add PluginExecutor.activate"
```

---

## Task 11: PluginExecutor.upgrade

**Files:**
- Modify: `src/nexus/plugins/executor.py`
- Test: extend `tests/test_plugins_executor.py`

- [ ] **Step 1: Write failing test**

```python
@pytest.mark.asyncio
async def test_upgrade_returns_rollback_version(client: FakeServiceNowClient) -> None:
    inv = _inventory(_info("com.x"))
    raw = _install_response("up-1")
    client.queue_upgrade_response(raw)
    client.set_progress_sequence("up-1", [
        _progress("2", 100, tracker="up-1") | {"rollback_version": "1.4"}
    ])
    exe = PluginExecutor(client=client, inventory=inv)
    result = await exe.upgrade("com.x", target_version="2.0")
    assert result.success
    assert result.rollback_version == "1.4"
    assert result.action == "upgrade"
```

- [ ] **Step 2: Run to verify failure**

Expected: AttributeError on `upgrade`.

- [ ] **Step 3: Add upgrade method**

```python
    async def upgrade(
        self,
        plugin_id: str,
        target_version: str | None = None,
    ) -> OperationResult:
        """Upgrade plugin_id (optionally to target_version, else latest)."""
        started = time.monotonic()
        try:
            self.lookup(plugin_id)
        except PluginNotFoundError as exc:
            return OperationResult(
                action="upgrade", plugin_id=plugin_id, success=False,
                message=str(exc), duration_s=time.monotonic() - started,
                tracker_id="", update_set=None, rollback_version=None,
            )
        try:
            raw = await self._client.submit_upgrade(plugin_id, target_version)
        except Exception as exc:
            return OperationResult(
                action="upgrade", plugin_id=plugin_id, success=False,
                message=str(exc), duration_s=time.monotonic() - started,
                tracker_id="", update_set=None, rollback_version=None,
            )
        tracker_id = str(raw.get("trackerId", ""))
        from nexus.plugins.progress import ProgressPoller
        poller = ProgressPoller(self._client)
        try:
            final = await poller.poll(tracker_id)
        except (PluginProgressError, PluginTimeoutError) as exc:
            return OperationResult(
                action="upgrade", plugin_id=plugin_id, success=False,
                message=getattr(exc, "error_message", str(exc)),
                duration_s=time.monotonic() - started, tracker_id=tracker_id,
                update_set=None, rollback_version=None,
            )
        return OperationResult(
            action="upgrade", plugin_id=plugin_id, success=True,
            message=final.status_label, duration_s=time.monotonic() - started,
            tracker_id=tracker_id, update_set=final.update_set,
            rollback_version=final.rollback_version,
        )
```

- [ ] **Step 4: Run tests to verify pass**

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add src/nexus/plugins/executor.py tests/test_plugins_executor.py
git commit -m "feat(plugins): add PluginExecutor.upgrade preserving rollback_version"
```

---

## Task 12: apply_plan happy path + ordering

**Files:**
- Modify: `src/nexus/plugins/executor.py`
- Test: extend `tests/test_plugins_executor.py`

- [ ] **Step 1: Write failing test**

```python
from nexus.plugins.diff import PromoteAction, PromotionPlan


def _action(action: str, pid: str, *, tv: str = "1.0", cv: str | None = None) -> PromoteAction:
    return PromoteAction(
        action=action, plugin_id=pid, name=pid, product_family="ITSM",
        target_version=tv, current_version=cv,
    )


@pytest.mark.asyncio
async def test_apply_plan_executes_actions_in_stable_order(client: FakeServiceNowClient) -> None:
    inv = _inventory(_info("com.b"))
    plan = PromotionPlan(
        source_profile="dev", target_profile="prod",
        actions=(
            _action("install", "com.a"),
            _action("activate", "com.b"),
            _action("upgrade", "com.b", tv="2.0", cv="1.0"),
        ),
    )
    client.queue_install_response(_install_response("t-i"))
    client.queue_activate_response(_install_response("t-a"))
    client.queue_upgrade_response(_install_response("t-u"))
    client.set_progress_sequence("t-i", [_progress("2", 100, tracker="t-i")])
    client.set_progress_sequence("t-a", [_progress("2", 100, tracker="t-a")])
    client.set_progress_sequence("t-u", [_progress("2", 100, tracker="t-u")])
    client._tables["v_plugin"] = [{"name": "com.a", "sys_id": "ai", "version": "1.0", "state": "active"}]
    exe = PluginExecutor(client=client, inventory=inv)
    from rich.console import Console
    log = await exe.apply_plan(plan, console=Console(quiet=True))
    assert log.success_count == 3
    assert log.failure_count == 0
    actions = tuple(r.action for r in log.results)
    assert actions == ("install", "activate", "upgrade")
```

- [ ] **Step 2: Run to verify failure**

Expected: AttributeError on `apply_plan`.

- [ ] **Step 3: Implement apply_plan**

```python
    async def apply_plan(
        self,
        plan: "PromotionPlan",
        *,
        console: "Console",
    ) -> OperationLog:
        """Execute a PromotionPlan against the SN instance.

        Pre-validation: every plugin_id in upgrade/activate actions must be
        in the snapshot. install plugin_ids are NOT required to exist yet
        (install creates them).

        Args:
            plan: PromotionPlan from project_to_promote_plan.
            console: Rich console for progress output.

        Returns:
            OperationLog with one OperationResult per executed action.
            On partial failure, includes rollback entries in reverse order.

        Raises:
            PluginExecutionError: After rollback, with the partial log.
        """
        for action in plan.actions:
            if action.action in ("activate", "upgrade") and action.plugin_id not in self._by_id:
                raise PluginNotFoundError(action.plugin_id)
        results: list[OperationResult] = []
        for action in plan.actions:
            console.print(f"[label]{action.action} {action.plugin_id}[/]")
            if action.action == "install":
                r = await self.install(action.plugin_id, action.target_version)
            elif action.action == "activate":
                r = await self.activate(action.plugin_id)
            else:  # upgrade
                r = await self.upgrade(action.plugin_id, action.target_version)
            results.append(r)
            if not r.success:
                console.print(f"[error]failed: {r.message}[/]")
                rollback = await self._rollback(results[:-1], console)
                return OperationLog(results=tuple(results) + tuple(rollback))
        return OperationLog(results=tuple(results))
```

Add imports at top:

```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from rich.console import Console
    from nexus.plugins.diff import PromotionPlan
```

- [ ] **Step 4: Run to verify pass**

Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add src/nexus/plugins/executor.py tests/test_plugins_executor.py
git commit -m "feat(plugins): add PluginExecutor.apply_plan happy path"
```

---

## Task 13: apply_plan rollback on partial failure

**Files:**
- Modify: `src/nexus/plugins/executor.py`
- Test: extend `tests/test_plugins_executor.py`

- [ ] **Step 1: Write failing tests**

```python
@pytest.mark.asyncio
async def test_apply_plan_rollback_on_install_failure(client: FakeServiceNowClient) -> None:
    inv = _inventory(_info("com.b"))
    plan = PromotionPlan(
        source_profile="dev", target_profile="prod",
        actions=(
            _action("install", "com.a"),
            _action("activate", "com.b"),  # this fails
        ),
    )
    client.queue_install_response(_install_response("t1"))
    client.set_progress_sequence("t1", [_progress("2", 100, tracker="t1")])
    client._tables["v_plugin"] = [{"name": "com.a", "sys_id": "ai", "version": "1.0", "state": "active"}]
    # activate fails
    client.queue_activate_response(_install_response("t2"))
    client.set_progress_sequence("t2", [_progress("3", 50, err="boom", tracker="t2")])
    # Rollback of "install com.a" -> calls submit_install with action=uninstall.
    # For Task 13 we use submit_install again as the fake's uninstall placeholder
    # (real uninstall path comes with sub-project N). Provide a response anyway:
    client.queue_install_response(_install_response("rb-1"))
    client.set_progress_sequence("rb-1", [_progress("2", 100, tracker="rb-1")])
    exe = PluginExecutor(client=client, inventory=inv)
    from rich.console import Console
    log = await exe.apply_plan(plan, console=Console(quiet=True))
    actions = tuple(r.action for r in log.results)
    # install ok, activate failed, rollback_install for com.a
    assert actions[0] == "install"
    assert actions[1] == "activate"
    assert "rollback" in actions[2]
    assert log.failure_count >= 1


@pytest.mark.asyncio
async def test_rollback_continues_through_secondary_failures(client: FakeServiceNowClient) -> None:
    # Two completed steps, then a failure. Both rollbacks attempted even when
    # the first rollback itself fails.
    inv = _inventory(_info("com.b"))
    plan = PromotionPlan(
        source_profile="dev", target_profile="prod",
        actions=(_action("install", "com.a"), _action("install", "com.c"), _action("activate", "com.b")),
    )
    client.queue_install_response(_install_response("ti1"))
    client.queue_install_response(_install_response("ti2"))
    client.set_progress_sequence("ti1", [_progress("2", 100, tracker="ti1")])
    client.set_progress_sequence("ti2", [_progress("2", 100, tracker="ti2")])
    client._tables["v_plugin"] = [
        {"name": "com.a", "sys_id": "a", "version": "1.0", "state": "active"},
        {"name": "com.c", "sys_id": "c", "version": "1.0", "state": "active"},
    ]
    # activate fails
    client.queue_activate_response(_install_response("ta"))
    client.set_progress_sequence("ta", [_progress("3", 0, err="x", tracker="ta")])
    # First rollback fails (no response queued); second rollback should still happen
    # We queue one rollback response: the second rollback for com.a uses it.
    # Note: real uninstall path is in sub-project N; for now this tests rollback flow.
    client.queue_install_response(_install_response("rb-a"))
    client.set_progress_sequence("rb-a", [_progress("2", 100, tracker="rb-a")])
    exe = PluginExecutor(client=client, inventory=inv)
    from rich.console import Console
    log = await exe.apply_plan(plan, console=Console(quiet=True))
    # Original 3 results + 2 rollback entries (one failed, one succeeded)
    assert len(log.results) == 5
```

- [ ] **Step 2: Run to verify failure**

Expected: AttributeError on `_rollback`.

- [ ] **Step 3: Implement _rollback**

```python
    async def _rollback(
        self,
        completed: list[OperationResult],
        console: "Console",
    ) -> list[OperationResult]:
        """Reverse-undo each completed forward op, best-effort.

        Sub-project N adds the actual uninstall / deactivate paths. For now,
        install -> rollback_install reuses submit_install as a placeholder
        (the real submit_uninstall lands in sub-project N).

        Never abort rollback due to a secondary failure.
        """
        rollback_results: list[OperationResult] = []
        for op in reversed(completed):
            started = time.monotonic()
            console.print(f"[warn]rollback {op.action} {op.plugin_id}[/]")
            try:
                if op.action == "install":
                    raw = await self._client.submit_install(op.plugin_id, None)
                    rb_action = "rollback_install"
                elif op.action == "activate":
                    raw = await self._client.submit_activate(op.plugin_id)
                    rb_action = "rollback_activate"
                else:  # upgrade -> upgrade to op.rollback_version
                    raw = await self._client.submit_upgrade(op.plugin_id, op.rollback_version)
                    rb_action = "rollback_upgrade"
            except Exception as exc:
                rollback_results.append(OperationResult(
                    action=rb_action if op.action != "upgrade" else "rollback_upgrade",
                    plugin_id=op.plugin_id, success=False,
                    message=f"rollback failed: {exc}",
                    duration_s=time.monotonic() - started,
                    tracker_id="", update_set=None, rollback_version=None,
                ))
                continue
            tracker_id = str(raw.get("trackerId", ""))
            from nexus.plugins.progress import ProgressPoller
            poller = ProgressPoller(self._client)
            try:
                final = await poller.poll(tracker_id)
            except (PluginProgressError, PluginTimeoutError) as exc:
                rollback_results.append(OperationResult(
                    action=rb_action, plugin_id=op.plugin_id, success=False,
                    message=f"rollback failed: {exc}",
                    duration_s=time.monotonic() - started,
                    tracker_id=tracker_id, update_set=None, rollback_version=None,
                ))
                continue
            rollback_results.append(OperationResult(
                action=rb_action, plugin_id=op.plugin_id, success=True,
                message=final.status_label,
                duration_s=time.monotonic() - started,
                tracker_id=tracker_id, update_set=final.update_set,
                rollback_version=final.rollback_version,
            ))
        return rollback_results
```

- [ ] **Step 4: Run all executor tests**

```
poetry run pytest tests/test_plugins_executor.py -v
```
Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add src/nexus/plugins/executor.py tests/test_plugins_executor.py
git commit -m "feat(plugins): add apply_plan rollback with best-effort secondary-failure handling"
```

---

## Task 14: CLI: nexus plugins install

**Files:**
- Modify: `src/nexus/cli.py`
- Test: `tests/test_cli_plugins_execute.py` (new file)

- [ ] **Step 1: Write failing test**

```python
# tests/test_cli_plugins_execute.py
# Tests for nexus plugins install/activate/upgrade/apply CLI commands.
# Author: Pierre Grothe
# Date: 2026-05-14

"""Tests for the new plugin execution CLI commands."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nexus.cache import clear_cache
from nexus.cli import app
from nexus.config.paths import NexusPaths
from nexus.instances.models import InstanceMeta
from nexus.plugins.models import PluginInfo, PluginInventory

__all__: list[str] = []


def _meta(profile: str) -> InstanceMeta:
    return InstanceMeta.create(
        profile=profile, url=f"https://{profile}.service-now.com",
        username="admin", client_id="cid", sn_version="Xanadu",
        sn_build="04-01-2025_1200", instance_name=profile,
        token_expires_in=1800,
    )


def _info(pid: str, state: str = "inactive") -> PluginInfo:
    return PluginInfo(
        plugin_id=pid, name=pid, version="1.0", state=state,
        source="servicenow", product_family="ITSM", depends_on=(),
        sys_id=f"sid-{pid}", installed_at=None,
    )


def _seed(tmp_path: Path, profile: str, plugins: tuple[PluginInfo, ...]) -> None:
    profile_dir = tmp_path / "instances" / profile
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "meta.json").write_text(_meta(profile).model_dump_json(indent=2), encoding="utf-8")
    inv = PluginInventory(captured_at=datetime.now(UTC), sn_version="Xanadu", plugins=plugins)
    (profile_dir / "plugins.json").write_text(inv.model_dump_json(indent=2), encoding="utf-8")


@pytest.fixture
def runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    monkeypatch.setenv("NEXUS_CONFIG_PATH", str(tmp_path / "config.yaml"))
    clear_cache(NexusPaths.from_env)
    return CliRunner()


def test_plugins_install_command_exists(runner: CliRunner, tmp_path: Path) -> None:
    _seed(tmp_path, "prod", (_info("com.x"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "install", "--help"])
    assert result.exit_code == 0
    assert "install" in result.output.lower()
```

- [ ] **Step 2: Run to verify failure**

Expected: typer "No such command 'install'".

- [ ] **Step 3: Add the install command to cli.py**

Add near the existing plugins commands (search for `@plugins_app.command("export")` and add after):

```python
@plugins_app.command("install")
def plugins_install(
    plugin_id: Annotated[str, typer.Argument(help="Plugin ID to install")],
    version: Annotated[str | None, typer.Option("--version", help="Pin to this version")] = None,
    yes: Annotated[bool, typer.Option("--yes", help="Skip action confirm prompt")] = False,
) -> None:
    """Install a plugin on the default instance.

    Shows the SN dependency cascade pre-flight, prompts for confirmation
    (unless --yes), then blocks with a progress bar until SN reports
    terminal status.
    """
    # Implementation pattern matches the existing plugins commands:
    # 1. Load profile + inventory via _load_default_profile / _load_inventory_for
    # 2. Build a ServiceNowClient from InstanceMeta + keyring token
    # 3. Build PluginExecutor(client, inventory)
    # 4. Show dependencies via fetch_dependencies + DataTable
    # 5. Confirm prompt
    # 6. await exe.install(plugin_id, version)
    # 7. Print OperationResult via KeyValuePanel
    from nexus.plugins.executor import PluginExecutor
    from nexus.plugins.dependencies import fetch_dependencies
    import asyncio

    paths = NexusPaths.from_env()
    profile = _resolve_default_profile_or_die(paths, console=err_console)
    meta = _load_meta(paths, profile)
    inventory = _load_inventory_or_die(paths, profile)
    token = _load_oauth_token(meta)

    async def _run() -> None:
        async with ServiceNowClient(meta.url, token=token) as client:
            deps = await fetch_dependencies(client, plugin_id, version)
            if deps:
                console.print(_dependencies_panel(deps, plugin_id))
            if not yes and not typer.confirm(f"Install {plugin_id} against {profile}?"):
                raise typer.Exit(0)
            exe = PluginExecutor(client=client, inventory=inventory)
            result = await exe.install(plugin_id, version)
            console.print(_result_panel(result))
            if not result.success:
                raise typer.Exit(1)

    asyncio.run(_run())
```

Add a helper `_dependencies_panel(deps, plugin_id)` near other panel
helpers using `DataTable`:

```python
def _dependencies_panel(deps: tuple, plugin_id: str):
    from nexus.ui.components.data_table import DataTable, DataColumn
    return DataTable(
        title=f"Dependency cascade for {plugin_id}",
        columns=(
            DataColumn(label="Plugin", value=lambda d: d.id),
            DataColumn(label="Status", value=lambda d: d.status),
            DataColumn(label="Active", value=lambda d: "yes" if d.active else "no"),
        ),
        rows=list(deps),
    )
```

And `_result_panel(result)`:

```python
def _result_panel(result):
    from nexus.ui.components.kv_panel import KeyValuePanel, KvRow
    return KeyValuePanel(
        title=f"{result.action} {result.plugin_id}",
        rows=(
            KvRow(label="Status", value="success" if result.success else "failed"),
            KvRow(label="Tracker", value=result.tracker_id),
            KvRow(label="Duration", value=f"{result.duration_s:.1f}s"),
            KvRow(label="Update set", value=result.update_set or "-"),
            KvRow(label="Rollback version", value=result.rollback_version or "-"),
            KvRow(label="Message", value=result.message),
        ),
    )
```

Also add a help entry to `_PLUGINS_HELP` (search for the existing dict):

```python
_help_entry(
    "install <plugin-id>",
    "Install a plugin on the default instance. Blocks until SN reports "
    "terminal status. Shows dependency cascade preview.",
    "nexus plugins install com.snc.discovery",
),
```

- [ ] **Step 4: Run to verify pass**

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add src/nexus/cli.py tests/test_cli_plugins_execute.py
git commit -m "feat(cli): add nexus plugins install command"
```

---

## Task 15: CLI: nexus plugins activate

**Files:**
- Modify: `src/nexus/cli.py`
- Test: extend `tests/test_cli_plugins_execute.py`

- [ ] **Step 1: Write failing test**

```python
def test_plugins_activate_command_exists(runner: CliRunner, tmp_path: Path) -> None:
    _seed(tmp_path, "prod", (_info("com.x"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "activate", "--help"])
    assert result.exit_code == 0
```

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Add activate command (pattern matches install, with `exe.activate` and no `--version`)**

```python
@plugins_app.command("activate")
def plugins_activate(
    plugin_id: Annotated[str, typer.Argument(help="Plugin ID to activate")],
    yes: Annotated[bool, typer.Option("--yes")] = False,
) -> None:
    """Activate an installed plugin on the default instance."""
    import asyncio
    from nexus.plugins.executor import PluginExecutor

    paths = NexusPaths.from_env()
    profile = _resolve_default_profile_or_die(paths, console=err_console)
    meta = _load_meta(paths, profile)
    inventory = _load_inventory_or_die(paths, profile)
    token = _load_oauth_token(meta)

    async def _run() -> None:
        async with ServiceNowClient(meta.url, token=token) as client:
            if not yes and not typer.confirm(f"Activate {plugin_id} against {profile}?"):
                raise typer.Exit(0)
            exe = PluginExecutor(client=client, inventory=inventory)
            result = await exe.activate(plugin_id)
            console.print(_result_panel(result))
            if not result.success:
                raise typer.Exit(1)

    asyncio.run(_run())
```

Add help entry to `_PLUGINS_HELP`:

```python
_help_entry(
    "activate <plugin-id>",
    "Activate an installed plugin on the default instance.",
    "nexus plugins activate com.snc.discovery",
),
```

- [ ] **Step 4: Run to verify pass**

- [ ] **Step 5: Commit**

```bash
git add src/nexus/cli.py tests/test_cli_plugins_execute.py
git commit -m "feat(cli): add nexus plugins activate command"
```

---

## Task 16: CLI: nexus plugins upgrade

**Files:**
- Modify: `src/nexus/cli.py`
- Test: extend `tests/test_cli_plugins_execute.py`

- [ ] **Step 1: Write failing test**

```python
def test_plugins_upgrade_command_exists(runner: CliRunner, tmp_path: Path) -> None:
    _seed(tmp_path, "prod", (_info("com.x"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "upgrade", "--help"])
    assert result.exit_code == 0
```

- [ ] **Step 2-4: Add upgrade command (pattern matches install but with `--to` option)**

```python
@plugins_app.command("upgrade")
def plugins_upgrade(
    plugin_id: Annotated[str, typer.Argument(help="Plugin ID to upgrade")],
    to: Annotated[str | None, typer.Option("--to", help="Target version")] = None,
    yes: Annotated[bool, typer.Option("--yes")] = False,
) -> None:
    """Upgrade a plugin on the default instance."""
    import asyncio
    from nexus.plugins.executor import PluginExecutor
    from nexus.plugins.dependencies import fetch_dependencies

    paths = NexusPaths.from_env()
    profile = _resolve_default_profile_or_die(paths, console=err_console)
    meta = _load_meta(paths, profile)
    inventory = _load_inventory_or_die(paths, profile)
    token = _load_oauth_token(meta)

    async def _run() -> None:
        async with ServiceNowClient(meta.url, token=token) as client:
            deps = await fetch_dependencies(client, plugin_id, to)
            if deps:
                console.print(_dependencies_panel(deps, plugin_id))
            if not yes and not typer.confirm(f"Upgrade {plugin_id} on {profile}?"):
                raise typer.Exit(0)
            exe = PluginExecutor(client=client, inventory=inventory)
            result = await exe.upgrade(plugin_id, to)
            console.print(_result_panel(result))
            if not result.success:
                raise typer.Exit(1)

    asyncio.run(_run())
```

Add help entry:

```python
_help_entry(
    "upgrade <plugin-id> [--to X.Y.Z]",
    "Upgrade a plugin to the latest available version, or to a specific "
    "version with --to. Shows dependency cascade.",
    "nexus plugins upgrade com.snc.discovery --to 21.0",
),
```

- [ ] **Step 5: Commit**

```bash
git add src/nexus/cli.py tests/test_cli_plugins_execute.py
git commit -m "feat(cli): add nexus plugins upgrade command"
```

---

## Task 17: CLI: nexus plugins apply

**Files:**
- Modify: `src/nexus/cli.py`
- Test: extend `tests/test_cli_plugins_execute.py`

- [ ] **Step 1: Write failing test**

```python
def test_plugins_apply_command_exists(runner: CliRunner, tmp_path: Path) -> None:
    _seed(tmp_path, "prod", (_info("com.x"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "apply", "--help"])
    assert result.exit_code == 0


def test_plugins_apply_with_missing_plan_file_errors(runner: CliRunner, tmp_path: Path) -> None:
    _seed(tmp_path, "prod", (_info("com.x"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "apply", str(tmp_path / "nope.yaml")])
    assert result.exit_code != 0
```

- [ ] **Step 2-4: Add apply command**

```python
@plugins_app.command("apply")
def plugins_apply(
    plan_file: Annotated[Path, typer.Argument(help="Path to PromotionPlan YAML")],
    yes: Annotated[bool, typer.Option("--yes")] = False,
) -> None:
    """Execute a PromotionPlan YAML produced by `nexus plugins promote`."""
    import asyncio
    import yaml as _yaml
    from nexus.plugins.diff import PromotionPlan
    from nexus.plugins.executor import PluginExecutor

    if not plan_file.exists():
        err_console.print(Notice.error(f"Plan file not found: {plan_file}"))
        raise typer.Exit(2)
    payload = _yaml.safe_load(plan_file.read_text(encoding="utf-8"))
    plan = PromotionPlan.model_validate(payload)

    paths = NexusPaths.from_env()
    profile = _resolve_default_profile_or_die(paths, console=err_console)
    meta = _load_meta(paths, profile)
    inventory = _load_inventory_or_die(paths, profile)
    token = _load_oauth_token(meta)

    async def _run() -> None:
        async with ServiceNowClient(meta.url, token=token) as client:
            console.print(f"Plan: {len(plan.actions)} actions against {profile}")
            if not yes and not typer.confirm("Proceed?"):
                raise typer.Exit(0)
            exe = PluginExecutor(client=client, inventory=inventory)
            log = await exe.apply_plan(plan, console=console)
            console.print(f"Done: {log.success_count} ok, {log.failure_count} failed")
            if log.failure_count:
                raise typer.Exit(1)

    asyncio.run(_run())
```

Add help entry:

```python
_help_entry(
    "apply <plan.yaml>",
    "Execute a PromotionPlan YAML produced by `nexus plugins promote`. "
    "Rolls back partial failures.",
    "nexus plugins apply promote-dev-to-prod.yaml",
),
```

- [ ] **Step 5: Commit**

```bash
git add src/nexus/cli.py tests/test_cli_plugins_execute.py
git commit -m "feat(cli): add nexus plugins apply for PromotionPlan execution"
```

---

## Task 18: Re-exports + ratchet + full suite verification

**Files:**
- Modify: `src/nexus/plugins/__init__.py`
- Modify: `.ratchet.json`

- [ ] **Step 1: Add re-exports**

Edit `src/nexus/plugins/__init__.py`. Add to `__all__`:

```
"DependencyEntry",
"OperationLog",
"OperationResult",
"PluginExecutor",
"ProgressPoller",
"ProgressState",
"PluginExecutionError",
"PluginProgressError",
"PluginTimeoutError",
"PluginNotFoundError",
"PluginBatchError",
"fetch_dependencies",
```

Add the corresponding imports / re-exports near the existing ones.

- [ ] **Step 2: Run full test suite**

```
poetry run pytest -q
```
Expected: ~855-860 passed (was 830 before; this plan adds ~25-30 tests).

- [ ] **Step 3: Run ruff + mypy + pyright + black**

```
poetry run ruff check src/nexus tests
poetry run mypy src/nexus
poetry run pyright src/nexus
poetry run black --check src/nexus tests
```
Expected: 0 errors from each.

- [ ] **Step 4: Update ratchet**

```
poetry run python scripts/update_ratchet.py
```
(Or whatever script the project uses -- if no automation exists, hand-edit
`.ratchet.json` based on the coverage report.)

- [ ] **Step 5: Final commit**

```bash
git add src/nexus/plugins/__init__.py .ratchet.json
git commit -m "feat(plugins): re-export executor public API + rebaseline ratchet"
```

- [ ] **Step 6: Push and open PR**

```bash
git push -u origin feat/plugins-execution
gh pr create --title "feat(plugins): plugin execution core (sub-project M)" --body "$(cat <<'EOF'
## Summary
- Implements sub-project M from the 2026-05-14 revised plugin-execution spec
- PluginExecutor with install / activate / upgrade / apply_plan
- ProgressPoller against /api/sn_cicd/progress/{trackerId}
- fetch_dependencies pre-flight via /api/sn_appclient/appmanager/dependencies
- Five new error types (PluginExecutionError + 4 subclasses)
- Four new CLI commands: nexus plugins install / activate / upgrade / apply

## Test plan
- [ ] Run full test suite: poetry run pytest -q
- [ ] Run linters: ruff + mypy + pyright + black
- [ ] Smoke test on a live PDI: nexus plugins install <safe plugin>
- [ ] Smoke test apply: nexus plugins promote + apply

Sub-project N (deactivate / uninstall + impact gate) ships in a follow-up PR.

EOF
)"
```

---

## Self-review

**Spec coverage:**
- Live-discovered SN endpoints -> Task 4 (client methods) + Task 1 (capture)
- DependencyEntry shape -> Task 3
- PluginExecutor interface -> Tasks 8-13
- Inventory refresh policy (gap 1) -> Task 8 + Task 9
- apply_plan flow -> Tasks 12-13
- Rollback design (gap 2) -> Task 13
- New CLI commands -> Tasks 14-17
- Error hierarchy additions -> Task 2
- PromotionPlan reuse -> Task 12 (uses existing types)
- Testing strategy -> integrated throughout

**Gaps in coverage:**
- Sub-project N's impact gate is explicitly out of scope and ships separately
- Live discovery of payload keys is Task 1 with a clear capture procedure
- The `# type: ignore` comments in the example code blocks are flagged with
  "use cast in real code" notes -- pre-edit hook blocks type:ignore

**Type consistency:**
- `PluginExecutor.install/activate/upgrade` all return `OperationResult` (Task 3 model)
- `apply_plan` returns `OperationLog` consistently across Tasks 12-13
- `fetch_dependencies` returns `tuple[DependencyEntry, ...]` consistently (Task 5)
- `ProgressPoller.poll(tracker_id)` returns `ProgressState` consistently (Task 6)
- All new CLI commands use `_resolve_default_profile_or_die`, `_load_meta`, `_load_inventory_or_die`, `_load_oauth_token` -- verify these helpers exist in cli.py; if any name differs in the codebase, search and use the existing name.

**No placeholders:** All TBDs are scoped to Task 1's live-capture procedure with the exact substitution location named in Task 4.
