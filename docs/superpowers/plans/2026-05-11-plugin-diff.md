# Plugin Diff + Promote Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship sub-project B of the plugin management roadmap: two new CLI commands, `nexus plugins diff <a> <b>` and `nexus plugins promote <src> --to <dst>`, backed by a single new pure-function module `src/nexus/plugins/diff.py`.

**Architecture:** One new file (`diff.py`) in the existing `src/nexus/plugins/` layer holds four frozen Pydantic models (`PluginDiffEntry`, `PluginDiff`, `PromoteAction`, `PromotionPlan`) plus two pure functions (`compute_diff` and `project_to_promote_plan`). Both new CLI commands extend the existing `plugins_app` in `cli.py` and render through the `nexus.ui` component library. The promote plan is written as YAML via the project's existing `_yaml` alias.

**Tech Stack:** Python 3.14, Pydantic v2 (frozen), Typer, Rich (via `nexus.ui`), `packaging.version`, PyYAML, pytest.

**Spec:** `docs/superpowers/specs/2026-05-11-plugin-diff-design.md`

---

## File structure

New files:

```
src/nexus/plugins/diff.py             -- 4 models + 2 pure functions
tests/test_plugins_diff.py            -- pure-function unit tests (~14 tests)
tests/test_cli_plugins_diff.py        -- CliRunner integration tests (~10 tests)
```

Modified files:

```
src/nexus/plugins/__init__.py         -- re-export new public names
src/nexus/cli.py                      -- add diff + promote subcommands;
                                         update _PLUGINS_HELP
.ratchet.json                         -- baseline for diff.py + bumped cli.py
```

---

## Task 1: Pydantic models

**Files:**
- Create: `src/nexus/plugins/diff.py` (models only)
- Create: `tests/test_plugins_diff.py` (model tests only)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_plugins_diff.py
# Tests for cross-instance plugin diff and promote-plan projection.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for PluginDiff / PromotionPlan models and pure functions."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from nexus.plugins.diff import (
    PluginDiff,
    PluginDiffEntry,
    PromoteAction,
    PromotionPlan,
)

__all__: list[str] = []


def _entry(**overrides: object) -> PluginDiffEntry:
    defaults: dict[str, object] = {
        "plugin_id": "com.snc.incident",
        "name": "Incident Management",
        "product_family": "ITSM",
        "status": "version_mismatch",
        "a_version": "1.2.0",
        "b_version": "1.0.0",
        "a_state": "active",
        "b_state": "active",
    }
    defaults.update(overrides)
    return PluginDiffEntry.model_validate(defaults)


def _action(**overrides: object) -> PromoteAction:
    defaults: dict[str, object] = {
        "action": "upgrade",
        "plugin_id": "com.snc.incident",
        "name": "Incident Management",
        "product_family": "ITSM",
        "target_version": "1.2.0",
        "current_version": "1.0.0",
    }
    defaults.update(overrides)
    return PromoteAction.model_validate(defaults)


def test_plugin_diff_entry_construction_with_required_fields() -> None:
    entry = _entry()
    assert entry.plugin_id == "com.snc.incident"
    assert entry.status == "version_mismatch"


def test_plugin_diff_entry_is_frozen() -> None:
    entry = _entry()
    with pytest.raises(ValidationError):
        entry.plugin_id = "renamed"


def test_plugin_diff_entry_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        _entry(status="weird")


def test_plugin_diff_entry_accepts_none_for_a_fields_when_only_in_b() -> None:
    entry = _entry(status="only_in_b", a_version=None, a_state=None)
    assert entry.a_version is None
    assert entry.a_state is None


def test_plugin_diff_holds_profiles_and_captured_at_pair() -> None:
    now = datetime.now(UTC)
    diff = PluginDiff(
        profile_a="prod",
        profile_b="dev",
        captured_at_a=now,
        captured_at_b=now,
        entries=(_entry(),),
    )
    assert diff.profile_a == "prod"
    assert diff.profile_b == "dev"
    assert len(diff.entries) == 1


def test_plugin_diff_round_trips_through_json() -> None:
    now = datetime.now(UTC)
    diff = PluginDiff(
        profile_a="prod",
        profile_b="dev",
        captured_at_a=now,
        captured_at_b=now,
        entries=(_entry(),),
    )
    re = PluginDiff.model_validate_json(diff.model_dump_json())
    assert re == diff


def test_promote_action_construction_with_required_fields() -> None:
    action = _action()
    assert action.action == "upgrade"
    assert action.current_version == "1.0.0"


def test_promote_action_is_frozen() -> None:
    action = _action()
    with pytest.raises(ValidationError):
        action.plugin_id = "renamed"


def test_promote_action_rejects_unknown_action() -> None:
    with pytest.raises(ValidationError):
        _action(action="delete")


def test_promote_action_install_has_no_current_version() -> None:
    install = _action(action="install", current_version=None)
    assert install.current_version is None


def test_promotion_plan_holds_profiles_and_actions() -> None:
    plan = PromotionPlan(
        source_profile="prod",
        target_profile="dev",
        actions=(_action(),),
    )
    assert plan.source_profile == "prod"
    assert plan.actions[0].action == "upgrade"


