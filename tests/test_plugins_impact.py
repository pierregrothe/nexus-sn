# tests/test_plugins_impact.py
# Tests for the plugin impact analysis layer.
# Author: Pierre Grothe
# Date: 2026-05-12
"""Tests for src/nexus/plugins/impact.py and PluginImpactError."""

from datetime import UTC, datetime

import pytest

from nexus.plugins.errors import PluginImpactError
from nexus.plugins.impact import reverse_dependencies
from nexus.plugins.models import PluginInfo, PluginInventory

__all__: list[str] = []


def test_plugin_impact_error_carries_plugin_id() -> None:
    err = PluginImpactError("com.unknown")
    assert err.plugin_id == "com.unknown"
    assert "com.unknown" in str(err)


def test_plugin_impact_error_is_exception_subclass() -> None:
    assert issubclass(PluginImpactError, Exception)


def _plugin(
    plugin_id: str,
    *,
    depends_on: tuple[str, ...] = (),
    state: str = "active",
) -> PluginInfo:
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
        }
    )


def _inventory(*plugins: PluginInfo) -> PluginInventory:
    return PluginInventory(
        captured_at=datetime(2026, 5, 12, tzinfo=UTC),
        sn_version="Washington",
        plugins=plugins,
    )


def test_reverse_dependencies_returns_empty_when_no_dependents() -> None:
    inv = _inventory(
        _plugin("com.target"),
        _plugin("com.unrelated", depends_on=("com.other",)),
    )
    assert reverse_dependencies(inv, "com.target") == ()


def test_reverse_dependencies_finds_direct_dependents_at_depth_1() -> None:
    inv = _inventory(
        _plugin("com.target"),
        _plugin("com.dependent", depends_on=("com.target",)),
    )
    deps = reverse_dependencies(inv, "com.target")
    assert len(deps) == 1
    assert deps[0].plugin_id == "com.dependent"
    assert deps[0].depth == 1


def test_reverse_dependencies_traverses_transitively() -> None:
    inv = _inventory(
        _plugin("com.target"),
        _plugin("com.mid", depends_on=("com.target",)),
        _plugin("com.outer", depends_on=("com.mid",)),
    )
    deps = reverse_dependencies(inv, "com.target")
    ids_by_depth = {d.plugin_id: d.depth for d in deps}
    assert ids_by_depth == {"com.mid": 1, "com.outer": 2}


def test_reverse_dependencies_sets_via_chain_inclusive_of_endpoints() -> None:
    inv = _inventory(
        _plugin("com.target"),
        _plugin("com.mid", depends_on=("com.target",)),
        _plugin("com.outer", depends_on=("com.mid",)),
    )
    deps = reverse_dependencies(inv, "com.target")
    outer = next(d for d in deps if d.plugin_id == "com.outer")
    assert outer.via == ("com.outer", "com.mid", "com.target")


def test_reverse_dependencies_handles_cycles_without_infinite_loop() -> None:
    inv = _inventory(
        _plugin("com.target", depends_on=("com.cycle",)),
        _plugin("com.cycle", depends_on=("com.target",)),
    )
    deps = reverse_dependencies(inv, "com.target")
    assert len(deps) == 1
    assert deps[0].plugin_id == "com.cycle"


def test_reverse_dependencies_handles_self_dependency_without_loop() -> None:
    inv = _inventory(
        _plugin("com.target", depends_on=("com.target",)),
    )
    assert reverse_dependencies(inv, "com.target") == ()


def test_reverse_dependencies_sorts_by_depth_then_plugin_id() -> None:
    inv = _inventory(
        _plugin("com.target"),
        _plugin("com.b", depends_on=("com.target",)),
        _plugin("com.a", depends_on=("com.target",)),
        _plugin("com.deep", depends_on=("com.a",)),
    )
    deps = reverse_dependencies(inv, "com.target")
    order = [(d.depth, d.plugin_id) for d in deps]
    assert order == sorted(order)


def test_reverse_dependencies_raises_when_target_not_in_inventory() -> None:
    inv = _inventory(_plugin("com.other"))
    with pytest.raises(PluginImpactError):
        reverse_dependencies(inv, "com.target")
