# src/nexus/plugins/product_families.py
# Loader for the curated plugin_id -> ProductFamily mapping.
# Author: Pierre Grothe
# Date: 2026-05-11
"""product_family_for: O(1) lookup against product_families.yaml."""

from pathlib import Path

import yaml

from nexus.cache import cached
from nexus.plugins.models import ProductFamily

__all__ = ["load_product_families", "product_family_for"]

_YAML_PATH = Path(__file__).parent / "product_families.yaml"


@cached(ttl=None)
def load_product_families() -> dict[str, str]:
    """Read product_families.yaml once and cache the mapping.

    Returns:
        ``plugin_id -> ProductFamily.value`` mapping. Values are validated
        against the ``ProductFamily`` enum so a typo in the YAML fails at
        load time rather than silently mis-tagging plugins.

    Raises:
        ValueError: When a YAML value is not a valid ProductFamily name.
    """
    raw: dict[str, str] = yaml.safe_load(_YAML_PATH.read_text(encoding="utf-8")) or {}
    valid_values = {f.value for f in ProductFamily}
    for plugin_id, family in raw.items():
        if family not in valid_values:
            raise ValueError(
                f"Invalid product family {family!r} for {plugin_id!r} " f"in product_families.yaml"
            )
    return raw


_KEYWORD_RULES: tuple[tuple[ProductFamily, tuple[str, ...]], ...] = (
    (
        ProductFamily.ITSM,
        (
            "incident",
            "problem",
            "change_management",
            "change_request",
            "knowledge",
            "service_catalog",
            "catalog_builder",
            "itil",
            "major_incident",
            "walk_up",
            "sla",
            "request_management",
        ),
    ),
    (
        ProductFamily.ITOM,
        (
            "cmdb",
            "discovery",
            "event_management",
            "service_mapping",
            "cloud_management",
            "health_log_analytics",
            "operational_intelligence",
            "agent_client_collector",
        ),
    ),
    (
        ProductFamily.ITAM,
        (
            "asset_management",
            "contract_management",
            "software_asset",
            "hardware_asset",
            "consumable",
            "stockroom",
        ),
    ),
    (
        ProductFamily.CSM,
        (
            "customer_service",
            "csm_",
            "case_management",
        ),
    ),
    (
        ProductFamily.HRSD,
        (
            "hr_",
            "hrsd",
            "human_resources",
            "employee_service",
            "onboarding",
        ),
    ),
    (
        ProductFamily.FSM,
        (
            "fsm",
            "field_service",
            "dispatch",
            "work_order",
        ),
    ),
    (
        ProductFamily.GRC,
        (
            "grc",
            "policy_compliance",
            "audit",
            "risk_management",
            "regulatory",
        ),
    ),
    (
        ProductFamily.IRM,
        (
            "irm",
            "integrated_risk",
        ),
    ),
    (
        ProductFamily.SEC_OPS,
        (
            "vulnerability",
            "threat",
            "secops",
            "security_incident",
            "sir_",
            "security_operations",
        ),
    ),
    (
        ProductFamily.SPM,
        (
            "spm",
            "project_portfolio",
            "resource_management",
            "demand_management",
            "innovation_management",
            "test_management",
            "agile",
        ),
    ),
    (
        ProductFamily.PLATFORM,
        (
            "platform",
            "flow_designer",
            "integration_hub",
            "now_assist",
            "studio",
            "scripted_rest",
            "ui_builder",
            "automated_testing",
            "ats",
            "oauth",
            "authentication",
            "system_security",
            "encryption",
            "audit_log",
            "scheduled_jobs",
            "table_builder",
            "workflow",
        ),
    ),
)


def _classify_by_keyword(plugin_id: str) -> ProductFamily | None:
    """Bucket a plugin_id by substring against the keyword rules.

    Returns the first matching ProductFamily or ``None`` when no rule fires.
    """
    pid = plugin_id.lower()
    for family, keywords in _KEYWORD_RULES:
        if any(kw in pid for kw in keywords):
            return family
    return None


def product_family_for(plugin_id: str) -> ProductFamily:
    """Return the curated ProductFamily for a plugin, or a keyword-derived one.

    Resolution order:
        1. Exact match against ``product_families.yaml``.
        2. Substring match against ``_KEYWORD_RULES``.
        3. ``com.glide.*`` plugins default to ``PLATFORM``.
        4. Fallback: ``UNCATEGORIZED``.

    Args:
        plugin_id: SN plugin identifier (v_plugin.id or sys_store_app.scope).

    Returns:
        ProductFamily enum member.
    """
    family_value = load_product_families().get(plugin_id)
    if family_value is not None:
        return ProductFamily(family_value)
    keyword_match = _classify_by_keyword(plugin_id)
    if keyword_match is not None:
        return keyword_match
    if plugin_id.startswith("com.glide."):
        return ProductFamily.PLATFORM
    return ProductFamily.UNCATEGORIZED
