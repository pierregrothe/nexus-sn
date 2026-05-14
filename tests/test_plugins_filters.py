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
