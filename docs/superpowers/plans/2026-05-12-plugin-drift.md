# Plugin Drift Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single-instance over-time audit feature: `nexus plugins drift` compares a manually-ack'd baseline `PluginInventory` against the current snapshot and surfaces added/removed/version_changed/state_changed plugins.

**Architecture:** New pure-function module `nexus.plugins.drift` (mirrors `nexus.plugins.diff` shape), one new error class, two new registry methods (atomic-rename pattern), one new CLI command with `--ack`, `--format`, and `--strict` flags. Storage: `instances/<profile>/plugins.baseline.json` -- independent of `plugins.json`.

**Tech Stack:** Python 3.14, Pydantic v2 (frozen+strict+extra=forbid), Typer, httpx (for nothing -- drift has no HTTP).

**Branch:** `feat/plugins-drift` (already created, spec committed at `a2ae013`, stacked on `feat/plugins-cleanups`).

**Spec:** `docs/superpowers/specs/2026-05-12-plugin-drift-design.md`

---

## File Map

**New files:**
- `src/nexus/plugins/drift.py` -- `PluginDriftEntry`, `PluginDriftReport`, `compute_drift`
- `tests/test_plugins_drift.py` -- pure-function tests
- `tests/test_cli_plugins_drift.py` -- CLI integration tests

**Modified files:**
- `src/nexus/plugins/errors.py` -- add `PluginBaselineNotFoundError`
- `src/nexus/plugins/__init__.py` -- re-export new public symbols
- `src/nexus/instances/registry.py` -- add `load_plugin_baseline` + `save_plugin_baseline`
- `src/nexus/cli.py` -- add `plugins_drift` command
- `tests/test_instances_registry.py` -- add baseline round-trip tests
- `.ratchet.json` -- bump coverage for affected modules (final task)

---

## Task 1: `nexus.plugins.drift` module + pure tests

**Files:**
- Create: `src/nexus/plugins/drift.py`
- Create: `tests/test_plugins_drift.py`

- [ ] **Step 1: Write failing tests for the data models and compute_drift**

Create `tests/test_plugins_drift.py`:

```python
# tests/test_plugins_drift.py
# Tests for single-instance over-time plugin drift detection.
# Author: Pierre Grothe
# Date: 2026-05-12
"""Tests for PluginDriftEntry / PluginDriftReport / compute_drift."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from nexus.plugins.drift import (
    PluginDriftEntry,
    PluginDriftReport,
    compute_drift,
)
from nexus.plugins.models import PluginInfo, PluginInventory

__all__: list[str] = []


def _entry(**overrides: object) -> PluginDriftEntry:
    defaults: dict[str, object] = {
        "plugin_id": "com.snc.incident",
        "name": "Incident Management",
        "product_family": "ITSM",
        "status": "version_changed",
        "baseline_version": "1.0.0",
        "current_version": "1.2.0",
        "baseline_state": "active",
        "current_state": "active",
    }
    defaults.update(overrides)
    return PluginDriftEntry.model_validate(defaults)


def _info(
    plugin_id: str,
    *,
    version: str = "1.0.0",
    state: str = "active",
    product_family: str = "ITSM",
) -> PluginInfo:
    return PluginInfo.model_validate(
        {
            "plugin_id": plugin_id,
            "name": plugin_id,
            "version": version,
            "state": state,
            "source": "servicenow",
            "product_family": product_family,
            "depends_on": (),
            "sys_id": f"sys-{plugin_id}",
            "installed_at": None,
        }
    )


def _inventory(*plugins: PluginInfo) -> PluginInventory:
    return PluginInventory(
        captured_at=datetime.now(UTC),
        sn_version="Xanadu",
        plugins=plugins,
    )


def test_plugin_drift_entry_construction_with_required_fields() -> None:
    entry = _entry()
    assert entry.plugin_id == "com.snc.incident"
    assert entry.status == "version_changed"


def test_plugin_drift_entry_is_frozen() -> None:
    entry = _entry()
    with pytest.raises(ValidationError):
        entry.plugin_id = "renamed"


def test_plugin_drift_entry_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        _entry(status="weird")


def test_plugin_drift_entry_accepts_none_for_baseline_fields_when_added() -> None:
    entry = _entry(status="added", baseline_version=None, baseline_state=None)
    assert entry.baseline_version is None
    assert entry.baseline_state is None


def test_plugin_drift_report_holds_profile_and_captured_at_pair() -> None:
    t0 = datetime(2026, 5, 1, tzinfo=UTC)
    t1 = datetime(2026, 5, 12, tzinfo=UTC)
    report = PluginDriftReport(
        profile="prod",
        baseline_captured_at=t0,
        current_captured_at=t1,
        entries=(_entry(),),
    )
    assert report.profile == "prod"
    assert report.baseline_captured_at == t0
    assert report.current_captured_at == t1


def test_compute_drift_returns_empty_when_inventories_identical() -> None:
    inv = _inventory(_info("com.snc.incident"))
    report = compute_drift(inv, inv, "prod")
    assert report.entries == ()


def test_compute_drift_emits_added_for_plugin_only_in_current() -> None:
    baseline = _inventory()
    current = _inventory(_info("com.snc.new"))
    report = compute_drift(baseline, current, "prod")
    assert len(report.entries) == 1
    entry = report.entries[0]
    assert entry.plugin_id == "com.snc.new"
    assert entry.status == "added"
    assert entry.baseline_version is None
    assert entry.baseline_state is None
    assert entry.current_version == "1.0.0"
    assert entry.current_state == "active"


def test_compute_drift_emits_removed_for_plugin_only_in_baseline() -> None:
    baseline = _inventory(_info("com.snc.gone"))
    current = _inventory()
    report = compute_drift(baseline, current, "prod")
    assert len(report.entries) == 1
    entry = report.entries[0]
    assert entry.plugin_id == "com.snc.gone"
    assert entry.status == "removed"
    assert entry.baseline_version == "1.0.0"
    assert entry.current_version is None


def test_compute_drift_emits_version_changed_when_versions_differ() -> None:
    baseline = _inventory(_info("com.snc.x", version="1.0.0"))
    current = _inventory(_info("com.snc.x", version="2.0.0"))
    report = compute_drift(baseline, current, "prod")
    assert len(report.entries) == 1
    entry = report.entries[0]
    assert entry.status == "version_changed"
    assert entry.baseline_version == "1.0.0"
    assert entry.current_version == "2.0.0"


def test_compute_drift_emits_state_changed_when_state_flipped() -> None:
    baseline = _inventory(_info("com.snc.x", state="inactive"))
    current = _inventory(_info("com.snc.x", state="active"))
    report = compute_drift(baseline, current, "prod")
    assert len(report.entries) == 1
    entry = report.entries[0]
    assert entry.status == "state_changed"
    assert entry.baseline_state == "inactive"
    assert entry.current_state == "active"


def test_compute_drift_uses_version_changed_when_both_version_and_state_differ() -> None:
    """version_changed wins as the primary key; both fields populated."""
    baseline = _inventory(_info("com.snc.x", version="1.0.0", state="inactive"))
    current = _inventory(_info("com.snc.x", version="2.0.0", state="active"))
    report = compute_drift(baseline, current, "prod")
    assert len(report.entries) == 1
    entry = report.entries[0]
    assert entry.status == "version_changed"
    assert entry.baseline_version == "1.0.0"
    assert entry.current_version == "2.0.0"
    assert entry.baseline_state == "inactive"
    assert entry.current_state == "active"


def test_compute_drift_sorts_entries_by_product_family_then_plugin_id() -> None:
    baseline = _inventory()
    current = _inventory(
        _info("com.b.alpha", product_family="ITSM"),
        _info("com.a.alpha", product_family="HRSD"),
        _info("com.a.beta", product_family="HRSD"),
    )
    report = compute_drift(baseline, current, "prod")
    ids = [e.plugin_id for e in report.entries]
    assert ids == ["com.a.alpha", "com.a.beta", "com.b.alpha"]


def test_compute_drift_returns_mixed_statuses() -> None:
    baseline = _inventory(
        _info("com.a", version="1.0.0"),
        _info("com.gone"),
        _info("com.flip", state="inactive"),
    )
    current = _inventory(
        _info("com.a", version="2.0.0"),
        _info("com.new"),
        _info("com.flip", state="active"),
    )
    report = compute_drift(baseline, current, "prod")
    statuses = sorted(e.status for e in report.entries)
    assert statuses == ["added", "removed", "state_changed", "version_changed"]


def test_compute_drift_records_captured_at_from_both_inventories() -> None:
    t0 = datetime(2026, 5, 1, tzinfo=UTC)
    t1 = datetime(2026, 5, 12, tzinfo=UTC)
    baseline = PluginInventory(captured_at=t0, sn_version="Xanadu", plugins=())
    current = PluginInventory(captured_at=t1, sn_version="Xanadu", plugins=())
    report = compute_drift(baseline, current, "prod")
    assert report.baseline_captured_at == t0
    assert report.current_captured_at == t1
```