def test_promotion_plan_round_trips_through_json() -> None:
    plan = PromotionPlan(
        source_profile="prod",
        target_profile="dev",
        actions=(_action(),),
    )
    re = PromotionPlan.model_validate_json(plan.model_dump_json())
    assert re == plan
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_plugins_diff.py -v --no-cov`
Expected: FAIL on missing module `nexus.plugins.diff`.

- [ ] **Step 3: Implement models**

```python
# src/nexus/plugins/diff.py
# Cross-instance plugin diff + promote-plan logic.
# Author: Pierre Grothe
# Date: 2026-05-11
"""PluginDiff and PromotionPlan models plus pure-function builders.

Consumes ``PluginInventory`` produced by sub-project A. No I/O; the CLI
layer is responsible for reading inventories from disk and writing the
YAML output. ``compute_diff`` and ``project_to_promote_plan`` are pure
functions that operate on already-loaded inventories.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from nexus.config.types import UtcDatetime

__all__ = [
    "PluginDiff",
    "PluginDiffEntry",
    "PromoteAction",
    "PromotionPlan",
]

_FROZEN = ConfigDict(frozen=True, strict=True, extra="forbid")


class PluginDiffEntry(BaseModel):
    """One row of a cross-instance plugin diff.

    Attributes:
        plugin_id: Canonical SN plugin identifier.
        name: Display name (from whichever inventory had the entry).
        product_family: Curated product family or ``Uncategorized``.
        status: Why this row appears in the diff.
        a_version: Version on instance A, or ``None`` when only_in_b.
        b_version: Version on instance B, or ``None`` when only_in_a.
        a_state: State on A, or ``None`` when only_in_b.
        b_state: State on B, or ``None`` when only_in_a.
    """

    model_config = _FROZEN

    plugin_id: str
    name: str
    product_family: str
    status: Literal[
        "only_in_a", "only_in_b", "version_mismatch", "state_mismatch"
    ]
    a_version: str | None
    b_version: str | None
    a_state: Literal["active", "inactive"] | None
    b_state: Literal["active", "inactive"] | None


class PluginDiff(BaseModel):
    """Full diff of two plugin inventories.

    Attributes:
        profile_a: Source instance profile name.
        profile_b: Target instance profile name.
        captured_at_a: When inventory A was captured (UTC).
        captured_at_b: When inventory B was captured (UTC).
        entries: All non-identical plugins in stable ``(product_family,
            plugin_id)`` order.
    """

    model_config = _FROZEN

    profile_a: str
    profile_b: str
    captured_at_a: UtcDatetime
    captured_at_b: UtcDatetime
    entries: tuple[PluginDiffEntry, ...]


class PromoteAction(BaseModel):
    """One step in a promotion plan.

    Attributes:
        action: ``install``, ``activate``, or ``upgrade``.
        plugin_id: Canonical SN plugin identifier.
        name: Display name from the source inventory.
        product_family: Curated product family.
        target_version: Version present on the source instance.
        current_version: Version present on the target instance, or
            ``None`` when the action is ``install``.
    """

    model_config = _FROZEN

    action: Literal["install", "activate", "upgrade"]
    plugin_id: str
    name: str
    product_family: str
    target_version: str
    current_version: str | None


class PromotionPlan(BaseModel):
    """Actions required to make ``target_profile`` match ``source_profile``.

    Attributes:
        source_profile: Profile the actions originate from.
        target_profile: Profile the actions are applied to.
        actions: All actions in stable ``(install < activate < upgrade,
            product_family, plugin_id)`` order.
    """

    model_config = _FROZEN

    source_profile: str
    target_profile: str
    actions: tuple[PromoteAction, ...]
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_plugins_diff.py -v --no-cov`
Expected: 12 PASS.

- [ ] **Step 5: Run linters**

```
ruff check src/nexus/plugins/diff.py tests/test_plugins_diff.py
pyright src/nexus/plugins/diff.py tests/test_plugins_diff.py
mypy src/nexus/plugins/diff.py tests/test_plugins_diff.py
```
Expected: all clean.

- [ ] **Step 6: Commit**

```bash
git add src/nexus/plugins/diff.py tests/test_plugins_diff.py
git commit -m "feat(plugins): add diff and promote-plan models"
```

---

## Task 2: compute_diff

**Files:**
- Modify: `src/nexus/plugins/diff.py` (append the function)
- Modify: `tests/test_plugins_diff.py` (append tests)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_plugins_diff.py`:

```python
from nexus.plugins.diff import compute_diff
from nexus.plugins.models import PluginInfo, PluginInventory


def _info(
    plugin_id: str,
    *,
    version: str = "1.0.0",
    state: str = "active",
    product_family: str = "ITSM",
    name: str = "",
) -> PluginInfo:
    return PluginInfo.model_validate(
        {
            "plugin_id": plugin_id,
            "name": name or plugin_id,
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


def test_compute_diff_returns_empty_entries_for_identical_inventories() -> None:
    inv = _inventory(_info("com.snc.incident"))
    diff = compute_diff(inv, inv, profile_a="prod", profile_b="dev")
    assert diff.entries == ()
    assert diff.profile_a == "prod"
    assert diff.profile_b == "dev"


def test_compute_diff_reports_only_in_a_when_a_has_extra_plugin() -> None:
    a = _inventory(_info("com.snc.incident"), _info("com.snc.problem"))
    b = _inventory(_info("com.snc.incident"))
    diff = compute_diff(a, b, profile_a="prod", profile_b="dev")
    assert len(diff.entries) == 1
    only = diff.entries[0]
    assert only.plugin_id == "com.snc.problem"
    assert only.status == "only_in_a"
    assert only.a_version == "1.0.0"
    assert only.b_version is None
    assert only.a_state == "active"
    assert only.b_state is None


def test_compute_diff_reports_only_in_b_when_b_has_extra_plugin() -> None:
    a = _inventory(_info("com.snc.incident"))
    b = _inventory(_info("com.snc.incident"), _info("com.snc.problem"))
    diff = compute_diff(a, b, profile_a="prod", profile_b="dev")
    only = next(e for e in diff.entries if e.plugin_id == "com.snc.problem")
    assert only.status == "only_in_b"
    assert only.a_version is None
    assert only.b_version == "1.0.0"


def test_compute_diff_reports_version_mismatch() -> None:
    a = _inventory(_info("com.snc.incident", version="1.2.0"))
    b = _inventory(_info("com.snc.incident", version="1.0.0"))
    diff = compute_diff(a, b, profile_a="prod", profile_b="dev")
    assert len(diff.entries) == 1
    e = diff.entries[0]
    assert e.status == "version_mismatch"
    assert e.a_version == "1.2.0"
    assert e.b_version == "1.0.0"
    assert e.a_state == "active"
    assert e.b_state == "active"


def test_compute_diff_reports_state_mismatch() -> None:
    a = _inventory(_info("com.snc.incident", state="active"))
    b = _inventory(_info("com.snc.incident", state="inactive"))
    diff = compute_diff(a, b, profile_a="prod", profile_b="dev")
    assert len(diff.entries) == 1
    e = diff.entries[0]
    assert e.status == "state_mismatch"
    assert e.a_state == "active"
    assert e.b_state == "inactive"


def test_compute_diff_sorts_entries_by_product_then_plugin_id() -> None:
    a = _inventory(
        _info("com.snc.discovery", product_family="ITOM"),
        _info("com.snc.problem", product_family="ITSM"),
        _info("com.snc.incident", product_family="ITSM"),
    )
    b = _inventory()
    diff = compute_diff(a, b, profile_a="prod", profile_b="dev")
    ids = [e.plugin_id for e in diff.entries]
    assert ids == ["com.snc.discovery", "com.snc.incident", "com.snc.problem"]
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_plugins_diff.py -v --no-cov -k compute_diff`
Expected: FAIL on missing `compute_diff`.

- [ ] **Step 3: Implement `compute_diff`**

Append to `src/nexus/plugins/diff.py`:

```python
from nexus.plugins.models import PluginInfo, PluginInventory


def compute_diff(
    a: PluginInventory,
    b: PluginInventory,
    profile_a: str,
    profile_b: str,
) -> PluginDiff:
    """Set-diff two plugin inventories.

    Identical plugins (same ``plugin_id``, ``version``, and ``state``)
    are excluded from the result. Entries are returned in stable
    ``(product_family, plugin_id)`` order.

    Args:
        a: Inventory captured from the first instance.
        b: Inventory captured from the second instance.
        profile_a: Profile name of instance A (recorded on the diff).
        profile_b: Profile name of instance B (recorded on the diff).

    Returns:
        A frozen ``PluginDiff`` describing every non-identical plugin.
    """
    by_id_a: dict[str, PluginInfo] = {p.plugin_id: p for p in a.plugins}
    by_id_b: dict[str, PluginInfo] = {p.plugin_id: p for p in b.plugins}
    all_ids = sorted(set(by_id_a) | set(by_id_b))
    entries: list[PluginDiffEntry] = []
    for plugin_id in all_ids:
        a_info = by_id_a.get(plugin_id)
        b_info = by_id_b.get(plugin_id)
        entry = _diff_entry(plugin_id, a_info, b_info)
        if entry is not None:
            entries.append(entry)
    entries.sort(key=lambda e: (e.product_family, e.plugin_id))
    return PluginDiff(
        profile_a=profile_a,
        profile_b=profile_b,
        captured_at_a=a.captured_at,
        captured_at_b=b.captured_at,
        entries=tuple(entries),
    )


def _diff_entry(
    plugin_id: str, a: PluginInfo | None, b: PluginInfo | None
) -> PluginDiffEntry | None:
    """Build one diff entry, or return ``None`` when a and b are identical."""
    if a is None and b is not None:
        return PluginDiffEntry(
            plugin_id=plugin_id,
            name=b.name,
            product_family=b.product_family,
            status="only_in_b",
            a_version=None,
            b_version=b.version,
            a_state=None,
            b_state=b.state,
        )
    if b is None and a is not None:
        return PluginDiffEntry(
            plugin_id=plugin_id,
            name=a.name,
            product_family=a.product_family,
            status="only_in_a",
            a_version=a.version,
            b_version=None,
            a_state=a.state,
            b_state=None,
        )
    if a is None or b is None:
        return None  # both None is impossible by construction
    if a.version != b.version:
        status: Literal[
            "only_in_a", "only_in_b", "version_mismatch", "state_mismatch"
        ] = "version_mismatch"
    elif a.state != b.state:
        status = "state_mismatch"
    else:
        return None
    return PluginDiffEntry(
        plugin_id=plugin_id,
        name=a.name,
        product_family=a.product_family,
        status=status,
        a_version=a.version,
        b_version=b.version,
        a_state=a.state,
        b_state=b.state,
    )
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_plugins_diff.py -v --no-cov -k compute_diff`
Expected: 6 PASS.

- [ ] **Step 5: Run linters**

```
ruff check src/nexus/plugins/diff.py tests/test_plugins_diff.py
pyright src/nexus/plugins/diff.py tests/test_plugins_diff.py
mypy src/nexus/plugins/diff.py tests/test_plugins_diff.py
```
Expected: all clean.

- [ ] **Step 6: Commit**

```bash
git add src/nexus/plugins/diff.py tests/test_plugins_diff.py
git commit -m "feat(plugins): add compute_diff for cross-instance comparison"
```

---

## Task 3: project_to_promote_plan

**Files:**
- Modify: `src/nexus/plugins/diff.py` (append the function)
- Modify: `tests/test_plugins_diff.py` (append tests)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_plugins_diff.py`:

```python
from nexus.plugins.diff import project_to_promote_plan


def test_project_to_promote_plan_includes_install_for_only_in_a() -> None:
    diff = compute_diff(
        _inventory(_info("com.snc.problem")),
        _inventory(),
        profile_a="prod",
        profile_b="dev",
    )
    plan = project_to_promote_plan(diff)
    assert plan.source_profile == "prod"
    assert plan.target_profile == "dev"
    assert len(plan.actions) == 1
    a = plan.actions[0]
    assert a.action == "install"
    assert a.plugin_id == "com.snc.problem"
    assert a.target_version == "1.0.0"
    assert a.current_version is None


def test_project_to_promote_plan_includes_activate_for_active_on_a_inactive_on_b() -> None:
    diff = compute_diff(
        _inventory(_info("com.snc.problem", state="active")),
        _inventory(_info("com.snc.problem", state="inactive")),
        profile_a="prod",
        profile_b="dev",
    )
    plan = project_to_promote_plan(diff)
    assert len(plan.actions) == 1
    assert plan.actions[0].action == "activate"


def test_project_to_promote_plan_skips_deactivate_direction() -> None:
    diff = compute_diff(
        _inventory(_info("com.snc.problem", state="inactive")),
        _inventory(_info("com.snc.problem", state="active")),
        profile_a="prod",
        profile_b="dev",
    )
    plan = project_to_promote_plan(diff)
    assert plan.actions == ()


def test_project_to_promote_plan_includes_upgrade_when_a_version_newer() -> None:
    diff = compute_diff(
        _inventory(_info("com.snc.incident", version="2.0.0")),
        _inventory(_info("com.snc.incident", version="1.0.0")),
        profile_a="prod",
        profile_b="dev",
    )
    plan = project_to_promote_plan(diff)
    assert len(plan.actions) == 1
    a = plan.actions[0]
    assert a.action == "upgrade"
    assert a.target_version == "2.0.0"
    assert a.current_version == "1.0.0"


def test_project_to_promote_plan_skips_downgrade_when_a_version_older() -> None:
    diff = compute_diff(
        _inventory(_info("com.snc.incident", version="1.0.0")),
        _inventory(_info("com.snc.incident", version="2.0.0")),
        profile_a="prod",
        profile_b="dev",
    )
    plan = project_to_promote_plan(diff)
    assert plan.actions == ()


def test_project_to_promote_plan_skips_only_in_b() -> None:
    diff = compute_diff(
        _inventory(),
        _inventory(_info("com.snc.problem")),
        profile_a="prod",
        profile_b="dev",
    )
    plan = project_to_promote_plan(diff)
    assert plan.actions == ()


def test_project_to_promote_plan_sorts_install_then_activate_then_upgrade() -> None:
    diff = compute_diff(
        _inventory(
            _info("com.snc.aaa"),  # only_in_a -> install
            _info("com.snc.bbb", version="2.0.0"),  # upgrade
            _info("com.snc.ccc", state="active"),  # activate
        ),
        _inventory(
            _info("com.snc.bbb", version="1.0.0"),
            _info("com.snc.ccc", state="inactive"),
        ),
        profile_a="prod",
        profile_b="dev",
    )
    plan = project_to_promote_plan(diff)
    actions = [a.action for a in plan.actions]
    assert actions == ["install", "activate", "upgrade"]


def test_project_to_promote_plan_handles_unparseable_versions_safely() -> None:
    """Unparseable versions yield a diff entry but no upgrade action."""
    diff = compute_diff(
        _inventory(_info("com.snc.incident", version="rolling-feature-x")),
        _inventory(_info("com.snc.incident", version="rolling-feature-y")),
        profile_a="prod",
        profile_b="dev",
    )
    plan = project_to_promote_plan(diff)
    assert plan.actions == ()
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_plugins_diff.py -v --no-cov -k project_to_promote_plan`
Expected: FAIL on missing `project_to_promote_plan`.

- [ ] **Step 3: Implement `project_to_promote_plan`**

At the top of `src/nexus/plugins/diff.py`, add the import:

```python
from packaging.version import InvalidVersion, parse as parse_version
```

Append to `src/nexus/plugins/diff.py`:

```python
_ACTION_ORDER: dict[str, int] = {"install": 0, "activate": 1, "upgrade": 2}


def project_to_promote_plan(diff: PluginDiff) -> PromotionPlan:
    """Project a diff into an additive set of install/activate/upgrade actions.

    Rules:
        - ``only_in_a`` -> ``install``.
        - ``state_mismatch`` where ``a_state == "active"`` and
          ``b_state == "inactive"`` -> ``activate``.
        - ``version_mismatch`` where ``a_version`` is strictly newer than
          ``b_version`` per ``packaging.version.parse`` -> ``upgrade``.
        - All other entries (deactivations, downgrades, ``only_in_b``,
          and entries with unparseable versions on either side) are
          skipped.

    Args:
        diff: The diff produced by ``compute_diff``.

    Returns:
        A frozen ``PromotionPlan`` whose actions are sorted by
        ``(install < activate < upgrade, product_family, plugin_id)``.
    """
    actions: list[PromoteAction] = []
    for entry in diff.entries:
        action = _project_entry(entry)
        if action is not None:
            actions.append(action)
    actions.sort(
        key=lambda a: (_ACTION_ORDER[a.action], a.product_family, a.plugin_id)
    )
    return PromotionPlan(
        source_profile=diff.profile_a,
        target_profile=diff.profile_b,
        actions=tuple(actions),
    )


def _project_entry(entry: PluginDiffEntry) -> PromoteAction | None:
    """Return the matching PromoteAction for a diff entry, or None to skip."""
    if entry.status == "only_in_a" and entry.a_version is not None:
        return PromoteAction(
            action="install",
            plugin_id=entry.plugin_id,
            name=entry.name,
            product_family=entry.product_family,
            target_version=entry.a_version,
            current_version=None,
        )
    if (
        entry.status == "state_mismatch"
        and entry.a_state == "active"
        and entry.b_state == "inactive"
        and entry.a_version is not None
    ):
        return PromoteAction(
            action="activate",
            plugin_id=entry.plugin_id,
            name=entry.name,
            product_family=entry.product_family,
            target_version=entry.a_version,
            current_version=entry.b_version,
        )
    if (
        entry.status == "version_mismatch"
        and entry.a_version is not None
        and entry.b_version is not None
        and _is_newer(entry.a_version, entry.b_version)
    ):
        return PromoteAction(
            action="upgrade",
            plugin_id=entry.plugin_id,
            name=entry.name,
            product_family=entry.product_family,
            target_version=entry.a_version,
            current_version=entry.b_version,
        )
    return None


def _is_newer(candidate: str, baseline: str) -> bool:
    """True when ``candidate`` is strictly newer than ``baseline``.

    Returns ``False`` when either string fails to parse as a version --
    skipping unparseable strings is safer than guessing.
    """
    try:
        return parse_version(candidate) > parse_version(baseline)
    except InvalidVersion:
        return False
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_plugins_diff.py -v --no-cov`
Expected: 20 PASS (12 model tests + 6 compute_diff + 8 project tests = 26 total... actually 12 + 6 + 8 = 26).

Wait, recount: Task 1 had 12 model tests. Task 2 added 6 compute_diff tests. Task 3 adds 8 project tests. Total: 26. Confirm `pytest tests/test_plugins_diff.py -v --no-cov` reports 26 passed.

- [ ] **Step 5: Run linters**

```
ruff check src/nexus/plugins/diff.py tests/test_plugins_diff.py
pyright src/nexus/plugins/diff.py tests/test_plugins_diff.py
mypy src/nexus/plugins/diff.py tests/test_plugins_diff.py
```
Expected: all clean.

- [ ] **Step 6: Commit**

```bash
git add src/nexus/plugins/diff.py tests/test_plugins_diff.py
git commit -m "feat(plugins): add project_to_promote_plan with version-aware upgrade"
```

---

## Task 4: Public re-exports

**Files:**
- Modify: `src/nexus/plugins/__init__.py`

- [ ] **Step 1: Add the new names to the public API**

Read the current `src/nexus/plugins/__init__.py`, then update it to include the diff/promote names. The file becomes:

```python
# src/nexus/plugins/__init__.py
# Public re-exports for the plugins layer.
# Author: Pierre Grothe
# Date: 2026-05-11
"""nexus.plugins: read-only plugin inventory layer.

