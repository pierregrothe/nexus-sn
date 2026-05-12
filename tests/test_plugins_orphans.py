# tests/test_plugins_orphans.py
# Tests for the plugin orphan detection layer.
# Author: Pierre Grothe
# Date: 2026-05-12
"""Tests for nexus.plugins.orphans.orphan_candidates."""

from datetime import UTC, datetime

import nexus.plugins as plugins_pkg
from nexus.plugins.models import PluginInfo, PluginInventory, ScopeRecordCount
from nexus.plugins.orphans import orphan_candidates

__all__: list[str] = []


def _plugin(
    plugin_id: str,
    *,
    depends_on: tuple[str, ...] = (),
    state: str = "active",
    record_count: int | None = None,
) -> PluginInfo:
    """Build a PluginInfo translating legacy record_count to record_counts.

    ``record_count=0`` -> ``record_counts=()`` (empty -> sum 0).
    ``record_count=N>0`` -> single-bucket tuple summing to N.
    ``record_count=None`` -> ``record_counts=None`` (uncaptured).
    """
    if record_count is None:
        counts: tuple[ScopeRecordCount, ...] | None = None
    elif record_count == 0:
        counts = ()
    else:
        counts = (ScopeRecordCount(table="sys_script", count=record_count),)
    return PluginInfo.model_validate(
        {
            "plugin_id": plugin_id,
            "name": plugin_id,
            "version": "1.0",
            "state": state,
            "source": "store",
            "product_family": "Uncategorized",
            "depends_on": depends_on,
            "sys_id": f"sys-{plugin_id}",
            "installed_at": None,
            "record_counts": counts,
        }
    )


def _inventory(*plugins: PluginInfo) -> PluginInventory:
    return PluginInventory(
        captured_at=datetime(2026, 5, 12, tzinfo=UTC),
        sn_version="Washington",
        plugins=plugins,
    )


def test_orphan_candidates_returns_plugin_with_zero_deps_and_zero_records() -> None:
    inv = _inventory(_plugin("com.lonely", record_count=0))
    result = orphan_candidates(inv)
    assert len(result) == 1
    assert result[0].plugin_id == "com.lonely"


def test_orphan_candidates_excludes_plugin_with_dependents() -> None:
    inv = _inventory(
        _plugin("com.target", record_count=0),
        _plugin("com.consumer", depends_on=("com.target",), record_count=0),
    )
    result = orphan_candidates(inv)
    # com.target has a dependent so it's excluded;
    # com.consumer has 0 deps + 0 records so IT is an orphan.
    assert [p.plugin_id for p in result] == ["com.consumer"]


def test_orphan_candidates_excludes_plugin_with_records() -> None:
    inv = _inventory(_plugin("com.busy", record_count=42))
    assert orphan_candidates(inv) == ()


def test_orphan_candidates_excludes_plugin_with_record_count_none() -> None:
    inv = _inventory(_plugin("com.unknown", record_count=None))
    assert orphan_candidates(inv) == ()


def test_orphan_candidates_includes_inactive_plugins() -> None:
    inv = _inventory(
        _plugin("com.dead", state="inactive", record_count=0),
    )
    assert orphan_candidates(inv)[0].state == "inactive"


def test_orphan_candidates_excludes_plugin_in_its_own_depends_on() -> None:
    inv = _inventory(
        _plugin("com.loop", depends_on=("com.loop",), record_count=0),
    )
    assert orphan_candidates(inv) == ()


def test_orphan_candidates_sorts_by_state_then_plugin_id() -> None:
    inv = _inventory(
        _plugin("com.b", state="inactive", record_count=0),
        _plugin("com.a", state="inactive", record_count=0),
        _plugin("com.z", state="active", record_count=0),
    )
    result = orphan_candidates(inv)
    assert [p.plugin_id for p in result] == ["com.z", "com.a", "com.b"]


def test_orphan_candidates_returns_empty_tuple_when_no_candidates() -> None:
    inv = _inventory(_plugin("com.busy", record_count=100))
    assert orphan_candidates(inv) == ()


def test_public_api_reexports_orphan_candidates() -> None:
    assert "orphan_candidates" in plugins_pkg.__all__
    assert hasattr(plugins_pkg, "orphan_candidates")
