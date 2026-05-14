# Plugin Batch Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `nexus plugins updates` so a single command can upgrade every pending plugin (or every pending plugin in one or more product families), with skip-on-fail semantics and an exit-code-correct YAML report.

**Architecture:** Pure client-side loop -- ServiceNow exposes no batch upgrade endpoint. Adds two pure functions (`filter_by_family`, `available_families`), one frozen model (`BatchUpgradeReport`), one executor method (`PluginExecutor.batch_upgrade` -- iterates and calls existing `upgrade` per plugin, never rolls back), and three new CLI flags on the existing `plugins updates` command.

**Tech Stack:** Python 3.14, Pydantic v2 (frozen+strict+extra=forbid), Typer, Rich, pytest, FakeServiceNowClient. No new SN endpoints; reuses `PluginExecutor.upgrade` + `ProgressPoller` from sub-project M.

Spec: `docs/superpowers/specs/2026-05-14-plugin-batch-upgrade-design.md`
Branch: `feat/plugins-batch-upgrade` (already created)
Parent commit: `dd3fee2` (spec)

---

## File Structure Overview

**Create:**
- `src/nexus/plugins/filters.py` -- pure family filter + listing
- `tests/test_plugins_filters.py` -- filter helpers tests
- `tests/test_plugins_batch_upgrade.py` -- executor batch tests
- `tests/test_cli_plugins_updates_apply.py` -- CLI --apply / --family / --out tests

**Modify:**
- `src/nexus/plugins/executor.py` -- add `BatchUpgradeReport` + `batch_upgrade`
- `src/nexus/plugins/__init__.py` -- re-export new symbols
- `src/nexus/cli.py` -- extend `plugins_updates` with `--family`, `--apply`, `--out`, `--yes`
- `scripts/smoke_plugins.py` -- 3 new smoke tests

---

### Task 1: filters.py module skeleton + first filter test

**Files:**
- Create: `src/nexus/plugins/filters.py`
- Create: `tests/test_plugins_filters.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_plugins_filters.py`:

```python
# tests/test_plugins_filters.py
# Tests for nexus.plugins.filters helpers.
# Author: Pierre Grothe
# Date: 2026-05-14

"""Tests for filter_by_family and available_families."""

from nexus.plugins.filters import available_families, filter_by_family
from nexus.plugins.models import PluginInfo

__all__: list[str] = []


def _info(plugin_id: str, *, product_family: str = "Uncategorized") -> PluginInfo:
    return PluginInfo(
        plugin_id=plugin_id,
        name=plugin_id,
        version="1.0.0",
        state="active",
        source="store",
        product_family=product_family,
        depends_on=(),
        sys_id=f"sys-{plugin_id}",
        installed_at=None,
    )


def test_filter_by_family_single_match() -> None:
    plugins = (
        _info("com.acme.incident", product_family="ITSM"),
        _info("com.acme.cmdb", product_family="ITOM"),
        _info("com.acme.problem", product_family="ITSM"),
    )
    result = filter_by_family(plugins, ("ITSM",))
    assert tuple(p.plugin_id for p in result) == ("com.acme.incident", "com.acme.problem")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_plugins_filters.py::test_filter_by_family_single_match -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'nexus.plugins.filters'"

- [ ] **Step 3: Create the module with minimal implementation**

Create `src/nexus/plugins/filters.py`:

```python
# src/nexus/plugins/filters.py
# Pure-Python family filter helpers for the plugins inventory.
# Author: Pierre Grothe
# Date: 2026-05-14

"""filter_by_family + available_families: in-memory filters over PluginInfo tuples."""

from collections import Counter

from nexus.plugins.models import PluginInfo

__all__ = ["available_families", "filter_by_family"]


def filter_by_family(
    plugins: tuple[PluginInfo, ...],
    families: tuple[str, ...],
) -> tuple[PluginInfo, ...]:
    """Return plugins whose ``product_family`` matches any of ``families``.

    Matching is case-insensitive. When ``families`` is empty, the input is
    returned unchanged (no filter applied).

    Args:
        plugins: PluginInfo tuple, typically from PluginInventory or
            plugins_with_updates().
        families: Family names to keep. Empty tuple == no filter.

    Returns:
        Filtered tuple preserving original order.
    """
    if not families:
        return plugins
    wanted = {f.lower() for f in families}
    return tuple(p for p in plugins if p.product_family.lower() in wanted)