Exports the data models, scanner, error type, product-family lookup,
and the cross-instance diff/promote helpers.
"""

from nexus.plugins.diff import (
    PluginDiff,
    PluginDiffEntry,
    PromoteAction,
    PromotionPlan,
    compute_diff,
    project_to_promote_plan,
)
from nexus.plugins.errors import PluginScanError
from nexus.plugins.models import PluginInfo, PluginInventory, ProductFamily
from nexus.plugins.product_families import product_family_for
from nexus.plugins.scanner import PluginScanner

__all__ = [
    "PluginDiff",
    "PluginDiffEntry",
    "PluginInfo",
    "PluginInventory",
    "PluginScanError",
    "PluginScanner",
    "ProductFamily",
    "PromoteAction",
    "PromotionPlan",
    "compute_diff",
    "product_family_for",
    "project_to_promote_plan",
]
```

- [ ] **Step 2: Verify import surface**

Run: `python -c "from nexus.plugins import compute_diff, project_to_promote_plan, PluginDiff, PluginDiffEntry, PromoteAction, PromotionPlan; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Run linters**

```
ruff check src/nexus/plugins/__init__.py
pyright src/nexus/plugins/__init__.py
mypy src/nexus/plugins/__init__.py
```
Expected: all clean.

- [ ] **Step 4: Commit**

```bash
git add src/nexus/plugins/__init__.py
git commit -m "feat(plugins): expose diff and promote helpers"
```

---

## Task 5: nexus plugins diff command

**Files:**
- Modify: `src/nexus/cli.py`
- Create: `tests/test_cli_plugins_diff.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cli_plugins_diff.py
# Tests for nexus plugins diff and nexus plugins promote.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for the cross-instance plugin commands."""

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


