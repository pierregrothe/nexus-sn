# tests/test_plugins_product_families.py
# Tests for the product-family YAML loader.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for product_family_for() and load_product_families()."""

from datetime import UTC, datetime

from nexus.plugins.models import PluginInfo, PluginInventory, ProductFamily
from nexus.plugins.product_families import (
    load_product_families,
    product_family_for,
    refresh_product_families,
)


def _make_plugin(plugin_id: str, product_family: str) -> PluginInfo:
    """Build a minimal PluginInfo with the given plugin_id and stale family."""
    return PluginInfo(
        plugin_id=plugin_id,
        name=plugin_id,
        version="1.0.0",
        state="active",
        source="store",
        product_family=product_family,
        depends_on=(),
        sys_id="abc123",
        installed_at=None,
    )


def _make_inventory(*plugins: PluginInfo) -> PluginInventory:
    """Build a minimal PluginInventory containing the given plugins."""
    return PluginInventory(
        captured_at=datetime(2026, 5, 15, tzinfo=UTC),
        sn_version="Yokohama",
        plugins=plugins,
    )


__all__: list[str] = []


def test_load_product_families_returns_non_empty_mapping() -> None:
    mapping = load_product_families()
    assert len(mapping) >= 40


def test_load_product_families_values_are_valid_product_family_members() -> None:
    mapping = load_product_families()
    valid = {f.value for f in ProductFamily}
    for plugin_id, family in mapping.items():
        assert family in valid, f"{plugin_id!r} maps to invalid family {family!r}"


def test_load_product_families_has_no_duplicate_keys() -> None:
    """YAML load already deduplicates, but assert no keys collide post-load."""
    mapping = load_product_families()
    assert len(mapping) == len({k.lower() for k in mapping})


def test_product_family_for_known_id_returns_curated_family() -> None:
    assert product_family_for("com.snc.incident") == ProductFamily.ITSM
    assert product_family_for("sn_hr_core") == ProductFamily.HRSD


def test_product_family_for_unknown_id_returns_uncategorized() -> None:
    assert product_family_for("x_company_app") == ProductFamily.UNCATEGORIZED


def test_product_family_for_empty_string_returns_uncategorized() -> None:
    assert product_family_for("") == ProductFamily.UNCATEGORIZED


def test_product_family_for_unknown_glide_id_defaults_to_platform() -> None:
    """com.glide.* plugins fall through keyword rules to PLATFORM."""
    assert product_family_for("com.glide.something_unknown") == ProductFamily.PLATFORM


def test_product_family_for_unknown_id_with_itsm_keyword_returns_itsm() -> None:
    """Keyword rules bucket 'incident' substring as ITSM even without YAML entry."""
    assert product_family_for("com.acme.major_incident_handler") == ProductFamily.ITSM


def test_product_family_for_unknown_id_with_cmdb_keyword_returns_itom() -> None:
    assert product_family_for("com.acme.cmdb_helper") == ProductFamily.ITOM


def test_product_family_for_unknown_id_with_asset_keyword_returns_itam() -> None:
    assert product_family_for("com.acme.asset_management_addon") == ProductFamily.ITAM


def test_product_family_for_unknown_id_with_secops_keyword_returns_secops() -> None:
    assert product_family_for("com.acme.vulnerability_scanner") == ProductFamily.SEC_OPS


def test_product_family_for_unknown_id_with_workflow_keyword_returns_platform() -> None:
    assert product_family_for("com.acme.workflow_helper") == ProductFamily.PLATFORM


def test_product_family_for_sn_bcm_returns_grc() -> None:
    """sn_bcm (Business Continuity Management) is curated GRC."""
    assert product_family_for("sn_bcm") == ProductFamily.GRC


def test_product_family_for_sn_bcm_subscope_via_keyword_returns_grc() -> None:
    """Unknown sn_bcm_* sub-scopes resolve via the ``_bcm`` keyword."""
    assert product_family_for("sn_bcm_recovery_workspace") == ProductFamily.GRC


def test_product_family_for_business_continuity_keyword_returns_grc() -> None:
    assert product_family_for("x_acme_business_continuity_plan") == ProductFamily.GRC


def test_product_family_for_vendor_risk_keyword_returns_grc() -> None:
    assert product_family_for("x_acme_vendor_risk_dashboard") == ProductFamily.GRC