def available_families(
    plugins: tuple[PluginInfo, ...],
) -> tuple[tuple[str, int], ...]:
    """Return (family, count) pairs for all distinct families in plugins.

    Args:
        plugins: PluginInfo tuple to scan.

    Returns:
        Tuple of (family_name, plugin_count) sorted by family_name.
    """
    counter: Counter[str] = Counter(p.product_family for p in plugins)
    return tuple(sorted(counter.items(), key=lambda item: item[0]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_plugins_filters.py::test_filter_by_family_single_match -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/nexus/plugins/filters.py tests/test_plugins_filters.py
git commit -m "feat(plugins): add filter_by_family with single-family match"
```

---

### Task 2: Remaining filter_by_family tests

**Files:**
- Modify: `tests/test_plugins_filters.py`

- [ ] **Step 1: Add four more filter tests**

Append to `tests/test_plugins_filters.py`:

```python
def test_filter_by_family_multiple_families() -> None:
    plugins = (
        _info("com.acme.incident", product_family="ITSM"),
        _info("com.acme.cmdb", product_family="ITOM"),
        _info("com.acme.hr", product_family="HRSD"),
    )
    result = filter_by_family(plugins, ("ITSM", "ITOM"))
    assert tuple(p.plugin_id for p in result) == ("com.acme.incident", "com.acme.cmdb")


def test_filter_by_family_case_insensitive() -> None:
    plugins = (_info("com.acme.incident", product_family="ITSM"),)
    result = filter_by_family(plugins, ("itsm",))
    assert len(result) == 1


def test_filter_by_family_empty_filter_returns_all() -> None:
    plugins = (
        _info("com.acme.a", product_family="ITSM"),
        _info("com.acme.b", product_family="ITOM"),
    )
    result = filter_by_family(plugins, ())
    assert result == plugins


def test_filter_by_family_no_match_returns_empty() -> None:
    plugins = (_info("com.acme.incident", product_family="ITSM"),)
    result = filter_by_family(plugins, ("ITOM",))
    assert result == ()
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest tests/test_plugins_filters.py -v`
Expected: 5 passed

- [ ] **Step 3: Commit**

```bash
git add tests/test_plugins_filters.py
git commit -m "test(plugins): cover filter_by_family edge cases (multi/case/empty/no-match)"
```

---

### Task 3: available_families test

**Files:**
- Modify: `tests/test_plugins_filters.py`

- [ ] **Step 1: Add the test**

Append to `tests/test_plugins_filters.py`:

```python
def test_available_families_counts_sorted_alphabetically() -> None:
    plugins = (
        _info("com.acme.a", product_family="ITSM"),
        _info("com.acme.b", product_family="ITOM"),
        _info("com.acme.c", product_family="ITSM"),
        _info("com.acme.d", product_family="HRSD"),
    )
    result = available_families(plugins)
    assert result == (("HRSD", 1), ("ITOM", 1), ("ITSM", 2))
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest tests/test_plugins_filters.py -v`
Expected: 6 passed

- [ ] **Step 3: Commit**

```bash
git add tests/test_plugins_filters.py
git commit -m "test(plugins): cover available_families counts + alphabetical sort"
```

---

### Task 4: Re-export filter helpers

**Files:**
- Modify: `src/nexus/plugins/__init__.py`

- [ ] **Step 1: Add the imports + __all__ entries**

In `src/nexus/plugins/__init__.py`:

Add this import (alphabetical with the other `from nexus.plugins.*` lines, right after the `errors` block):

```python
from nexus.plugins.filters import available_families, filter_by_family
```

Add to the `__all__` list, keeping it sorted (alphabetical):

```python
    "available_families",
    "filter_by_family",
```

- [ ] **Step 2: Verify the package still imports**

Run: `python -c "from nexus.plugins import filter_by_family, available_families; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Run full plugins tests**

Run: `pytest tests/test_plugins_filters.py tests/test_plugins_models.py -v`
Expected: all passing

- [ ] **Step 4: Commit**

```bash
git add src/nexus/plugins/__init__.py
git commit -m "feat(plugins): re-export filter_by_family + available_families"
```

---

### Task 5: BatchUpgradeReport model

**Files:**
- Create: `tests/test_plugins_batch_upgrade.py`
- Modify: `src/nexus/plugins/executor.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_plugins_batch_upgrade.py`:

```python
# tests/test_plugins_batch_upgrade.py
# Tests for PluginExecutor.batch_upgrade and BatchUpgradeReport.
# Author: Pierre Grothe
# Date: 2026-05-14

"""Tests for the batch upgrade workflow."""

from datetime import UTC, datetime
from typing import Any

import pytest
from rich.console import Console

from nexus.plugins.executor import (
    BatchUpgradeReport,
    OperationResult,
    PluginExecutor,
)
from nexus.plugins.models import PluginInfo, PluginInventory
from tests.fakes.fake_sn_client import FakeServiceNowClient

__all__: list[str] = []


def _info(
    pid: str,
    *,
    version: str = "1.0.0",
    latest_version: str | None = "2.0.0",
    family: str = "ITSM",
) -> PluginInfo:
    return PluginInfo(
        plugin_id=pid,
        name=pid,
        version=version,
        state="active",
        source="store",
        product_family=family,
        depends_on=(),
        sys_id=f"sysid-{pid}",
        installed_at=None,
        latest_version=latest_version,
    )


def _inventory(*plugins: PluginInfo) -> PluginInventory:
    return PluginInventory(
        captured_at=datetime.now(UTC),
        sn_version="Xanadu",
        plugins=plugins,
    )


def _upgrade_kickoff(tracker: str = "t1") -> dict[str, Any]:
    return {
        "status": "0",
        "status_label": "Pending",
        "percent_complete": 0,
        "error": "",
        "update_set": None,
        "rollback_version": None,
        "trackerId": tracker,
        "status_message": "",
        "status_detail": "",
    }


def _progress(status: str, pct: int, err: str = "", tracker: str = "t1") -> dict[str, Any]:
    return {
        "status": status,
        "status_label": "x",
        "percent_complete": pct,
        "error": err,
        "update_set": None,
        "rollback_version": None,
        "trackerId": tracker,
        "status_message": "",
        "status_detail": "",
    }


@pytest.fixture
def console() -> Console:
    return Console(record=True, width=120)


def test_batch_upgrade_report_exit_code_all_succeeded() -> None:
    report = BatchUpgradeReport(
        results=(),
        families=(),
        target_count=0,
        succeeded=0,
        failed=0,
    )
    assert report.exit_code == 0


def test_batch_upgrade_report_exit_code_with_failures() -> None:
    fake_result = OperationResult(
        action="upgrade",
        plugin_id="com.acme.x",
        success=False,
        message="boom",
        duration_s=0.1,
        tracker_id="t1",
        update_set=None,
        rollback_version=None,
    )
    report = BatchUpgradeReport(
        results=(fake_result,),
        families=("ITSM",),
        target_count=1,
        succeeded=0,
        failed=1,
    )
    assert report.exit_code == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_plugins_batch_upgrade.py -v`
Expected: FAIL with `ImportError: cannot import name 'BatchUpgradeReport' from 'nexus.plugins.executor'`

- [ ] **Step 3: Add the model to executor.py**

In `src/nexus/plugins/executor.py`, add after the existing `OperationLog` class (around line 95):

```python
class BatchUpgradeReport(BaseModel):
    """Aggregate result of PluginExecutor.batch_upgrade.

    Attributes:
        results: One OperationResult per attempted plugin, in execution order.
        families: Family names used to filter targets, echoed back on the report.
            Empty tuple when no filter was applied.
        target_count: Number of plugins attempted (==len(results)).
        succeeded: Number of results with success=True.
        failed: Number of results with success=False.
    """

    model_config = _FROZEN

    results: tuple[OperationResult, ...]
    families: tuple[str, ...]
    target_count: int
    succeeded: int
    failed: int

    @property
    def exit_code(self) -> int:
        """0 when all succeeded (including empty target -- idempotent), 1 when any failed."""
        return 0 if self.failed == 0 else 1
```

Also update `__all__` at the top of the file:

```python
__all__ = ["BatchUpgradeReport", "OperationLog", "OperationResult", "PluginExecutor"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_plugins_batch_upgrade.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/nexus/plugins/executor.py tests/test_plugins_batch_upgrade.py
git commit -m "feat(plugins): add BatchUpgradeReport frozen model with exit_code"
```

---

### Task 6: PluginExecutor.batch_upgrade happy-path

**Files:**
- Modify: `tests/test_plugins_batch_upgrade.py`
- Modify: `src/nexus/plugins/executor.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_plugins_batch_upgrade.py`:

```python
async def test_batch_upgrade_all_succeed_in_order(console: Console) -> None:
    client = FakeServiceNowClient()
    for tracker in ("t-a", "t-b", "t-c"):
        client.queue_upgrade_response(_upgrade_kickoff(tracker))
        client.set_progress_sequence(tracker, [_progress("3", 100, tracker=tracker)])
    inv = _inventory(
        _info("com.acme.a"),
        _info("com.acme.b"),
        _info("com.acme.c"),
    )
    executor = PluginExecutor(client=client, inventory=inv)

    targets = inv.plugins
    report = await executor.batch_upgrade(targets, families=(), console=console)

    assert report.target_count == 3
    assert report.succeeded == 3
    assert report.failed == 0
    assert tuple(r.plugin_id for r in report.results) == (
        "com.acme.a",
        "com.acme.b",
        "com.acme.c",
    )
    assert all(r.success for r in report.results)
    assert report.exit_code == 0
```

Note: the test is async and uses pytest-asyncio. Confirm by reading the top of `tests/test_plugins_executor.py` -- they use the same pattern (no `@pytest.mark.asyncio` if `asyncio_mode = "auto"` is set in `pyproject.toml`, which it is for this project).

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_plugins_batch_upgrade.py::test_batch_upgrade_all_succeed_in_order -v`
Expected: FAIL with `AttributeError: 'PluginExecutor' object has no attribute 'batch_upgrade'`

- [ ] **Step 3: Implement batch_upgrade on PluginExecutor**

In `src/nexus/plugins/executor.py`, add this method on `PluginExecutor` (after `apply_plan`, before `_rollback`):

```python
async def batch_upgrade(
    self,
    targets: tuple[PluginInfo, ...],
    *,
    families: tuple[str, ...] = (),
    console: Console,
) -> BatchUpgradeReport:
    """Upgrade each target plugin sequentially. Skip-on-fail; never rolls back.

    Each plugin is upgraded to its ``latest_version`` (passed straight to
    ``submit_upgrade`` -- ``None`` means "latest available"). Failures are
    recorded but the loop continues.

    Args:
        targets: Plugins to upgrade, in execution order. Already filtered
            upstream (by family, by needs-update).
        families: Family filter names, echoed onto the report for audit.
            Empty tuple when no filter was applied.
        console: Rich console for per-plugin status output.

    Returns:
        BatchUpgradeReport with per-plugin OperationResult in execution order.
    """
    results: list[OperationResult] = []
    for plugin in targets:
        console.print(f"[label]upgrade {plugin.plugin_id}[/]")
        result = await self.upgrade(plugin.plugin_id, plugin.latest_version)
        results.append(result)
        if result.success:
            console.print(f"[ok]ok {plugin.plugin_id} -> {result.message}[/]")
        else:
            console.print(f"[error]fail {plugin.plugin_id}: {result.message}[/]")
    succeeded = sum(1 for r in results if r.success)
    failed = len(results) - succeeded
    return BatchUpgradeReport(
        results=tuple(results),
        families=families,
        target_count=len(results),
        succeeded=succeeded,
        failed=failed,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_plugins_batch_upgrade.py::test_batch_upgrade_all_succeed_in_order -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/nexus/plugins/executor.py tests/test_plugins_batch_upgrade.py
git commit -m "feat(plugins): PluginExecutor.batch_upgrade happy path"
```

---

### Task 7: batch_upgrade skip-on-fail behaviour

**Files:**
- Modify: `tests/test_plugins_batch_upgrade.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_plugins_batch_upgrade.py`:

```python
async def test_batch_upgrade_one_fails_others_continue(console: Console) -> None:
    client = FakeServiceNowClient()
    # a -> success
    client.queue_upgrade_response(_upgrade_kickoff("t-a"))
    client.set_progress_sequence("t-a", [_progress("3", 100, tracker="t-a")])
    # b -> SN reports failure (status "4")
    client.queue_upgrade_response(_upgrade_kickoff("t-b"))
    client.set_progress_sequence("t-b", [_progress("4", 100, err="boom", tracker="t-b")])
    # c -> success
    client.queue_upgrade_response(_upgrade_kickoff("t-c"))
    client.set_progress_sequence("t-c", [_progress("3", 100, tracker="t-c")])

    inv = _inventory(_info("com.acme.a"), _info("com.acme.b"), _info("com.acme.c"))
    executor = PluginExecutor(client=client, inventory=inv)

    report = await executor.batch_upgrade(inv.plugins, families=(), console=console)

    assert report.target_count == 3
    assert report.succeeded == 2
    assert report.failed == 1
    assert [r.plugin_id for r in report.results] == [
        "com.acme.a",
        "com.acme.b",
        "com.acme.c",
    ]
    assert [r.success for r in report.results] == [True, False, True]
    assert report.exit_code == 1
```

- [ ] **Step 2: Run test to verify it passes (it should -- skip-on-fail is the default loop behaviour)**

Run: `pytest tests/test_plugins_batch_upgrade.py::test_batch_upgrade_one_fails_others_continue -v`
Expected: PASS

If it fails: confirm `PluginExecutor.upgrade` returns an `OperationResult` with `success=False` rather than raising. (It does -- see existing executor code.)

- [ ] **Step 3: Commit**

```bash
git add tests/test_plugins_batch_upgrade.py
git commit -m "test(plugins): batch_upgrade continues past one failed plugin"
```

---

### Task 8: batch_upgrade never calls _rollback

**Files:**
- Modify: `tests/test_plugins_batch_upgrade.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_plugins_batch_upgrade.py`:

```python
async def test_batch_upgrade_does_not_invoke_rollback_on_failure(
    console: Console,
) -> None:
    """Regression guard: batch must never use apply_plan's rollback path."""

    class _NoRollbackExecutor(PluginExecutor):
        async def _rollback(self, completed, console):  # noqa: ARG002
            raise AssertionError("batch_upgrade must not invoke _rollback")

    client = FakeServiceNowClient()
    client.queue_upgrade_response(_upgrade_kickoff("t-a"))
    client.set_progress_sequence("t-a", [_progress("3", 100, tracker="t-a")])
    client.queue_upgrade_response(_upgrade_kickoff("t-b"))
    client.set_progress_sequence("t-b", [_progress("4", 100, err="boom", tracker="t-b")])

    inv = _inventory(_info("com.acme.a"), _info("com.acme.b"))
    executor = _NoRollbackExecutor(client=client, inventory=inv)
    report = await executor.batch_upgrade(inv.plugins, families=(), console=console)
    assert report.failed == 1
    assert report.succeeded == 1
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/test_plugins_batch_upgrade.py::test_batch_upgrade_does_not_invoke_rollback_on_failure -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_plugins_batch_upgrade.py
git commit -m "test(plugins): assert batch_upgrade never invokes _rollback"
```

---

### Task 9: batch_upgrade echoes families + handles empty targets

**Files:**
- Modify: `tests/test_plugins_batch_upgrade.py`

- [ ] **Step 1: Add two tests**

Append to `tests/test_plugins_batch_upgrade.py`:

```python
async def test_batch_upgrade_echoes_families_on_report(console: Console) -> None:
    client = FakeServiceNowClient()
    client.queue_upgrade_response(_upgrade_kickoff("t-a"))
    client.set_progress_sequence("t-a", [_progress("3", 100, tracker="t-a")])
    inv = _inventory(_info("com.acme.a"))
    executor = PluginExecutor(client=client, inventory=inv)
    report = await executor.batch_upgrade(
        inv.plugins, families=("ITSM", "ITOM"), console=console
    )
    assert report.families == ("ITSM", "ITOM")


async def test_batch_upgrade_empty_targets_returns_empty_report(console: Console) -> None:
    client = FakeServiceNowClient()
    inv = _inventory()
    executor = PluginExecutor(client=client, inventory=inv)
    report = await executor.batch_upgrade((), families=(), console=console)
    assert report.target_count == 0
    assert report.results == ()
    assert report.exit_code == 0
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest tests/test_plugins_batch_upgrade.py -v`
Expected: all 6 in this file pass

- [ ] **Step 3: Commit**

```bash
git add tests/test_plugins_batch_upgrade.py
git commit -m "test(plugins): batch_upgrade family echo + empty-target idempotent"
```

---

### Task 10: Re-export BatchUpgradeReport from package

**Files:**
- Modify: `src/nexus/plugins/__init__.py`

- [ ] **Step 1: Add the import + __all__ entry**

In `src/nexus/plugins/__init__.py`, update the executor import line:

```python
from nexus.plugins.executor import BatchUpgradeReport, OperationLog, OperationResult, PluginExecutor
```

Add to the `__all__` list, in alphabetical order:

```python
    "BatchUpgradeReport",
```

- [ ] **Step 2: Verify the package still imports**

Run: `python -c "from nexus.plugins import BatchUpgradeReport; print(BatchUpgradeReport.__name__)"`
Expected: `BatchUpgradeReport`

- [ ] **Step 3: Run full plugins test suite**

Run: `pytest tests/test_plugins_filters.py tests/test_plugins_batch_upgrade.py tests/test_plugins_executor.py -v`
Expected: all passing

- [ ] **Step 4: Commit**

```bash
git add src/nexus/plugins/__init__.py
git commit -m "feat(plugins): re-export BatchUpgradeReport"
```

---

### Task 11: CLI --family filter (no --apply yet)

**Files:**
- Create: `tests/test_cli_plugins_updates_apply.py`
- Modify: `src/nexus/cli.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli_plugins_updates_apply.py`:

```python
# tests/test_cli_plugins_updates_apply.py
# Tests for `nexus plugins updates` --family / --apply / --out flags.
# Author: Pierre Grothe
# Date: 2026-05-14

"""Tests for the batch-upgrade extensions on `nexus plugins updates`."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml as _yaml
from typer.testing import CliRunner

from nexus.cache import clear_cache
from nexus.cli import app
from nexus.config.paths import NexusPaths
from nexus.instances.models import InstanceMeta
from nexus.plugins.models import PluginInfo, PluginInventory

__all__: list[str] = []


def _meta(profile: str) -> InstanceMeta:
    return InstanceMeta.create(
        profile=profile,
        url=f"https://{profile}.service-now.com",
        username="admin",
        client_id="cid",
        sn_version="Xanadu",
        sn_build="04-01-2025_1200",
        instance_name=profile,
        token_expires_in=1800,
    )


def _info(
    pid: str,
    *,
    version: str = "1.0.0",
    latest_version: str | None = "2.0.0",
    family: str = "Uncategorized",
) -> PluginInfo:
    return PluginInfo.model_validate(
        {
            "plugin_id": pid,
            "name": pid,
            "version": version,
            "state": "active",
            "source": "store",
            "product_family": family,
            "depends_on": (),
            "sys_id": f"sys-{pid}",
            "installed_at": None,
            "latest_version": latest_version,
        }
    )


def _seed(tmp_path: Path, profile: str, plugins: tuple[PluginInfo, ...]) -> None:
    profile_dir = tmp_path / "instances" / profile
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "meta.json").write_text(
        _meta(profile).model_dump_json(indent=2), encoding="utf-8"
    )
    inv = PluginInventory(
        captured_at=datetime.now(UTC),
        sn_version="Xanadu",
        plugins=plugins,
    )
    (profile_dir / "plugins.json").write_text(inv.model_dump_json(indent=2), encoding="utf-8")


@pytest.fixture
def runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    monkeypatch.setenv("NEXUS_CONFIG_PATH", str(tmp_path / "config.yaml"))
    clear_cache(NexusPaths.from_env)
    return CliRunner()


def test_plugins_updates_family_filter_shrinks_pending(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "prod",
        (
            _info("com.acme.incident", family="ITSM"),
            _info("com.acme.cmdb", family="ITOM"),
        ),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "updates", "--family", "ITSM"])
    assert result.exit_code == 0
    assert "com.acme.incident" in result.output
    assert "com.acme.cmdb" not in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_plugins_updates_apply.py::test_plugins_updates_family_filter_shrinks_pending -v`
Expected: FAIL with "No such option: --family"

- [ ] **Step 3: Add --family option to plugins_updates**

In `src/nexus/cli.py` at `plugins_updates` (around line 2389), add the `--family` parameter after `--instance` and before `--queue`:

```python
    family: Annotated[
        list[str] | None,
        typer.Option(
            "--family",
            help="Filter to one or more product families (case-insensitive). Repeatable.",
        ),
    ] = None,
```

Add the filter step. After the line `pending = plugins_with_updates(inventory)` (around line 2414):

```python
    if family:
        from nexus.plugins.filters import filter_by_family  # noqa: PLC0415

        pending = filter_by_family(pending, tuple(family))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli_plugins_updates_apply.py::test_plugins_updates_family_filter_shrinks_pending -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/nexus/cli.py tests/test_cli_plugins_updates_apply.py
git commit -m "feat(cli): plugins updates --family filter (repeatable, case-insensitive)"
```

---

### Task 12: CLI unknown family -> exit 2

**Files:**
- Modify: `tests/test_cli_plugins_updates_apply.py`
- Modify: `src/nexus/cli.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli_plugins_updates_apply.py`:

```python
def test_plugins_updates_unknown_family_exits_2_and_lists_available(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "prod",
        (
            _info("com.acme.incident", family="ITSM"),
            _info("com.acme.cmdb", family="ITOM"),
        ),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "updates", "--family", "BOGUS"])
    assert result.exit_code == 2
    assert "ITSM" in result.output
    assert "ITOM" in result.output
    assert "BOGUS" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_plugins_updates_apply.py::test_plugins_updates_unknown_family_exits_2_and_lists_available -v`
Expected: FAIL (exit code currently 0, not 2)

- [ ] **Step 3: Add validation block in plugins_updates**

In `src/nexus/cli.py`, replace the `if family:` block added in Task 11 with:

```python
    if family:
        from nexus.plugins.filters import (  # noqa: PLC0415
            available_families,
            filter_by_family,
        )
        from nexus.plugins.models import ProductFamily  # noqa: PLC0415

        valid = {f.value.lower() for f in ProductFamily}
        unknown = [f for f in family if f.lower() not in valid]
        if unknown:
            console.print(
                Notice.error(
                    f"Unknown product family: {', '.join(unknown)}. "
                    f"Available families on this instance:"
                )
            )
            rows: list[list[RenderableType]] = [
                [name, str(count)] for name, count in available_families(inventory.plugins)
            ]
            console.print(
                DataTable(
                    title="Available families",
                    columns=[
                        DataColumn(header="Family", width=20),
                        DataColumn(header="Plugins", width=10),
                    ],
                    rows=rows,
                )
            )
            raise typer.Exit(2)
        pending = filter_by_family(pending, tuple(family))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli_plugins_updates_apply.py::test_plugins_updates_unknown_family_exits_2_and_lists_available -v`
Expected: PASS

- [ ] **Step 5: Confirm the earlier family test still passes**

Run: `pytest tests/test_cli_plugins_updates_apply.py -v`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add src/nexus/cli.py tests/test_cli_plugins_updates_apply.py
git commit -m "feat(cli): plugins updates unknown --family exits 2 with available list"
```

---

### Task 13: CLI --apply executes batch_upgrade with --yes

**Files:**
- Modify: `tests/test_cli_plugins_updates_apply.py`
- Modify: `src/nexus/cli.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli_plugins_updates_apply.py`:

```python
def test_plugins_updates_apply_executes_batch_upgrade(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--apply --yes calls executor.batch_upgrade once with the pending set."""
    _seed(
        tmp_path,
        "prod",
        (
            _info("com.acme.incident", family="ITSM"),
            _info("com.acme.cmdb", family="ITOM"),
        ),
    )
    runner.invoke(app, ["instance", "use", "prod"])

    calls: list[dict[str, object]] = []

    async def _fake_batch_upgrade(
        self,  # noqa: ARG001
        targets,
        *,
        families,
        console,  # noqa: ARG001
    ):
        from nexus.plugins.executor import BatchUpgradeReport

        calls.append({"targets": [p.plugin_id for p in targets], "families": families})
        return BatchUpgradeReport(
            results=(),
            families=families,
            target_count=len(targets),
            succeeded=len(targets),
            failed=0,
        )

    monkeypatch.setattr(
        "nexus.plugins.executor.PluginExecutor.batch_upgrade",
        _fake_batch_upgrade,
    )
    # Stub _acquire_token + ServiceNowClient construction to avoid real auth.
    monkeypatch.setattr(
        "nexus.cli._acquire_token",
        lambda profile: (profile, "url", "token", None),
    )

    class _FakeAsyncCtx:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr("nexus.cli.ServiceNowClient", lambda **_: _FakeAsyncCtx())

    result = runner.invoke(
        app, ["plugins", "updates", "--apply", "--yes"]
    )
    assert result.exit_code == 0
    assert len(calls) == 1
    assert set(calls[0]["targets"]) == {"com.acme.incident", "com.acme.cmdb"}
    assert calls[0]["families"] == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_plugins_updates_apply.py::test_plugins_updates_apply_executes_batch_upgrade -v`
Expected: FAIL ("No such option: --apply")

- [ ] **Step 3: Add --apply and --yes flags + the apply block**

In `src/nexus/cli.py` at `plugins_updates`, add these parameters after `--family`:

```python
    apply_flag: Annotated[
        bool,
        typer.Option(
            "--apply",
            help="Upgrade every pending plugin (sequential, skip-on-fail). Destructive.",
        ),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", help="Skip the confirmation prompt before --apply."),
    ] = False,
```

At the END of the function (after the existing table render + queue message), add:

```python
    if apply_flag:
        if not pending:
            console.print(Notice.info("Nothing to upgrade."))
            return
        if not yes and not typer.confirm(
            f"Upgrade {len(pending)} plugin(s) on {meta.profile}?"
        ):
            raise typer.Exit(0)

        from nexus.plugins.executor import PluginExecutor  # noqa: PLC0415

        _, _, token, _ = _acquire_token(meta.profile)
        families_used: tuple[str, ...] = tuple(family) if family else ()

        async def _run() -> None:
            async with ServiceNowClient(instance_url=meta.url, token=token) as client:
                executor = PluginExecutor(client=client, inventory=inventory)
                report = await executor.batch_upgrade(
                    pending, families=families_used, console=console
                )
                console.print(
                    Notice.info(
                        f"{report.succeeded} upgraded, {report.failed} failed "
                        f"(of {report.target_count})."
                    )
                )
                if report.exit_code != 0:
                    raise typer.Exit(report.exit_code)

        asyncio.run(_run())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli_plugins_updates_apply.py::test_plugins_updates_apply_executes_batch_upgrade -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/nexus/cli.py tests/test_cli_plugins_updates_apply.py
git commit -m "feat(cli): plugins updates --apply --yes runs batch_upgrade sequentially"
```

---

### Task 14: CLI --out writes BatchUpgradeReport YAML

**Files:**
- Modify: `tests/test_cli_plugins_updates_apply.py`
- Modify: `src/nexus/cli.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli_plugins_updates_apply.py`:

```python
def test_plugins_updates_apply_writes_report_yaml(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path, "prod", (_info("com.acme.incident", family="ITSM"),))
    runner.invoke(app, ["instance", "use", "prod"])

    async def _fake_batch_upgrade(self, targets, *, families, console):  # noqa: ARG001
        from nexus.plugins.executor import BatchUpgradeReport, OperationResult

        return BatchUpgradeReport(
            results=(
                OperationResult(
                    action="upgrade",
                    plugin_id="com.acme.incident",
                    success=True,
                    message="Success",
                    duration_s=1.23,
                    tracker_id="t-a",
                    update_set=None,
                    rollback_version=None,
                ),
            ),
            families=families,
            target_count=1,
            succeeded=1,
            failed=0,
        )

    monkeypatch.setattr(
        "nexus.plugins.executor.PluginExecutor.batch_upgrade", _fake_batch_upgrade
    )
    monkeypatch.setattr(
        "nexus.cli._acquire_token",
        lambda profile: (profile, "url", "token", None),
    )

    class _FakeAsyncCtx:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr("nexus.cli.ServiceNowClient", lambda **_: _FakeAsyncCtx())

    out_path = tmp_path / "report.yaml"
    result = runner.invoke(
        app,
        [
            "plugins",
            "updates",
            "--apply",
            "--yes",
            "--out",
            str(out_path),
        ],
    )
    assert result.exit_code == 0
    payload = _yaml.safe_load(out_path.read_text(encoding="utf-8"))
    assert payload["target_count"] == 1
    assert payload["succeeded"] == 1
    assert payload["failed"] == 0
    assert payload["results"][0]["plugin_id"] == "com.acme.incident"
    assert payload["results"][0]["success"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_plugins_updates_apply.py::test_plugins_updates_apply_writes_report_yaml -v`
Expected: FAIL ("No such option: --out")

- [ ] **Step 3: Add --out parameter and writer**

In `src/nexus/cli.py` at `plugins_updates`, add this parameter right after `yes`:

```python
    out: Annotated[
        str,
        typer.Option(
            "--out",
            help="Write BatchUpgradeReport YAML to this path after --apply runs.",
        ),
    ] = "",
```

In the apply block (inside `_run`), after the `Notice.info(...)` line, before the `report.exit_code` check, add:

```python
                if out:
                    Path(out).write_text(
                        _yaml.safe_dump(report.model_dump(), sort_keys=False),
                        encoding="utf-8",
                    )
```

(`Path` and `_yaml` are already imported at the top of cli.py for the `--queue` flag.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli_plugins_updates_apply.py::test_plugins_updates_apply_writes_report_yaml -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/nexus/cli.py tests/test_cli_plugins_updates_apply.py
git commit -m "feat(cli): plugins updates --out writes BatchUpgradeReport YAML"
```

---

### Task 15: CLI confirms when --yes is absent

**Files:**
- Modify: `tests/test_cli_plugins_updates_apply.py`

- [ ] **Step 1: Write the test**

Append to `tests/test_cli_plugins_updates_apply.py`:

```python
def test_plugins_updates_apply_prompts_when_yes_absent(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without --yes, declining the prompt exits 0 without calling batch_upgrade."""
    _seed(tmp_path, "prod", (_info("com.acme.incident", family="ITSM"),))
    runner.invoke(app, ["instance", "use", "prod"])

    calls: list[int] = []

    async def _should_not_run(self, *a, **kw):  # noqa: ARG001
        calls.append(1)

    monkeypatch.setattr(
        "nexus.plugins.executor.PluginExecutor.batch_upgrade", _should_not_run
    )
    result = runner.invoke(app, ["plugins", "updates", "--apply"], input="n\n")
    assert result.exit_code == 0
    assert calls == []
```

- [ ] **Step 2: Run test to verify it passes (typer.confirm with declined input -> our code raises typer.Exit(0))**

Run: `pytest tests/test_cli_plugins_updates_apply.py::test_plugins_updates_apply_prompts_when_yes_absent -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_cli_plugins_updates_apply.py
git commit -m "test(cli): plugins updates --apply confirms before destructive run"
```

---

### Task 16: CLI dry-run regression test (no --apply)

**Files:**
- Modify: `tests/test_cli_plugins_updates_apply.py`

- [ ] **Step 1: Write the test**

Append to `tests/test_cli_plugins_updates_apply.py`:

```python
def test_plugins_updates_without_apply_remains_dry_run(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No --apply flag: lists the candidate set, never invokes batch_upgrade."""
    _seed(tmp_path, "prod", (_info("com.acme.incident", family="ITSM"),))
    runner.invoke(app, ["instance", "use", "prod"])

    calls: list[int] = []

    async def _should_not_run(self, *a, **kw):  # noqa: ARG001
        calls.append(1)

    monkeypatch.setattr(
        "nexus.plugins.executor.PluginExecutor.batch_upgrade", _should_not_run
    )
    result = runner.invoke(app, ["plugins", "updates"])
    assert result.exit_code == 0
    assert "com.acme.incident" in result.output
    assert calls == []
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/test_cli_plugins_updates_apply.py::test_plugins_updates_without_apply_remains_dry_run -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_cli_plugins_updates_apply.py
git commit -m "test(cli): plugins updates without --apply remains dry-run"
```

---

### Task 17: Empty-target idempotent path

**Files:**
- Modify: `tests/test_cli_plugins_updates_apply.py`

- [ ] **Step 1: Write the test**

Append to `tests/test_cli_plugins_updates_apply.py`:

```python
def test_plugins_updates_apply_empty_target_exits_zero(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No pending updates + --apply: exit 0, never invoke batch_upgrade."""
    _seed(
        tmp_path,
        "prod",
        (
            _info(
                "com.acme.incident",
                version="2.0.0",
                latest_version="2.0.0",
                family="ITSM",
            ),
        ),
    )
    runner.invoke(app, ["instance", "use", "prod"])

    calls: list[int] = []

    async def _should_not_run(self, *a, **kw):  # noqa: ARG001
        calls.append(1)

    monkeypatch.setattr(
        "nexus.plugins.executor.PluginExecutor.batch_upgrade", _should_not_run
    )
    result = runner.invoke(app, ["plugins", "updates", "--apply", "--yes"])
    assert result.exit_code == 0
    assert calls == []
    assert "Nothing to upgrade" in result.output
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/test_cli_plugins_updates_apply.py::test_plugins_updates_apply_empty_target_exits_zero -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_cli_plugins_updates_apply.py
git commit -m "test(cli): plugins updates --apply on empty target is idempotent (exit 0)"
```

---

### Task 18: Smoke tests for live family filter

**Files:**
- Modify: `scripts/smoke_plugins.py`

- [ ] **Step 1: Read the existing smoke patterns**

Open `scripts/smoke_plugins.py` and find the helper that runs `nexus plugins updates` (existing dry-run smoke). Match its style:

- Uses subprocess to invoke `nexus plugins updates ...`
- Asserts on stdout / exit code
- Reports pass/fail counters in a totals line

- [ ] **Step 2: Add the three new smoke tests**

Append three new smoke functions inside `scripts/smoke_plugins.py`. Follow the pattern of the existing `smoke_plugins_updates_*` helpers (look at the file for naming + invocation conventions; smoke functions take `profile: str` and return a result tuple consumed by the totals block).

```python
def smoke_plugins_updates_family_filter(profile: str) -> tuple[str, bool, str]:
    """`--family Platform` succeeds and only shows Platform-family plugins."""
    result = subprocess.run(
        ["nexus", "plugins", "updates", "--family", "Platform", "--instance", profile],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return (
            "plugins updates --family Platform",
            False,
            f"exit {result.returncode}: {result.stderr.strip()[:200]}",
        )
    if "Platform" not in result.stdout and "Up to date" not in result.stdout:
        return (
            "plugins updates --family Platform",
            False,
            "neither Platform updates nor up-to-date marker seen",
        )
    return ("plugins updates --family Platform", True, "ok")


def smoke_plugins_updates_unknown_family(profile: str) -> tuple[str, bool, str]:
    """Unknown --family exits 2 and lists available families."""
    result = subprocess.run(
        ["nexus", "plugins", "updates", "--family", "ZZZ_BOGUS", "--instance", profile],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 2:
        return (
            "plugins updates --family ZZZ_BOGUS",
            False,
            f"expected exit 2, got {result.returncode}",
        )
    if "ZZZ_BOGUS" not in result.stdout:
        return (
            "plugins updates --family ZZZ_BOGUS",
            False,
            "expected the bad family name to appear in error output",
        )
    return ("plugins updates --family ZZZ_BOGUS", True, "ok")


def smoke_plugins_updates_dry_run_no_apply(profile: str) -> tuple[str, bool, str]:
    """Without --apply, the command never calls submit_upgrade (dry-run)."""
    result = subprocess.run(
        ["nexus", "plugins", "updates", "--instance", profile],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return (
            "plugins updates (dry-run)",
            False,
            f"exit {result.returncode}: {result.stderr.strip()[:200]}",
        )
    # Dry run never writes a YAML report
    return ("plugins updates (dry-run)", True, "ok")
```

Register the three new functions in the master smoke list (whatever data structure the file uses for ordering the runs -- a list/tuple at module scope, named something like `_SMOKES`, `ALL_SMOKES`, or directly invoked in `main()`).

- [ ] **Step 3: Verify smoke script still parses**

Run: `python scripts/smoke_plugins.py --help`
Expected: prints usage with no traceback.

- [ ] **Step 4: Commit**

```bash
git add scripts/smoke_plugins.py
git commit -m "test(smoke): add family-filter + unknown-family + dry-run smokes"
```

---

### Task 19: Full suite + ratchet refresh

**Files:**
- Modify (auto-generated): `.ratchet.json`, `coverage.json`

- [ ] **Step 1: Run the full pytest suite**

Run: `pytest`
Expected: All previously passing tests still pass + ~16 new tests pass. Total around 903 tests.

- [ ] **Step 2: Run ruff + mypy + pyright**

Run: `ruff check src/ tests/ scripts/`
Run: `mypy src/nexus/`
Run: `pyright src/nexus/`
Expected: 0 violations / 0 errors from each.

If pyright complains about implicit-Any in test files (`def _fake_batch_upgrade(self, targets, *, families, console)`), add explicit type annotations:

```python
from nexus.plugins.executor import BatchUpgradeReport
from nexus.plugins.models import PluginInfo
from rich.console import Console

async def _fake_batch_upgrade(
    self: object,
    targets: tuple[PluginInfo, ...],
    *,
    families: tuple[str, ...],
    console: Console,
) -> BatchUpgradeReport:
    ...
```

- [ ] **Step 3: Inspect ratchet drift**

Run: `git diff .ratchet.json` (if regenerated by hooks)
Expected: per-module covered_lines for executor.py and the new filters.py at or above baseline. If any module dropped, investigate the test gap rather than lowering the baseline.

- [ ] **Step 4: Commit any auto-generated baseline updates**

```bash
git add .ratchet.json coverage.json
git commit -m "chore(plugins): refresh coverage ratchet for batch_upgrade + filters"
```

(Skip if there's nothing staged.)

---

### Task 20: Primer + roadmap sync

**Files:**
- Modify: `.primer/active.md`
- Modify: `.primer/progress.md`
- Modify: `.primer/roadmap.md`

- [ ] **Step 1: Update active.md with the batch-upgrade entry**

Append a line to the Recent Changes section pointing to the merged PR (placeholder hash until merge):

```
- <pending-merge> feat(plugins): batch upgrade via `nexus plugins updates --apply [--family]`
```

Update the Current Focus block to remove the batch-upgrade item from Next Steps if it was added (we did not add it; this is a small follow-on).

- [ ] **Step 2: Update progress.md What Works section**

Under the Plugins layer block, add a bullet:

```
  batch_upgrade -- BatchUpgradeReport + skip-on-fail loop; filter_by_family
    + available_families helpers; `nexus plugins updates --apply --family X
    --out report.yaml` extends the existing updates command without a new
    subcommand.
```

- [ ] **Step 3: Update roadmap.md**

The roadmap's "Plugin Execution" section is already marked done. Add the batch upgrade as a Done sub-bullet to capture the shipped scope:

```
- [x] Batch upgrade -- `nexus plugins updates --apply [--family ...]` with
      skip-on-fail; reuses sub-project M's PluginExecutor.upgrade primitive.
```

- [ ] **Step 4: Commit primer sync**

```bash
git add .primer/active.md .primer/progress.md .primer/roadmap.md
git commit -m "primer: sync after batch upgrade shipped"
```

---

### Task 21: Open the PR

**Files:** none

- [ ] **Step 1: Push the branch**

Run: `git push -u origin feat/plugins-batch-upgrade`

- [ ] **Step 2: Open the PR**

Run:

```bash
gh pr create --title "feat(plugins): batch upgrade via updates --apply [--family]" --body "$(cat <<'EOF'
## Summary

- Adds `--apply`, `--family NAME` (repeatable), `--out PATH`, `--yes` flags to `nexus plugins updates`.
- New `PluginExecutor.batch_upgrade` runs upgrades sequentially with skip-on-fail (no rollback, by design -- different audience than apply_plan).
- New pure helpers `filter_by_family` + `available_families` in `nexus.plugins.filters`.
- New frozen `BatchUpgradeReport` model with `exit_code` property.
- Unknown family name exits 2 + lists available families. Empty pending set is idempotent (exit 0).

Native API check: ServiceNow exposes no batch upgrade endpoint (confirmed against `docs/sn-internal-api-catalog.md`). Client-side loop is the only path. `/api/now/v1/batch` is already used internally to wrap individual kickoffs.

Spec: `docs/superpowers/specs/2026-05-14-plugin-batch-upgrade-design.md`
Plan: `docs/superpowers/plans/2026-05-14-plugin-batch-upgrade.md`

## Test plan

- [x] 6 unit tests for `filter_by_family` + `available_families`
- [x] 6 unit tests for `PluginExecutor.batch_upgrade` (happy / skip-on-fail / no-rollback / family-echo / empty / exit-code)
- [x] 7 CLI tests (`--family`, unknown family, `--apply --yes`, `--out`, prompt path, dry-run regression, empty-target)
- [x] 3 live smoke tests on alectri PDI (family filter, unknown family, dry-run)
- [x] ruff / mypy strict / pyright strict all green
- [x] Coverage ratchet preserved
EOF
)"
```

- [ ] **Step 3: Confirm PR opened**

Verify the URL printed by `gh pr create` opens cleanly and CI starts.

---

## Self-Review Checklist (already applied)

**Spec coverage:**
- User stories 1-4: covered by Tasks 11-17 (CLI flow) + Task 5-9 (executor).
- Family source: Tasks 1-4 (`filter_by_family` reads `PluginInfo.product_family`).
- Skip-on-fail: Task 7 + Task 8 (no-rollback regression).
- Impact gate (none, by design): verified by Task 8 (`_rollback` not invoked); upgrade itself never gates so nothing to test.
- Concurrency (sequential): Task 6's order-preserving assertion.
- CLI entry point: Tasks 11-14.
- Models: Task 5 (BatchUpgradeReport) + Task 10 (re-export).
- Error handling: Task 12 (unknown family exit 2), Task 13 (decline -> exit 0), Task 17 (empty -> exit 0).
- File plan: 4 new + 4 modified files -- matches the spec.
- Test plan: 6 + 6 + 7 + 3 smokes = 22 new tests, slightly above the spec's ~16-21 estimate, all listed above.

**Placeholder scan:** no "TBD", "TODO", "fill in details", or vague "handle errors" in any step.

**Type consistency:**
- `PluginExecutor.batch_upgrade` signature identical across Task 5's spec excerpt, Task 6's implementation, and Task 13's call site.
- `BatchUpgradeReport` field set identical between Task 5's model, Task 14's YAML payload, and Task 15's empty case.
- `filter_by_family` and `available_families` signatures match across module (Task 1), tests (Task 1-3), and CLI usage (Tasks 11-12).