- [ ] **Step 2: Run; expect FAIL (ImportError)**

`.venv/Scripts/python -m pytest tests/test_plugins_drift.py -v --no-cov`

Expected: ImportError -- `nexus.plugins.drift` does not exist yet.

- [ ] **Step 3: Create `src/nexus/plugins/drift.py`**

```python
# src/nexus/plugins/drift.py
# Single-instance over-time plugin drift detection.
# Author: Pierre Grothe
# Date: 2026-05-12
"""PluginDriftEntry, PluginDriftReport, and compute_drift.

Mirror of ``nexus.plugins.diff`` for single-instance drift: compare
a baseline ``PluginInventory`` against a current one on the same
profile and emit added / removed / version_changed / state_changed
entries.

No I/O: pure functions over already-loaded inventories. The CLI
layer reads the two inventories from disk via the registry.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from nexus.config.types import UtcDatetime
from nexus.plugins.models import PluginInfo, PluginInventory

__all__ = [
    "PluginDriftEntry",
    "PluginDriftReport",
    "compute_drift",
]

_FROZEN = ConfigDict(frozen=True, strict=True, extra="forbid")


class PluginDriftEntry(BaseModel):
    """One drift row: how a plugin changed between baseline and current.

    Attributes:
        plugin_id: Canonical SN plugin identifier.
        name: Display name (from whichever inventory had the entry).
        product_family: Curated product family or ``Uncategorized``.
        status: Why this row appears. ``version_changed`` wins when
            both version and state changed; the four ``baseline_*``
            / ``current_*`` fields still report both deltas truthfully.
        baseline_version: Version in baseline, or ``None`` when added.
        current_version: Version in current, or ``None`` when removed.
        baseline_state: State in baseline, or ``None`` when added.
        current_state: State in current, or ``None`` when removed.
    """

    model_config = _FROZEN

    plugin_id: str
    name: str
    product_family: str
    status: Literal["added", "removed", "version_changed", "state_changed"]
    baseline_version: str | None
    current_version: str | None
    baseline_state: Literal["active", "inactive"] | None
    current_state: Literal["active", "inactive"] | None


class PluginDriftReport(BaseModel):
    """Drift between a baseline and current inventory for one profile.

    Attributes:
        profile: Instance profile this drift applies to.
        baseline_captured_at: When the baseline inventory was captured.
        current_captured_at: When the current inventory was captured.
        entries: Drift entries in stable ``(product_family, plugin_id)``
            ascending order.
    """

    model_config = _FROZEN

    profile: str
    baseline_captured_at: UtcDatetime
    current_captured_at: UtcDatetime
    entries: tuple[PluginDriftEntry, ...]


def compute_drift(
    baseline: PluginInventory,
    current: PluginInventory,
    profile: str,
) -> PluginDriftReport:
    """Build a drift report from two inventories of the same profile.

    Identical plugins (same ``plugin_id``, ``version``, and ``state``)
    are excluded. Entries are sorted by ``(product_family, plugin_id)``
    ascending for stable output.

    Args:
        baseline: Inventory previously ack'd as the known-good state.
        current: Inventory captured at the most recent refresh.
        profile: Instance profile name (recorded on the report).

    Returns:
        A frozen ``PluginDriftReport`` describing every non-identical plugin.
    """
    by_id_b: dict[str, PluginInfo] = {p.plugin_id: p for p in baseline.plugins}
    by_id_c: dict[str, PluginInfo] = {p.plugin_id: p for p in current.plugins}
    all_ids = sorted(set(by_id_b) | set(by_id_c))
    entries: list[PluginDriftEntry] = []
    for plugin_id in all_ids:
        entry = _drift_entry(plugin_id, by_id_b.get(plugin_id), by_id_c.get(plugin_id))
        if entry is not None:
            entries.append(entry)
    entries.sort(key=lambda e: (e.product_family, e.plugin_id))
    return PluginDriftReport(
        profile=profile,
        baseline_captured_at=baseline.captured_at,
        current_captured_at=current.captured_at,
        entries=tuple(entries),
    )


def _drift_entry(
    plugin_id: str,
    baseline_info: PluginInfo | None,
    current_info: PluginInfo | None,
) -> PluginDriftEntry | None:
    """Build one PluginDriftEntry for a plugin_id, or None when identical.

    Returns:
        ``None`` when both sides are present with matching version and
        state. Otherwise an entry whose ``status`` is one of
        ``added`` / ``removed`` / ``version_changed`` / ``state_changed``.
    """
    if baseline_info is None and current_info is not None:
        return PluginDriftEntry(
            plugin_id=plugin_id,
            name=current_info.name,
            product_family=current_info.product_family,
            status="added",
            baseline_version=None,
            current_version=current_info.version,
            baseline_state=None,
            current_state=current_info.state,
        )
    if current_info is None and baseline_info is not None:
        return PluginDriftEntry(
            plugin_id=plugin_id,
            name=baseline_info.name,
            product_family=baseline_info.product_family,
            status="removed",
            baseline_version=baseline_info.version,
            current_version=None,
            baseline_state=baseline_info.state,
            current_state=None,
        )
    # Both sides present (the both-None case can't happen given all_ids construction).
    assert baseline_info is not None and current_info is not None
    if baseline_info.version == current_info.version and baseline_info.state == current_info.state:
        return None
    status: Literal["version_changed", "state_changed"] = (
        "version_changed" if baseline_info.version != current_info.version else "state_changed"
    )
    return PluginDriftEntry(
        plugin_id=plugin_id,
        name=current_info.name,
        product_family=current_info.product_family,
        status=status,
        baseline_version=baseline_info.version,
        current_version=current_info.version,
        baseline_state=baseline_info.state,
        current_state=current_info.state,
    )
```