def test_product_family_for_unknown_com_snc_id_defaults_to_platform() -> None:
    """SN-shipped com.snc.* plugins without keyword match default to Platform."""
    assert product_family_for("com.snc.some_unknown_feature") == ProductFamily.PLATFORM


def test_product_family_for_unknown_com_servicenow_id_defaults_to_platform() -> None:
    assert product_family_for("com.servicenow.experimental") == ProductFamily.PLATFORM


def test_product_family_for_unknown_thirdparty_app_stays_uncategorized() -> None:
    """Third-party / OEM apps (no SN-shipped prefix, no keyword) stay uncategorized."""
    assert product_family_for("x_acme_widget") == ProductFamily.UNCATEGORIZED


def test_product_family_for_now_mobile_returns_platform() -> None:
    """sn_now_mobile is curated Platform."""
    assert product_family_for("sn_now_mobile") == ProductFamily.PLATFORM


def test_product_family_for_predictive_intelligence_keyword_returns_platform() -> None:
    assert product_family_for("x_acme_predictive_intelligence") == ProductFamily.PLATFORM


def test_product_family_for_compliance_keyword_returns_grc() -> None:
    assert product_family_for("x_acme_compliance_dashboard") == ProductFamily.GRC


def test_product_family_for_secops_si_prefix_returns_secops() -> None:
    """sn_si_ prefix resolves to SecOps via keyword rule."""
    assert product_family_for("sn_si_incident_response_workflow") == ProductFamily.SEC_OPS


def test_product_family_for_app_engine_keyword_returns_platform() -> None:
    assert product_family_for("x_acme_app_engine_helper") == ProductFamily.PLATFORM


def test_product_family_for_employee_center_keyword_returns_hrsd() -> None:
    assert product_family_for("x_acme_employee_center_widget") == ProductFamily.HRSD


def test_product_family_for_continual_improvement_returns_grc() -> None:
    """sn_continual_improvement is curated as GRC."""
    assert product_family_for("sn_continual_improvement") == ProductFamily.GRC


def test_product_family_for_glide_prefix_still_defaults_to_platform() -> None:
    """Regression: com.glide.* fallback continues to work after refactor."""
    assert product_family_for("com.glide.experimental") == ProductFamily.PLATFORM


def test_refresh_product_families_rewrites_stale_uncategorized_to_grc() -> None:
    """A persisted inventory tagged Uncategorized for sn_bcm is corrected on load."""
    inv = _make_inventory(_make_plugin("sn_bcm", "Uncategorized"))
    refreshed = refresh_product_families(inv)
    assert refreshed.plugins[0].product_family == ProductFamily.GRC.value


def test_refresh_product_families_returns_same_instance_when_no_change() -> None:
    """Identity-preserving fast path: when every family already matches, no copy."""
    inv = _make_inventory(_make_plugin("com.snc.incident", ProductFamily.ITSM.value))
    refreshed = refresh_product_families(inv)
    assert refreshed is inv


def test_refresh_product_families_preserves_other_fields() -> None:
    """Only product_family changes; other plugin attributes are untouched."""
    original = _make_plugin("sn_bcm", "Uncategorized")
    inv = _make_inventory(original)
    refreshed = refresh_product_families(inv)
    new_plugin = refreshed.plugins[0]
    assert new_plugin.plugin_id == original.plugin_id
    assert new_plugin.name == original.name
    assert new_plugin.version == original.version
    assert new_plugin.sys_id == original.sys_id
    assert new_plugin.product_family == ProductFamily.GRC.value


def test_refresh_product_families_handles_mixed_inventory() -> None:
    """Mix of correctly tagged and stale plugins: only the stale ones change."""
    fresh = _make_plugin("com.snc.incident", ProductFamily.ITSM.value)
    stale = _make_plugin("sn_bcm", "Uncategorized")
    inv = _make_inventory(fresh, stale)
    refreshed = refresh_product_families(inv)
    assert refreshed.plugins[0].product_family == ProductFamily.ITSM.value
    assert refreshed.plugins[1].product_family == ProductFamily.GRC.value


def test_refresh_product_families_preserves_inventory_metadata() -> None:
    """captured_at and sn_version survive the refresh."""
    inv = _make_inventory(_make_plugin("sn_bcm", "Uncategorized"))
    refreshed = refresh_product_families(inv)
    assert refreshed.captured_at == inv.captured_at
    assert refreshed.sn_version == inv.sn_version
