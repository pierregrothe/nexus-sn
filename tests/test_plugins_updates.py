# tests/test_plugins_updates.py
# Tests for the plugins_with_updates filter.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for plugins_with_updates."""

from datetime import UTC, datetime

from nexus.plugins.models import PluginInfo, PluginInventory
from nexus.plugins.updates import plugins_with_updates

__all__: list[str] = []


def _info(
    plugin_id: str,
    *,
    version: str = "1.0.0",
    latest_version: str | None = None,
    product_family: str = "ITSM",
) -> PluginInfo:
    return PluginInfo.model_validate(
        {
            "plugin_id": plugin_id,
            "name": plugin_id,
            "version": version,
            "state": "active",
            "source": "store",
            "product_family": product_family,
            "depends_on": (),
            "sys_id": f"sys-{plugin_id}",
            "installed_at": None,
            "latest_version": latest_version,
        }
    )


def _inventory(*plugins: PluginInfo) -> PluginInventory:
    return PluginInventory(
        captured_at=datetime.now(UTC),
        sn_version="Xanadu",
        plugins=plugins,
    )


def test_plugins_with_updates_filters_to_only_those_with_newer_latest() -> None:
    inv = _inventory(
        _info("com.acme.helper", version="3.0.0", latest_version="3.1.0"),
        _info("com.acme.other", version="1.0.0", latest_version="1.0.0"),
        _info("com.snc.incident", version="1.0.0", latest_version=None),
    )
    result = plugins_with_updates(inv)
    assert len(result) == 1
    assert result[0].plugin_id == "com.acme.helper"


def test_plugins_with_updates_skips_plugins_without_latest_version() -> None:
    inv = _inventory(
        _info("com.snc.incident", version="1.0.0", latest_version=None),
    )
    assert plugins_with_updates(inv) == ()


def test_plugins_with_updates_skips_plugins_at_latest_version() -> None:
    inv = _inventory(
        _info("com.acme.helper", version="3.1.0", latest_version="3.1.0"),
    )
    assert plugins_with_updates(inv) == ()


def test_plugins_with_updates_sorts_by_product_then_plugin_id() -> None:
    inv = _inventory(
        _info(
            "com.acme.helper",
            version="1.0.0",
            latest_version="2.0.0",
            product_family="Uncategorized",
        ),
        _info(
            "com.snc.problem",
            version="1.0.0",
            latest_version="2.0.0",
            product_family="ITSM",
        ),
        _info(
            "com.snc.incident",
            version="1.0.0",
            latest_version="2.0.0",
            product_family="ITSM",
        ),
    )
    result = plugins_with_updates(inv)
    ids = [p.plugin_id for p in result]
    assert ids == ["com.snc.incident", "com.snc.problem", "com.acme.helper"]