- [ ] **Step 4: Run; expect PASS**

`.venv/Scripts/python -m pytest tests/test_plugins_drift.py -v --no-cov`

Expected: 14 tests pass.

- [ ] **Step 5: Verify**

```
.venv/Scripts/ruff check src/nexus/plugins/drift.py tests/test_plugins_drift.py
.venv/Scripts/pyright src/nexus/plugins/drift.py tests/test_plugins_drift.py
```

Both: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add src/nexus/plugins/drift.py tests/test_plugins_drift.py
git commit -m "feat(plugins): add PluginDriftReport + compute_drift

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `PluginBaselineNotFoundError`

**Files:**
- Modify: `src/nexus/plugins/errors.py`

- [ ] **Step 1: Modify `src/nexus/plugins/errors.py`**

Add the new error class at the bottom of the file and update `__all__`:

```python
__all__ = [
    "PluginAdvisoryDataError",
    "PluginBaselineNotFoundError",
    "PluginImpactError",
    "PluginScanError",
]
```

Add the class after `PluginImpactError`:

```python
class PluginBaselineNotFoundError(Exception):
    """Raised when nexus plugins drift runs without a saved baseline.

    The profile has no ``plugins.baseline.json``. User must run
    ``nexus plugins drift --ack`` to mark the current snapshot as the
    baseline first.

    Args:
        profile: Instance profile that is missing a baseline.
    """

    def __init__(self, profile: str) -> None:
        """Store the profile name and a human-readable message."""
        super().__init__(f"no plugin baseline saved for profile: {profile}")
        self.profile = profile
```

- [ ] **Step 2: Verify**

```
.venv/Scripts/ruff check src/nexus/plugins/errors.py
.venv/Scripts/pyright src/nexus/plugins/errors.py
.venv/Scripts/python -m pytest tests/test_plugins_errors.py -v --no-cov
```

All: 0 errors. Existing error tests should still pass.

- [ ] **Step 3: Commit**

```bash
git add src/nexus/plugins/errors.py
git commit -m "feat(plugins): add PluginBaselineNotFoundError

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Registry baseline I/O + tests

**Files:**
- Modify: `src/nexus/instances/registry.py`
- Modify: `tests/test_instances_registry.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_instances_registry.py`:

```python
def test_load_plugin_baseline_returns_none_when_missing(tmp_path: Path) -> None:
    """A profile dir exists but no plugins.baseline.json -> None."""
    registry = InstanceRegistry(tmp_path)
    registry.save(_meta("prod"))
    assert registry.load_plugin_baseline("prod") is None


def test_save_plugin_baseline_round_trip(tmp_path: Path) -> None:
    """save_plugin_baseline writes the inventory; load_plugin_baseline reads it back."""
    registry = InstanceRegistry(tmp_path)
    registry.save(_meta("prod"))
    inv = _inventory()
    registry.save_plugin_baseline("prod", inv)
    loaded = registry.load_plugin_baseline("prod")
    assert loaded is not None
    assert loaded.plugins == inv.plugins


def test_save_plugin_baseline_overwrites_existing(tmp_path: Path) -> None:
    """A second save replaces the first baseline."""
    registry = InstanceRegistry(tmp_path)
    registry.save(_meta("prod"))
    first = _inventory()
    registry.save_plugin_baseline("prod", first)
    second_plugin = PluginInfo(
        plugin_id="com.snc.other",
        name="Other",
        version="2.0.0",
        state="active",
        source="servicenow",
        product_family="ITSM",
        depends_on=(),
        sys_id="sys-other",
        installed_at=None,
    )
    second = PluginInventory(
        captured_at=datetime.now(UTC) + timedelta(days=1),
        sn_version="Xanadu",
        plugins=(second_plugin,),
    )
    registry.save_plugin_baseline("prod", second)
    loaded = registry.load_plugin_baseline("prod")
    assert loaded is not None
    assert len(loaded.plugins) == 1
    assert loaded.plugins[0].plugin_id == "com.snc.other"


