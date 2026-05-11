# tests/test_plugins_models.py
# Tests for the plugins layer Pydantic models.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for PluginInfo, PluginInventory, and ProductFamily."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from nexus.plugins.models import PluginInfo, PluginInventory, ProductFamily

__all__: list[str] = []


def _info(**overrides: object) -> PluginInfo:
    defaults: dict[str, object] = {
        "plugin_id": "com.snc.incident",
        "name": "Incident Management",
        "version": "1.0.0",
        "state": "active",
        "source": "servicenow",
        "product_family": "ITSM",
        "depends_on": (),
        "sys_id": "abc123",
        "installed_at": None,
    }
    defaults.update(overrides)
    return PluginInfo.model_validate(defaults)


def test_product_family_includes_all_curated_families() -> None:
    for name in (
        "ITSM", "ITOM", "ITAM", "SPM", "CSM", "HRSD",
        "FSM", "GRC", "IRM", "SecOps", "Platform", "Uncategorized",
    ):
        assert any(f.value == name for f in ProductFamily)


def test_plugin_info_construction_with_required_fields() -> None:
    info = _info()
    assert info.plugin_id == "com.snc.incident"
    assert info.state == "active"


def test_plugin_info_is_frozen() -> None:
    info = _info()
    with pytest.raises(ValidationError):
        info.name = "renamed"


def test_plugin_info_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        PluginInfo.model_validate({**_info().model_dump(), "extra": "x"})


def test_plugin_info_rejects_unknown_state() -> None:
    with pytest.raises(ValidationError):
        _info(state="unknown")


def test_plugin_info_rejects_unknown_source() -> None:
    with pytest.raises(ValidationError):
        _info(source="vendor")


def test_plugin_inventory_holds_captured_at_and_plugins() -> None:
    now = datetime.now(UTC)
    inv = PluginInventory(
        captured_at=now, sn_version="Xanadu", plugins=(_info(),)
    )
    assert inv.captured_at == now
    assert inv.plugins[0].plugin_id == "com.snc.incident"


def test_plugin_inventory_is_frozen() -> None:
    inv = PluginInventory(
        captured_at=datetime.now(UTC), sn_version="Xanadu", plugins=()
    )
    with pytest.raises(ValidationError):
        inv.sn_version = "Yokohama"


def test_plugin_inventory_round_trips_through_json() -> None:
    inv = PluginInventory(
        captured_at=datetime.now(UTC), sn_version="Xanadu", plugins=(_info(),)
    )
    re = PluginInventory.model_validate_json(inv.model_dump_json())
    assert re == inv
