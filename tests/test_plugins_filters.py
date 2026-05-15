# tests/test_plugins_filters.py
# Tests for nexus.plugins.filters helpers.
# Author: Pierre Grothe
# Date: 2026-05-14

"""Tests for filter_by_family and available_families."""

from nexus.plugins.filters import available_families, filter_by_family, unknown_families
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
    assert result == plugins


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


def test_available_families_counts_sorted_alphabetically() -> None:
    plugins = (
        _info("com.acme.a", product_family="ITSM"),
        _info("com.acme.b", product_family="ITOM"),
        _info("com.acme.c", product_family="ITSM"),
        _info("com.acme.d", product_family="HRSD"),
    )
    result = available_families(plugins)
    assert result == (("HRSD", 1), ("ITOM", 1), ("ITSM", 2))


def test_unknown_families_returns_only_invalid_names() -> None:
    assert unknown_families(("ITSM", "BOGUS", "ITOM", "ALSO_BAD")) == ("BOGUS", "ALSO_BAD")


def test_unknown_families_is_case_insensitive() -> None:
    assert unknown_families(("itsm", "ITOM", "platform")) == ()


def test_unknown_families_empty_input_returns_empty() -> None:
    assert unknown_families(()) == ()