def test_load_plugin_baseline_raises_when_profile_missing(tmp_path: Path) -> None:
    """Profile directory does not exist -> InstanceNotFoundError."""
    registry = InstanceRegistry(tmp_path)
    with pytest.raises(InstanceNotFoundError):
        registry.load_plugin_baseline("ghost")


def test_save_plugin_baseline_raises_when_profile_missing(tmp_path: Path) -> None:
    """save with no profile dir -> InstanceNotFoundError."""
    registry = InstanceRegistry(tmp_path)
    inv = _inventory()
    with pytest.raises(InstanceNotFoundError):
        registry.save_plugin_baseline("ghost", inv)
```

Verify that the existing test file has `_meta`, `_inventory` helpers and the imports for `PluginInfo`, `PluginInventory`, `InstanceNotFoundError`, `datetime`, `UTC`, `timedelta`. The test file's imports (line 7-15) already cover all of these. No new imports required at the top.

- [ ] **Step 2: Run; expect FAIL (AttributeError)**

`.venv/Scripts/python -m pytest tests/test_instances_registry.py -v -k "baseline" --no-cov`

Expected: `AttributeError: 'InstanceRegistry' object has no attribute 'load_plugin_baseline'`.

- [ ] **Step 3: Modify `src/nexus/instances/registry.py`**

Add a constant next to `_PLUGIN_INVENTORY` (around line 24):

```python
_PLUGIN_BASELINE = "plugins.baseline.json"
```

Add two methods next to `save_plugin_inventory` (after the existing method ends, before `_dir`):

```python
def load_plugin_baseline(self, profile: str) -> PluginInventory | None:
    """Read plugins.baseline.json for a profile if it exists.

    Args:
        profile: Profile name.

    Returns:
        PluginInventory or None if no baseline has been ack'd yet.

    Raises:
        InstanceNotFoundError: If the profile directory does not exist.
    """
    profile_dir = self._dir(profile)
    if not profile_dir.exists():
        raise InstanceNotFoundError(profile)
    baseline_file = profile_dir / _PLUGIN_BASELINE
    if not baseline_file.exists():
        return None
    return PluginInventory.model_validate_json(baseline_file.read_text(encoding="utf-8"))


def save_plugin_baseline(self, profile: str, inventory: PluginInventory) -> None:
    """Atomically write plugins.baseline.json for a profile.

    Writes to a temp file then renames to avoid partial writes on failure.

    Args:
        profile: Profile name.
        inventory: Inventory to record as the ack'd baseline.

    Raises:
        InstanceNotFoundError: If the profile directory does not exist.
    """
    profile_dir = self._dir(profile)
    if not profile_dir.exists():
        raise InstanceNotFoundError(profile)
    baseline_file = profile_dir / _PLUGIN_BASELINE
    fd, tmp = tempfile.mkstemp(dir=profile_dir, suffix=".tmp")
    try:
        with open(fd, "w", encoding="utf-8") as f:
            f.write(inventory.model_dump_json(indent=2))
        Path(tmp).replace(baseline_file)
    except OSError:
        Path(tmp).unlink(missing_ok=True)
        raise
```

- [ ] **Step 4: Run; expect PASS**

`.venv/Scripts/python -m pytest tests/test_instances_registry.py -v --no-cov`

Expected: all existing tests still pass + 5 new tests pass.

- [ ] **Step 5: Verify + commit**

```
.venv/Scripts/ruff check src/nexus/instances/registry.py tests/test_instances_registry.py
.venv/Scripts/pyright src/nexus/instances/registry.py tests/test_instances_registry.py
```

Both: 0 errors.

```bash
git add src/nexus/instances/registry.py tests/test_instances_registry.py
git commit -m "feat(instances): add load_plugin_baseline + save_plugin_baseline

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Public re-exports in `nexus.plugins.__init__`

**Files:**
- Modify: `src/nexus/plugins/__init__.py`

- [ ] **Step 1: Modify `src/nexus/plugins/__init__.py`**

Add the imports (sorted alphabetically with the existing `from nexus.plugins.diff import (...)` block). Insert the drift import after the diff block:

```python
from nexus.plugins.drift import (
    PluginDriftEntry,
    PluginDriftReport,
    compute_drift,
)
```

Update the `from nexus.plugins.errors import (...)` block to include the new error:

```python
from nexus.plugins.errors import (
    PluginAdvisoryDataError,
    PluginBaselineNotFoundError,
    PluginImpactError,
    PluginScanError,
)
```

Update `__all__` to add the new public symbols in alphabetical order:

```python
__all__ = [
    "AdvisoryDatabase",
    "AdvisoryFinding",
    "AdvisorySet",
    "AdvisoryType",
    "PluginAdvisoryDataError",
    "PluginBaselineNotFoundError",
    "PluginDiff",
    "PluginDiffEntry",
    "PluginDriftEntry",
    "PluginDriftReport",
    "PluginImpact",
    "PluginImpactError",
    "PluginInfo",
    "PluginInventory",
    "PluginScanError",
    "PluginScanner",
    "ProductFamily",
    "PromoteAction",
    "PromotionPlan",
    "ReverseDependency",
    "ScopeRecordCount",
    "Severity",
    "compute_advisories",
    "compute_diff",
    "compute_drift",
    "compute_impact",
    "orphan_candidates",
    "plugins_with_updates",
    "product_family_for",
    "project_to_promote_plan",
    "reverse_dependencies",
]
```

- [ ] **Step 2: Verify**

```
.venv/Scripts/ruff check src/nexus/plugins/__init__.py
.venv/Scripts/pyright src/nexus/plugins/__init__.py
.venv/Scripts/python -m pytest tests/test_plugins_drift.py -v --no-cov
```

All: 0 errors / all tests pass.

- [ ] **Step 3: Smoke-test the re-exports**

```
.venv/Scripts/python -c "from nexus.plugins import PluginDriftReport, PluginDriftEntry, compute_drift, PluginBaselineNotFoundError; print('ok')"
```

Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add src/nexus/plugins/__init__.py
git commit -m "feat(plugins): re-export drift symbols from public package

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: CLI `plugins_drift` command (basic + --ack)