def _seed(
    tmp_path: Path,
    profile: str,
    plugins: tuple[PluginInfo, ...] | None,
) -> None:
    profile_dir = tmp_path / "instances" / profile
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "meta.json").write_text(
        _meta(profile).model_dump_json(indent=2), encoding="utf-8"
    )
    if plugins is not None:
        inv = PluginInventory(
            captured_at=datetime.now(UTC),
            sn_version="Xanadu",
            plugins=plugins,
        )
        (profile_dir / "plugins.json").write_text(
            inv.model_dump_json(indent=2), encoding="utf-8"
        )


@pytest.fixture
def runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    monkeypatch.setenv("NEXUS_CONFIG_PATH", str(tmp_path / "config.yaml"))
    clear_cache(NexusPaths.from_env)
    return CliRunner()


def test_plugins_diff_renders_datatable_with_all_status_categories(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "prod",
        (
            _info("com.snc.problem"),
            _info("com.snc.incident", version="2.0.0"),
            _info("com.snc.discovery", state="active"),
        ),
    )
    _seed(
        tmp_path,
        "dev",
        (
            _info("com.snc.incident", version="1.0.0"),
            _info("com.snc.discovery", state="inactive"),
            _info("com.snc.legacy"),
        ),
    )
    result = runner.invoke(app, ["plugins", "diff", "prod", "dev"])
    assert result.exit_code == 0
    out = result.output
    assert "com.snc.problem" in out
    assert "com.snc.incident" in out
    assert "com.snc.discovery" in out
    assert "com.snc.legacy" in out


def test_plugins_diff_filters_by_status_flag(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(tmp_path, "prod", (_info("com.snc.problem"), _info("com.snc.incident")))
    _seed(tmp_path, "dev", (_info("com.snc.incident"),))
    result = runner.invoke(
        app, ["plugins", "diff", "prod", "dev", "--status", "only_in_a"]
    )
    assert result.exit_code == 0
    assert "com.snc.problem" in result.output
    assert "com.snc.incident" not in result.output


def test_plugins_diff_warns_when_either_inventory_missing(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(tmp_path, "prod", (_info("com.snc.incident"),))
    _seed(tmp_path, "dev", None)  # meta only, no plugins.json
    result = runner.invoke(app, ["plugins", "diff", "prod", "dev"])
    assert result.exit_code != 0
    assert "nexus instance refresh" in result.output


def test_plugins_diff_errors_when_profile_unknown(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(tmp_path, "prod", (_info("com.snc.incident"),))
    result = runner.invoke(app, ["plugins", "diff", "prod", "nonexistent"])
    assert result.exit_code != 0


def test_plugins_diff_with_identical_inventories_prints_no_differences(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(tmp_path, "prod", (_info("com.snc.incident"),))
    _seed(tmp_path, "dev", (_info("com.snc.incident"),))
    result = runner.invoke(app, ["plugins", "diff", "prod", "dev"])
    assert result.exit_code == 0
    assert "No differences" in result.output
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_cli_plugins_diff.py -v --no-cov`
Expected: FAIL on missing `diff` subcommand.

- [ ] **Step 3: Add the diff subcommand**

In `src/nexus/cli.py`, locate the existing `_PLUGINS_HELP` list and extend it. Find:

```python
_PLUGINS_HELP = [
    ("list", "Show all plugins with optional --product / --source / --state filters"),
    ("info <plugin_id>", "Show full details and dependencies for one plugin"),
    ("export", "Write the inventory to YAML or CSV"),
]
```

Replace with:

```python
_PLUGINS_HELP = [
    ("list", "Show all plugins with optional --product / --source / --state filters"),
    ("info <plugin_id>", "Show full details and dependencies for one plugin"),
    ("export", "Write the inventory to YAML or CSV"),
    ("diff <a> <b>", "Show cross-instance plugin differences"),
    ("promote <src> --to <dst>", "Write an action plan to make <dst> match <src>"),
]
```

Add to the imports near the existing nexus.plugins imports:

```python
from nexus.plugins.diff import (
    PluginDiff,
    PluginDiffEntry,
    PromotionPlan,
    compute_diff,
    project_to_promote_plan,
)
```

After `plugins_export` and before `plugins_callback` (or anywhere in `plugins_app` command order; placement only affects help-listing order), add:

```python
def _diff_status_badge(status: str) -> StatusBadge:
    """Return a StatusBadge for a PluginDiffEntry.status value."""
    if status == "version_mismatch":
        return StatusBadge.error(status)
    if status == "state_mismatch":
        return StatusBadge.ok(status)
    return StatusBadge.warn(status)


def _load_inventory_or_exit(profile: str) -> tuple[InstanceMeta, PluginInventory]:
    """Resolve a profile and load its plugin inventory, exiting with a Hint when empty."""
    registry, meta = _resolve_profile(profile)
    inv = registry.load_plugin_inventory(meta.profile)
    if inv is None:
        console.print(Notice.warn(f"Plugin inventory empty for {meta.profile!r}."))
        console.print(
            Hint(label="Refresh", command=f"nexus instance refresh {meta.profile}")
        )
        raise typer.Exit(1)
    return meta, inv


@plugins_app.command("diff")
def plugins_diff(
    profile_a: str,
    profile_b: str,
    status: Annotated[
        str,
        typer.Option(
            "--status",
            help="Filter by status (only_in_a|only_in_b|version_mismatch|state_mismatch)",
        ),
    ] = "",
) -> None:
    """Show cross-instance plugin differences."""
    meta_a, inv_a = _load_inventory_or_exit(profile_a)
    meta_b, inv_b = _load_inventory_or_exit(profile_b)
    diff = compute_diff(inv_a, inv_b, meta_a.profile, meta_b.profile)
    entries = diff.entries
    if status:
        entries = tuple(e for e in entries if e.status == status)
    if not entries:
        console.print(Notice.info("No differences found."))
        return
    rows: list[list[RenderableType]] = [
        [
            e.plugin_id,
            e.name,
            e.product_family,
            _diff_status_badge(e.status),
            e.a_version or "-",
            e.b_version or "-",
            e.a_state or "-",
            e.b_state or "-",
        ]
        for e in entries
    ]
    console.print(
        DataTable(
            title=f"Plugins: {meta_a.profile} vs {meta_b.profile}",
            columns=[
                DataColumn(header="Plugin ID", width=32),
                DataColumn(header="Name", width=20),
                DataColumn(header="Product", width=14),
                DataColumn(header="Status", width=18),
                DataColumn(header="A version", width=10),
                DataColumn(header="B version", width=10),
                DataColumn(header="A state", width=9),
                DataColumn(header="B state", width=9),
            ],
            rows=rows,
        )
    )
    console.print(Notice.info(f"{len(entries)} difference(s)."))
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_cli_plugins_diff.py -v --no-cov -k diff`
Expected: 5 PASS.

- [ ] **Step 5: Run linters**

```
ruff check src/nexus/cli.py tests/test_cli_plugins_diff.py
pyright src/nexus/cli.py tests/test_cli_plugins_diff.py
mypy src/nexus/cli.py tests/test_cli_plugins_diff.py
```
Expected: all clean.

- [ ] **Step 6: Commit**

```bash
git add src/nexus/cli.py tests/test_cli_plugins_diff.py
git commit -m "feat(cli): add nexus plugins diff for cross-instance comparison"
```

---

## Task 6: nexus plugins promote command

**Files:**
- Modify: `src/nexus/cli.py`
- Modify: `tests/test_cli_plugins_diff.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_cli_plugins_diff.py`:

```python
import yaml as _yaml


def test_plugins_promote_writes_yaml_with_install_activate_upgrade_sections(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "prod",
        (
            _info("com.snc.aaa"),  # install
            _info("com.snc.bbb", version="2.0.0"),  # upgrade
            _info("com.snc.ccc", state="active"),  # activate
        ),
    )
    _seed(
        tmp_path,
        "dev",
        (
            _info("com.snc.bbb", version="1.0.0"),
            _info("com.snc.ccc", state="inactive"),
        ),
    )
    out_file = tmp_path / "plan.yaml"
    result = runner.invoke(
        app,
        ["plugins", "promote", "prod", "--to", "dev", "--out", str(out_file)],
    )
    assert result.exit_code == 0
    payload = _yaml.safe_load(out_file.read_text(encoding="utf-8"))
    assert payload["source_profile"] == "prod"
    assert payload["target_profile"] == "dev"
    assert {a["plugin_id"] for a in payload["actions"]["install"]} == {"com.snc.aaa"}
    assert {a["plugin_id"] for a in payload["actions"]["activate"]} == {"com.snc.ccc"}
    assert {a["plugin_id"] for a in payload["actions"]["upgrade"]} == {"com.snc.bbb"}


def test_plugins_promote_default_out_path_is_promote_src_to_dst_yaml(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path, "prod", (_info("com.snc.aaa"),))
    _seed(tmp_path, "dev", ())
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["plugins", "promote", "prod", "--to", "dev"])
    assert result.exit_code == 0
    expected = tmp_path / "promote-prod-to-dev.yaml"
    assert expected.exists()


def test_plugins_promote_with_zero_actions_prints_already_matches_notice(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(tmp_path, "prod", (_info("com.snc.incident"),))
    _seed(tmp_path, "dev", (_info("com.snc.incident"),))
    out_file = tmp_path / "plan.yaml"
    result = runner.invoke(
        app,
        ["plugins", "promote", "prod", "--to", "dev", "--out", str(out_file)],
    )
    assert result.exit_code == 0
    assert "already matches" in result.output
    assert not out_file.exists()


def test_plugins_promote_rejects_same_source_and_target(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(tmp_path, "prod", (_info("com.snc.incident"),))
    result = runner.invoke(app, ["plugins", "promote", "prod", "--to", "prod"])
    assert result.exit_code != 0
    assert "same profile" in result.output.lower()


def test_plugins_promote_errors_when_either_inventory_missing(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(tmp_path, "prod", (_info("com.snc.incident"),))
    _seed(tmp_path, "dev", None)
    result = runner.invoke(app, ["plugins", "promote", "prod", "--to", "dev"])
    assert result.exit_code != 0
    assert "nexus instance refresh" in result.output
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_cli_plugins_diff.py -v --no-cov -k promote`
Expected: FAIL on missing `promote` subcommand.

- [ ] **Step 3: Add the promote subcommand**

In `src/nexus/cli.py`, after `plugins_diff`, add:

```python
def _promote_payload(plan: PromotionPlan) -> dict[str, object]:
    """Serialise a PromotionPlan into the YAML payload shape."""
    bucket: dict[str, list[dict[str, object]]] = {
        "install": [],
        "activate": [],
        "upgrade": [],
    }
    for action in plan.actions:
        row: dict[str, object] = {
            "plugin_id": action.plugin_id,
            "name": action.name,
            "product_family": action.product_family,
            "target_version": action.target_version,
        }
        if action.current_version is not None:
            row["current_version"] = action.current_version
        bucket[action.action].append(row)
    return {
        "source_profile": plan.source_profile,
        "target_profile": plan.target_profile,
        "actions": bucket,
    }


@plugins_app.command("promote")
def plugins_promote(
    source: str,
    target: Annotated[
        str, typer.Option("--to", help="Target profile to bring up to match source.")
    ],
    out: Annotated[
        str,
        typer.Option(
            "--out",
            help="Output YAML file (default: promote-<src>-to-<dst>.yaml)",
        ),
    ] = "",
) -> None:
    """Write an additive action plan to make <target> match <source>."""
    if source == target:
        err_console.print(
            Notice.error("Source and target are the same profile; nothing to promote.")
        )
        raise typer.Exit(1)
    meta_src, inv_src = _load_inventory_or_exit(source)
    meta_dst, inv_dst = _load_inventory_or_exit(target)
    diff = compute_diff(inv_src, inv_dst, meta_src.profile, meta_dst.profile)
    plan = project_to_promote_plan(diff)
    if not plan.actions:
        console.print(
            Notice.info(
                f"Target {meta_dst.profile!r} already matches "
                f"{meta_src.profile!r}. No actions written."
            )
        )
        return
    path = Path(out) if out else Path(f"promote-{meta_src.profile}-to-{meta_dst.profile}.yaml")
    payload = _promote_payload(plan)
    path.write_text(_yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    counts: dict[str, int] = {"install": 0, "activate": 0, "upgrade": 0}
    for action in plan.actions:
        counts[action.action] += 1
    console.print(
        KeyValuePanel(
            title="Promotion plan",
            rows=[
                KvRow(
                    label="Source",
                    value=f"{meta_src.profile} (captured {inv_src.captured_at.strftime('%Y-%m-%d %H:%M UTC')})",
                ),
                KvRow(
                    label="Target",
                    value=f"{meta_dst.profile} (captured {inv_dst.captured_at.strftime('%Y-%m-%d %H:%M UTC')})",
                ),
                KvRow(label="Install", value=str(counts["install"])),
                KvRow(label="Activate", value=str(counts["activate"])),
                KvRow(label="Upgrade", value=str(counts["upgrade"])),
                KvRow(label="Output", value=str(path)),
            ],
        )
    )
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_cli_plugins_diff.py -v --no-cov`
Expected: 10 PASS (5 diff + 5 promote).

- [ ] **Step 5: Run linters**

```
ruff check src/nexus/cli.py tests/test_cli_plugins_diff.py
pyright src/nexus/cli.py tests/test_cli_plugins_diff.py
mypy src/nexus/cli.py tests/test_cli_plugins_diff.py
```
Expected: all clean.

- [ ] **Step 6: Commit**

```bash
git add src/nexus/cli.py tests/test_cli_plugins_diff.py
git commit -m "feat(cli): add nexus plugins promote with YAML action plan"
```

---

## Task 7: Final verification + ratchet refresh

**Files:**
- Modify: `.ratchet.json`

- [ ] **Step 1: Run full quality suite**

```
ruff check src/nexus tests
black --check src/nexus tests
pyright src/nexus
mypy src/nexus
pytest tests/ --ignore=tests/test_updater_runner.py --no-cov -q
```
Expected: all clean except the 4 known pre-existing failures.

If black flags any files, run `black src/nexus tests` and commit the formatting separately.

- [ ] **Step 2: Smoke-render the new commands**

```
PYTHONIOENCODING=utf-8 .venv/Scripts/nexus plugins diff --help
PYTHONIOENCODING=utf-8 .venv/Scripts/nexus plugins promote --help
```
Expected: each prints help text without traceback.

- [ ] **Step 3: Generate coverage data**

```
pytest tests/ --ignore=tests/test_updater_runner.py --cov=nexus --cov-report=json --cov-fail-under=0 -q --no-header --tb=no
```

- [ ] **Step 4: Inspect new module coverage**

```
python -c "
import json
data = json.loads(open('coverage.json').read())
for k, v in sorted(data['files'].items()):
    nk = k.replace('\\\\', '/')
    if '/plugins/diff.py' in nk or '/nexus/cli.py' in nk or '/plugins/__init__.py' in nk:
        s = v['summary']
        rel = nk[nk.index('nexus/'):]
        mod = rel.replace('/', '.').removesuffix('.py')
        print(f'{mod}: covered={s[\"covered_lines\"]} total={s[\"num_statements\"]}')
"
```

- [ ] **Step 5: Update .ratchet.json**

Edit `.ratchet.json`:
- Bump `nexus.cli` to the new covered_lines / total_lines numbers from Step 4 (cli.py grew by ~80 lines for the two new commands).
- Update `nexus.plugins.__init__` to the new covered_lines (it gained the diff imports).
- Add a new entry for `nexus.plugins.diff` with the covered_lines / total_lines from Step 4.

The ratchet invariant is that ``covered_lines`` may only stay the same or grow per module. Verify the new numbers are equal or higher than the existing baseline for every line being changed.

- [ ] **Step 6: Verify ratchet still passes**

Run: `pytest tests/ --ignore=tests/test_updater_runner.py --no-cov -q`
Expected: same 4 pre-existing failures, all new tests pass.

- [ ] **Step 7: Commit**

```bash
git add .ratchet.json
git commit -m "chore(plugins): refresh ratchet baselines for the diff layer"
```

- [ ] **Step 8: Verify branch state**

Run: `git log --oneline 9ac0221..HEAD`
Expected: 7 commits (one per task) on top of the spec commit on this branch.

---

## Self-review against spec

Coverage check (each spec section must be implemented):

- Goal -- Tasks 1-7 collectively ship `nexus plugins diff` and `nexus plugins promote`.
- Layer placement (new `diff.py`, no upward imports) -- Task 1.
- Pydantic models (`PluginDiffEntry`, `PluginDiff`, `PromoteAction`, `PromotionPlan`) -- Task 1.
- Pure functions (`compute_diff`, `project_to_promote_plan`) -- Tasks 2 + 3.
- CLI surface (diff + promote with --status / --out / --to) -- Tasks 5 + 6.
- Promote YAML shape -- Task 6 (`_promote_payload`).
- Diff rendering (DataTable with StatusBadge, summary Notice, "No differences" when empty) -- Task 5.
- Promote rendering (KeyValuePanel with counts + already-matches Notice for zero actions) -- Task 6.
- Layer reuse (`InstanceRegistry.load_plugin_inventory`, `_resolve_profile`, `packaging.version.parse`, `_yaml.safe_dump`, UI components) -- Tasks 5 + 6.
- Error paths (unknown profile, missing inventory, same profile) -- Tasks 5 + 6.
- Out-of-scope (B3 deactivation impact, deactivate/downgrade actions in promote) -- not introduced; deliberately excluded.

Type-consistency check:

- `PluginDiffEntry.status` is `Literal["only_in_a", "only_in_b", "version_mismatch", "state_mismatch"]` in Task 1 and Task 2 uses the same literal in `_diff_entry`.
- `PromoteAction.action` is `Literal["install", "activate", "upgrade"]` in Task 1 and Task 3 emits exactly those three strings in `_project_entry`.
- `compute_diff(a, b, profile_a, profile_b)` keyword signature matches between Task 2 (definition) and Task 5 (call from `plugins_diff`).
- `project_to_promote_plan(diff)` signature matches between Task 3 (definition) and Task 6 (call from `plugins_promote`).
- `_load_inventory_or_exit(profile)` returns `tuple[InstanceMeta, PluginInventory]`; both Tasks 5 and 6 destructure exactly that shape.
- YAML payload shape (`source_profile`, `target_profile`, `actions: {install, activate, upgrade}`) is identical between Task 6 (`_promote_payload`) and the spec's promote YAML example.

Placeholder scan: none. Every step has either complete code or an exact command. No "TBD", no "similar to Task N", no "add validation".

Plan ready for execution.