**Files:**
- Modify: `src/nexus/cli.py`
- Create: `tests/test_cli_plugins_drift.py`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_cli_plugins_drift.py`:

```python
# tests/test_cli_plugins_drift.py
# Tests for the nexus plugins drift command.
# Author: Pierre Grothe
# Date: 2026-05-12
"""Tests for nexus plugins drift (audit baseline + current snapshots)."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nexus.cache import clear_cache
from nexus.cli import app
from nexus.config.paths import NexusPaths
from nexus.instances.models import InstanceMeta
from nexus.instances.registry import InstanceRegistry
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
    plugin_id: str,
    *,
    version: str = "1.0.0",
    state: str = "active",
    product_family: str = "ITSM",
) -> PluginInfo:
    return PluginInfo.model_validate(
        {
            "plugin_id": plugin_id,
            "name": plugin_id,
            "version": version,
            "state": state,
            "source": "servicenow",
            "product_family": product_family,
            "depends_on": (),
            "sys_id": f"sys-{plugin_id}",
            "installed_at": None,
        }
    )


def _seed_current(
    tmp_path: Path,
    profile: str,
    plugins: tuple[PluginInfo, ...] | None = None,
) -> None:
    """Write meta + plugins.json (current snapshot) for a profile."""
    paths = NexusPaths.from_env()
    registry = InstanceRegistry(paths.instances_dir)
    registry.save(_meta(profile))
    if plugins is not None:
        inv = PluginInventory(
            captured_at=datetime.now(UTC),
            sn_version="Xanadu",
            plugins=plugins,
        )
        registry.save_plugin_inventory(profile, inv)


def _seed_baseline(
    tmp_path: Path,
    profile: str,
    plugins: tuple[PluginInfo, ...],
) -> None:
    """Write plugins.baseline.json for a profile."""
    paths = NexusPaths.from_env()
    registry = InstanceRegistry(paths.instances_dir)
    inv = PluginInventory(
        captured_at=datetime.now(UTC),
        sn_version="Xanadu",
        plugins=plugins,
    )
    registry.save_plugin_baseline(profile, inv)


@pytest.fixture
def runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    monkeypatch.setenv("NEXUS_CONFIG_PATH", str(tmp_path / "config.yaml"))
    clear_cache(NexusPaths.from_env)
    return CliRunner()


def test_drift_errors_when_no_current_snapshot(runner: CliRunner, tmp_path: Path) -> None:
    """No plugins.json captured yet -> exit 1 with refresh hint."""
    _seed_current(tmp_path, "prod", plugins=None)
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "drift"])
    assert result.exit_code == 1
    assert "refresh" in result.output.lower()


def test_drift_errors_when_no_baseline_with_hint(runner: CliRunner, tmp_path: Path) -> None:
    """Current exists, no baseline -> exit 1 with --ack hint."""
    _seed_current(tmp_path, "prod", (_info("com.snc.x"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "drift"])
    assert result.exit_code == 1
    assert "--ack" in result.output


def test_drift_ack_sets_baseline(runner: CliRunner, tmp_path: Path) -> None:
    """--ack saves current snapshot as plugins.baseline.json."""
    _seed_current(tmp_path, "prod", (_info("com.snc.x"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "drift", "--ack"])
    assert result.exit_code == 0
    assert "Baseline set" in result.output
    paths = NexusPaths.from_env()
    registry = InstanceRegistry(paths.instances_dir)
    baseline = registry.load_plugin_baseline("prod")
    assert baseline is not None
    assert len(baseline.plugins) == 1
    assert baseline.plugins[0].plugin_id == "com.snc.x"


def test_drift_ack_errors_when_no_current_snapshot(runner: CliRunner, tmp_path: Path) -> None:
    """--ack with no plugins.json -> exit 1 with refresh hint."""
    _seed_current(tmp_path, "prod", plugins=None)
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "drift", "--ack"])
    assert result.exit_code == 1
    assert "refresh" in result.output.lower()


def test_drift_reports_no_drift_when_inventories_identical(
    runner: CliRunner, tmp_path: Path
) -> None:
    """Same plugin in baseline and current -> 'No drift detected.'"""
    plugins = (_info("com.snc.x"),)
    _seed_current(tmp_path, "prod", plugins)
    _seed_baseline(tmp_path, "prod", plugins)
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "drift"])
    assert result.exit_code == 0
    assert "No drift detected" in result.output


def test_drift_renders_added_removed_version_state_changes(
    runner: CliRunner, tmp_path: Path
) -> None:
    """Mixed drift renders DataTable with each status."""
    baseline = (
        _info("com.gone"),
        _info("com.flip", state="inactive"),
        _info("com.bump", version="1.0.0"),
    )
    current = (
        _info("com.new"),
        _info("com.flip", state="active"),
        _info("com.bump", version="2.0.0"),
    )
    _seed_baseline(tmp_path, "prod", baseline)
    _seed_current(tmp_path, "prod", current)
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "drift"])
    assert result.exit_code == 0
    assert "com.new" in result.output
    assert "com.gone" in result.output
    assert "com.flip" in result.output
    assert "com.bump" in result.output
```

- [ ] **Step 2: Run; expect FAIL**

`.venv/Scripts/python -m pytest tests/test_cli_plugins_drift.py -v --no-cov`

Expected: every test fails because the `drift` command does not exist yet (typer reports `No such command 'drift'`).

- [ ] **Step 3: Modify `src/nexus/cli.py`**

Add the imports for the drift symbols. Search for the existing `from nexus.plugins.diff import (...)` block (around line 55) and add the drift import after the diff block, keeping alphabetical sort:

```python
from nexus.plugins.drift import (
    PluginDriftEntry,
    PluginDriftReport,
    compute_drift,
)
```

Update the existing `from nexus.plugins.errors import (...)` block (around line 62) to include the new error:

```python
from nexus.plugins.errors import (
    PluginAdvisoryDataError,
    PluginBaselineNotFoundError,
    PluginImpactError,
)
```

Wait -- inspect the existing import block FIRST to see which errors are currently imported. The plan above assumes the file imports `PluginAdvisoryDataError, PluginImpactError`. If `PluginScanError` is also imported there (in cli.py), keep it. Add `PluginBaselineNotFoundError` to the imported set; do not drop the others.

Append the `plugins_drift` command at the end of the plugins commands block (after `plugins_orphans`, around cli.py:1925, BEFORE the `capture_app.callback` definition):

```python
@plugins_app.command("drift")
def plugins_drift(
    instance: Annotated[
        str,
        typer.Option("--instance", help="Instance profile (default: configured default)"),
    ] = "",
    ack: Annotated[
        bool,
        typer.Option(
            "--ack",
            help="Set the current snapshot as the new baseline and exit.",
        ),
    ] = False,
) -> None:
    """Show plugin drift on an instance since the last baseline."""
    meta, inventory = _load_inventory_or_exit(instance)
    paths = NexusPaths.from_env()
    registry = InstanceRegistry(paths.instances_dir)

    if ack:
        registry.save_plugin_baseline(meta.profile, inventory)
        captured = inventory.captured_at.strftime("%Y-%m-%d")
        console.print(
            Notice.info(
                f"Baseline set: {len(inventory.plugins)} plugins captured {captured}."
            )
        )
        return

    baseline = registry.load_plugin_baseline(meta.profile)
    if baseline is None:
        err_console.print(
            Notice.error(f"No baseline set for {meta.profile!r}.")
        )
        console.print(Hint(label="Set baseline", command="nexus plugins drift --ack"))
        raise typer.Exit(1)

    report = compute_drift(baseline, inventory, meta.profile)
    if not report.entries:
        console.print(Notice.info("No drift detected."))
        return

    rows: list[list[RenderableType]] = [
        [
            e.plugin_id,
            e.name,
            e.product_family,
            _drift_status_badge(e.status),
            (e.baseline_version or "-"),
            (e.current_version or "-"),
            (e.baseline_state or "-"),
            (e.current_state or "-"),
        ]
        for e in report.entries
    ]
    console.print(
        DataTable(
            title=f"Plugin drift: {meta.profile}",
            columns=[
                DataColumn(header="Plugin ID", width=32),
                DataColumn(header="Name", width=20),
                DataColumn(header="Product", width=14),
                DataColumn(header="Status", width=16),
                DataColumn(header="Baseline ver", width=12),
                DataColumn(header="Current ver", width=12),
                DataColumn(header="Baseline state", width=14),
                DataColumn(header="Current state", width=14),
            ],
            rows=rows,
        )
    )
    counts: dict[str, int] = {
        "added": 0,
        "removed": 0,
        "version_changed": 0,
        "state_changed": 0,
    }
    for entry in report.entries:
        counts[entry.status] += 1
    breakdown = ", ".join(f"{n} {k}" for k, n in counts.items() if n)
    console.print(Notice.info(f"{len(report.entries)} drift(s): {breakdown}"))
```

Add a small helper near the existing `_diff_status_badge` (in cli.py), placed alongside it:

```python
def _drift_status_badge(status: str) -> RenderableType:
    """Color-code a drift status for the DataTable cell."""
    if status == "added":
        return StatusBadge.ok(status)
    if status == "removed":
        return StatusBadge.warn(status)
    return StatusBadge.warn(status)
```

If `_diff_status_badge` does not exist, just inline the call: replace `_drift_status_badge(e.status)` with `StatusBadge.warn(e.status)` directly in the row construction.

- [ ] **Step 4: Run; expect PASS**

`.venv/Scripts/python -m pytest tests/test_cli_plugins_drift.py -v --no-cov`

Expected: all 6 tests pass.

- [ ] **Step 5: Verify + commit**

```
.venv/Scripts/ruff check src/nexus/cli.py tests/test_cli_plugins_drift.py
.venv/Scripts/pyright src/nexus/cli.py tests/test_cli_plugins_drift.py
```

Both: 0 errors.

```bash
git add src/nexus/cli.py tests/test_cli_plugins_drift.py
git commit -m "feat(cli): add nexus plugins drift (basic + --ack)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: `--format text|json` on `plugins_drift`

**Files:**
- Modify: `src/nexus/cli.py` (`plugins_drift`)
- Modify: `tests/test_cli_plugins_drift.py`

- [ ] **Step 1: Append failing tests**

```python
def test_drift_emits_json_when_format_flag_provided(
    runner: CliRunner, tmp_path: Path
) -> None:
    """--format json emits a PluginDriftReport JSON to stdout."""
    baseline = (_info("com.snc.x", version="1.0.0"),)
    current = (_info("com.snc.x", version="2.0.0"),)
    _seed_baseline(tmp_path, "prod", baseline)
    _seed_current(tmp_path, "prod", current)
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "drift", "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.output.strip().split("\n")[-1])
    assert payload["profile"] == "prod"
    assert "entries" in payload
    assert len(payload["entries"]) == 1
    assert payload["entries"][0]["status"] == "version_changed"


def test_drift_emits_empty_entries_json_when_no_drift(
    runner: CliRunner, tmp_path: Path
) -> None:
    """--format json emits {"entries": []} when no drift -- CI-parseable."""
    plugins = (_info("com.snc.x"),)
    _seed_baseline(tmp_path, "prod", plugins)
    _seed_current(tmp_path, "prod", plugins)
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "drift", "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.output.strip().split("\n")[-1])
    assert payload["entries"] == []


def test_drift_errors_on_unknown_format_value(runner: CliRunner, tmp_path: Path) -> None:
    """--format yaml exits 1 with the standard Unknown --format message."""
    _seed_current(tmp_path, "prod", (_info("com.snc.x"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "drift", "--format", "yaml"])
    assert result.exit_code == 1
    assert "Unknown --format" in result.output
```

- [ ] **Step 2: Run; expect FAIL**

`.venv/Scripts/python -m pytest tests/test_cli_plugins_drift.py -v -k "emits_json or errors_on_unknown_format" --no-cov`

Expected: failures -- the `--format` option does not exist on the drift command yet.

- [ ] **Step 3: Modify `plugins_drift` signature**

Add `output_format` parameter (after `ack`):

```python
output_format: Annotated[
    str,
    typer.Option("--format", help="Output format: text | json (default: text)"),
] = "text",
```

In the function body, add `_validate_format(output_format)` as the FIRST statement (before `_load_inventory_or_exit`).

In the `--ack` branch, no JSON output is emitted (ack is a state-change command, not a query). Leave the ack branch unchanged.

In the drift-report branch, BEFORE the "No drift detected." early-return and BEFORE the DataTable rendering, add:

```python
if output_format == "json":
    _emit_json(report)
    return
```

The JSON branch emits the report (including an empty `entries` tuple when there's no drift) for CI parseability. The text-mode "No drift detected." notice is preserved.

The drift command's final body shape becomes:

```python
def plugins_drift(...) -> None:
    _validate_format(output_format)
    meta, inventory = _load_inventory_or_exit(instance)
    paths = NexusPaths.from_env()
    registry = InstanceRegistry(paths.instances_dir)

    if ack:
        registry.save_plugin_baseline(meta.profile, inventory)
        captured = inventory.captured_at.strftime("%Y-%m-%d")
        console.print(Notice.info(f"Baseline set: ..."))
        return

    baseline = registry.load_plugin_baseline(meta.profile)
    if baseline is None:
        err_console.print(Notice.error(f"No baseline set for {meta.profile!r}."))
        console.print(Hint(label="Set baseline", command="nexus plugins drift --ack"))
        raise typer.Exit(1)

    report = compute_drift(baseline, inventory, meta.profile)

    if output_format == "json":
        _emit_json(report)
        return

    if not report.entries:
        console.print(Notice.info("No drift detected."))
        return

    # ... existing DataTable rendering ...
```

- [ ] **Step 4: Run; expect PASS**

`.venv/Scripts/python -m pytest tests/test_cli_plugins_drift.py -v --no-cov`

Expected: all 9 tests pass (6 existing + 3 new).

- [ ] **Step 5: Verify + commit**

```
.venv/Scripts/ruff check src/nexus/cli.py tests/test_cli_plugins_drift.py
.venv/Scripts/pyright src/nexus/cli.py tests/test_cli_plugins_drift.py
```

Both: 0 errors.

```bash
git add src/nexus/cli.py tests/test_cli_plugins_drift.py
git commit -m "feat(cli): --format json on nexus plugins drift

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: `--strict` on `plugins_drift`

**Files:**
- Modify: `src/nexus/cli.py` (`plugins_drift`)
- Modify: `tests/test_cli_plugins_drift.py`

- [ ] **Step 1: Append failing tests**

```python
def test_drift_strict_exits_1_when_drift_detected(runner: CliRunner, tmp_path: Path) -> None:
    """--strict + drift present -> exit 1 after rendering."""
    baseline = (_info("com.snc.x", version="1.0.0"),)
    current = (_info("com.snc.x", version="2.0.0"),)
    _seed_baseline(tmp_path, "prod", baseline)
    _seed_current(tmp_path, "prod", current)
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "drift", "--strict"])
    assert result.exit_code == 1


def test_drift_strict_exits_0_when_no_drift(runner: CliRunner, tmp_path: Path) -> None:
    """--strict + no drift -> exit 0."""
    plugins = (_info("com.snc.x"),)
    _seed_baseline(tmp_path, "prod", plugins)
    _seed_current(tmp_path, "prod", plugins)
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "drift", "--strict"])
    assert result.exit_code == 0
    assert "No drift detected" in result.output


def test_drift_strict_json_emits_report_and_exits_1(
    runner: CliRunner, tmp_path: Path
) -> None:
    """--strict --format json with drift -> emits JSON to stdout, exits 1."""
    baseline = (_info("com.snc.x", version="1.0.0"),)
    current = (_info("com.snc.x", version="2.0.0"),)
    _seed_baseline(tmp_path, "prod", baseline)
    _seed_current(tmp_path, "prod", current)
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "drift", "--strict", "--format", "json"])
    assert result.exit_code == 1
    payload = json.loads(result.output.strip().split("\n")[-1])
    assert len(payload["entries"]) == 1
```

- [ ] **Step 2: Run; expect FAIL**

`.venv/Scripts/python -m pytest tests/test_cli_plugins_drift.py -v -k "strict" --no-cov`

Expected: failures -- the `--strict` option does not exist on the drift command yet.

- [ ] **Step 3: Modify `plugins_drift` signature**

Add `strict` parameter (after `output_format`):

```python
strict: Annotated[
    bool,
    typer.Option(
        "--strict",
        help="Exit with code 1 if any drift is detected.",
    ),
] = False,
```

The exit-1 check must fire in BOTH the JSON path (after `_emit_json`) and the text path (after the DataTable rendering). It must NOT fire when `report.entries` is empty (text path's "No drift detected." early-return already handles that; JSON path needs an explicit guard).

JSON branch:

```python
if output_format == "json":
    _emit_json(report)
    if strict and report.entries:
        raise typer.Exit(1)
    return
```

Text branch's end (after the DataTable + summary Notice):

```python
if strict and report.entries:
    raise typer.Exit(1)
```

The "No drift detected." early-return is reached only when `report.entries` is empty, so strict exits 0 in that path naturally (the `if strict and report.entries` line is never reached). No additional guard needed there.

- [ ] **Step 4: Run; expect PASS**

`.venv/Scripts/python -m pytest tests/test_cli_plugins_drift.py -v --no-cov`

Expected: all 12 tests pass (9 existing + 3 new).

- [ ] **Step 5: Verify + commit**

```
.venv/Scripts/ruff check src/nexus/cli.py tests/test_cli_plugins_drift.py
.venv/Scripts/pyright src/nexus/cli.py tests/test_cli_plugins_drift.py
```

Both: 0 errors.

```bash
git add src/nexus/cli.py tests/test_cli_plugins_drift.py
git commit -m "feat(cli): --strict on nexus plugins drift

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Black + ratchet + PR

**Files:**
- Modify: `.ratchet.json`

- [ ] **Step 1: Black**

```
.venv/Scripts/black src/nexus/plugins/drift.py src/nexus/plugins/errors.py src/nexus/plugins/__init__.py src/nexus/instances/registry.py src/nexus/cli.py tests/test_plugins_drift.py tests/test_cli_plugins_drift.py tests/test_instances_registry.py
```

- [ ] **Step 2: Full quality gate**

```
.venv/Scripts/ruff check src tests            # 0 violations
.venv/Scripts/mypy src/nexus/                 # 0 errors
.venv/Scripts/pyright src/nexus/              # 0 errors
.venv/Scripts/python -m pytest --no-cov --ignore=tests/test_updater_runner.py
# Expected: all new tests pass; 4 pre-existing failures unchanged
```

- [ ] **Step 3: Measure coverage**

```
.venv/Scripts/python -m pytest --ignore=tests/test_updater_runner.py --cov=nexus --cov-report=json --cov-fail-under=0
```

Extract numbers for these modules from `coverage.json`:
- `src\nexus\cli.py`
- `src\nexus\plugins\drift.py` (new)
- `src\nexus\plugins\errors.py`
- `src\nexus\instances\registry.py`

Use this Python one-liner (PowerShell-safe via a temp script):

```python
# extract_cov.py (one-off; delete after)
import json

with open("coverage.json") as f:
    data = json.load(f)
files = data["files"]
for path in [
    r"src\nexus\cli.py",
    r"src\nexus\plugins\drift.py",
    r"src\nexus\plugins\errors.py",
    r"src\nexus\instances\registry.py",
]:
    summary = files[path]["summary"]
    print(f"{path}: {summary['covered_lines']} / {summary['num_statements']}")
```

Run `.venv/Scripts/python extract_cov.py`, capture the output, then `rm extract_cov.py`.

If `coverage.json` was tracked in the repo, restore it: `git checkout coverage.json`.

- [ ] **Step 4: Update `.ratchet.json`**

Update the relevant module entries with the new values. Do not change other entries.

```jsonc
{
  ...
  "modules": {
    ...
    "nexus.cli": {"covered_lines": <new>, "total_lines": <new>},
    "nexus.instances.registry": {"covered_lines": <new>, "total_lines": <new>},
    "nexus.plugins.drift": {"covered_lines": <new>, "total_lines": <new>},  // NEW entry
    ...
  }
}
```

`nexus.plugins.drift` is a NEW entry, not an update.

`nexus.plugins.errors` may or may not have a ratchet entry already. If it does, update it. If not (e.g., if the module wasn't tracked before), add a new entry. Use the same logic as the original `.ratchet.json` followed for existing modules.

Ratchet rule: `covered_lines` must be >= the previous value for each module; `total_lines` reflects the new module size.

- [ ] **Step 5: Commit**

```bash
git add .ratchet.json src/nexus/plugins/ src/nexus/instances/registry.py src/nexus/cli.py tests/
git commit -m "chore(plugins): black formatting + refresh ratchet for drift

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 6: Push + open PR**

```bash
git push -u origin feat/plugins-drift
gh pr create --base feat/plugins-cleanups --title "feat(plugins): H drift detection (audit baseline + current snapshot comparison)" --body "$(cat <<'EOF'
## Summary

Sub-project H of plugin management: single-instance over-time drift detection.

Adds `nexus plugins drift` to compare a manually-ack'd baseline `PluginInventory` against the current snapshot, mirroring the 4 statuses from `nexus plugins diff`: added, removed, version_changed, state_changed.

**Stacked on `feat/plugins-cleanups` (PR #18 -- sub-project G).** Once G merges to main, this PR can be retargeted to main.

### Architecture
- New module `nexus.plugins.drift` -- pure functions, mirror of `nexus.plugins.diff`
- New error `PluginBaselineNotFoundError`
- Registry methods `load_plugin_baseline` / `save_plugin_baseline` -- atomic-rename pattern, parallel to existing `*_plugin_inventory` methods
- New CLI command `nexus plugins drift` with `--ack`, `--format text|json`, `--strict`

### UX
- `nexus plugins drift --ack` sets the current snapshot as the audit baseline (stored as `plugins.baseline.json` alongside `plugins.json`)
- `nexus plugins drift` reports drift since the last ack
- No baseline yet -> exit 1 with hint to run `--ack`
- `--format json` for CI consumption
- `--strict` exits 1 when drift is detected (matches G's ruff/mypy/black convention)

Spec: `docs/superpowers/specs/2026-05-12-plugin-drift-design.md`
Plan: `docs/superpowers/plans/2026-05-12-plugin-drift.md`

## Test plan
- [x] 14 new tests in `tests/test_plugins_drift.py` (pure-function tests for compute_drift)
- [x] 5 new tests in `tests/test_instances_registry.py` (baseline round-trip)
- [x] 12 new tests in `tests/test_cli_plugins_drift.py` (CLI: no-baseline, --ack, drift report, --format, --strict)
- [x] Full suite green except the 4 pre-existing failures
- [x] ruff / black / mypy strict / pyright strict clean
- [x] Ratchet updated for cli + registry; drift module added
EOF
)"
```

Note: `--base feat/plugins-cleanups` because H stacks on G's PR. When G merges, GitHub will auto-retarget H to main.

---

## Self-Review Summary

**Spec coverage:**
- Storage (`plugins.baseline.json` alongside `plugins.json`) -> Task 3
- `PluginDriftEntry` / `PluginDriftReport` / `compute_drift` -> Task 1
- `PluginBaselineNotFoundError` -> Task 2
- Registry `load_plugin_baseline` / `save_plugin_baseline` -> Task 3
- Public re-exports -> Task 4
- CLI command (basic + --ack) -> Task 5
- CLI `--format text|json` -> Task 6
- CLI `--strict` -> Task 7
- Behavior table from spec covered by tests in Tasks 5/6/7
- Quality gate + PR -> Task 8

**Placeholder scan:** The `<new>` markers in Task 8's ratchet block are intentionally pinned to "measure then fill in" -- explicit instruction matching the G plan's pattern. No "TBD" or "TODO" markers in the body.

**Type consistency:**
- `PluginDriftEntry` field names match between model definition (Task 1), test factory (Task 1), CLI rendering (Task 5), and JSON test assertions (Task 6).
- `PluginDriftReport.profile` (singular, not `profile_a/profile_b`) matches between Task 1's model, Task 5's CLI use, and Task 6's JSON test assertion.
- `compute_drift(baseline, current, profile)` signature consistent between definition (Task 1) and call sites (Task 5).
- Status set: `added | removed | version_changed | state_changed` consistent across model, test cases, CLI status counts dict, and JSON test assertions.
- Registry method names `load_plugin_baseline` / `save_plugin_baseline` consistent between definition (Task 3) and call sites (Task 5).
- `PluginBaselineNotFoundError` is defined in Task 2 but NEVER raised by the CLI; the CLI handles the "no baseline" case via an `if baseline is None` check returning `Exit(1)` with a hint. The error class exists for callers who may use the registry directly. This is intentional (the registry's `load_plugin_baseline` returns `None`, not raises).
