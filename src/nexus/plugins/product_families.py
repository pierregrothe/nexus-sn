# src/nexus/plugins/product_families.py
# Loader for the curated plugin_id -> ProductFamily mapping.
# Author: Pierre Grothe
# Date: 2026-05-11
"""product_family_for: O(1) lookup against product_families.yaml."""

from pathlib import Path

import yaml

from nexus.cache import cached
from nexus.plugins.models import PluginInfo, PluginInventory, ProductFamily

__all__ = [
    "load_product_families",
    "product_family_for",
    "refresh_product_families",
]

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
    # SEC_OPS is evaluated before ITSM so prefixes like ``sn_si_`` win over
    # the broader ``incident`` keyword for security-incident plugins.
    (
        ProductFamily.SEC_OPS,
        (
            "vulnerability",
            "threat",
            "secops",
            "security_incident",
            "sir_",
            "_sir",
            "security_operations",
            "phishing",
            "_siem",
            "siem_",
            "_soar",
            "soar_",
            "sn_si_",
            "sn_vul",
            "sn_ti_",
            "sn_sec_",
        ),
    ),
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
            "request_item",
            "_itsm",
            "service_desk",
            "ticketing",
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
            "service_graph",
            "metric_intelligence",
            "cloud_observability",
            "_itom",
            "monitor_",
            "site_reliability",
            "_acc_",
            "certificate_inventory",
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
            "_itam",
            "_sam_",
            "_ham_",
            "license_workbench",
        ),
    ),
    (
        ProductFamily.CSM,
        (
            "customer_service",
            "csm_",
            "_csm",
            "case_management",
            "_complaint",
            "contact_center",
            "partner_management",
            "industry_solution",
            "telecommunication",
            "_tsom",
            "tsom_",
        ),
    ),
    (
        ProductFamily.HRSD,
        (
            "hr_",
            "_hrsd",
            "hrsd",
            "human_resources",
            "employee_service",
            "employee_center",
            "employee_journey",
            "journey_designer",
            "onboarding",
            "talent_",
            "lifecycle_event",
        ),
    ),
    (
        ProductFamily.FSM,
        (
            "fsm",
            "field_service",
            "dispatch",
            "work_order",
            "route_optimiz",
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
            "_bcm",
            "bcm_",
            "business_continuity",
            "compliance_",
            "_compliance",
            "vendor_risk",
            "third_party_risk",
            "_tprm",
            "tprm_",
            "vrm_",
            "_vrm",
            "operational_resilience",
            "continual_improvement",
            "crisis_management",
            "privacy_management",
            "esg_",
            "_esg",
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
            "_sir",
            "security_operations",
            "phishing",
            "_siem",
            "siem_",
            "_soar",
            "soar_",
            "sn_si_",
            "sn_vul",
            "sn_ti_",
            "sn_sec_",
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
            "_apm_",
            "apm_",
            "_tpm_",
            "tpm_",
            "program_management",
            "business_planning",
            "strategic_portfolio",
        ),
    ),
    (
        ProductFamily.PLATFORM,
        (
            "platform",
            "flow_designer",
            "integration_hub",
            "now_assist",
            "now_mobile",
            "now_learning",
            "studio",
            "scripted_rest",
            "ui_builder",
            "ui_action",
            "automated_testing",
            "atf_",
            "_atf",
            "ats",
            "oauth",
            "authentication",
            "saml",
            "ldap",
            "system_security",
            "encryption",
            "audit_log",
            "scheduled_jobs",
            "table_builder",
            "workflow",
            "app_engine",
            "appcreator",
            "app_creator",
            "predictive_intelligence",
            "_ml_",
            "ml_models",
            "branding",
            "live_feed",
            "mobile_",
            "_mobile",
            "notify",
            "notification",
            "virtual_agent",
            "performance_analytics",
            "ai_search",
            "ai_agent",
            "decision_builder",
            "decision_table",
            "form_designer",
            "import_set",
            "import_export",
            "instance_security",
            "domain_separation",
            "delegated_dev",
            "password_reset",
            "process_automation",
            "translation",
            "subscription",
            "support_assistant",
            "service_portal",
            "pdi_",
            "_pdi",
            "app_store",
            "data_classification",
            "data_quality",
            "guided_setup",
            "dashboard",
            "report_designer",
            "schedule_publication",
            "managed_document",
            "team_development",
            "update_set",
            "source_control",
            "platform_analytics",
            "process_optimization",
            "process_mining",
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


_SN_SHIPPED_PREFIXES: tuple[str, ...] = (
    "com.",
    "sn_",
    "now_",
    "glide.",
    "sys.",
)
"""SN-shipped plugin id prefixes.

ServiceNow plugins always use one of these prefixes. Third-party
("scoped") apps shipped through the store by other vendors use the
``x_<vendor>_<app>`` convention and never start with ``com.`` or
``sn_``. So any plugin matching one of these prefixes that does NOT
match a domain keyword can safely default to ``PLATFORM`` rather than
``UNCATEGORIZED`` -- it is some kind of SN-shipped platform feature
or UI component (``com.devsnc_*``, ``com.servicenow_now_*``,
``com.glideapp.*``, ``sn_uib_*``, etc.).
"""


def refresh_product_families(inventory: PluginInventory) -> PluginInventory:
    """Return ``inventory`` with every plugin's ``product_family`` recomputed.

    ``product_family`` is a derived attribute -- a pure function of
    ``plugin_id`` via :func:`product_family_for`. Persisted inventories
    written by an older NEXUS version can carry stale family labels (e.g.,
    ``Uncategorized``) that the current ruleset would resolve. Calling this
    on every on-disk load means the user sees today's categorization
    without having to re-scan.

    Args:
        inventory: Inventory loaded from disk (or any inventory).

    Returns:
        A new :class:`PluginInventory` with each ``PluginInfo`` rebuilt via
        ``model_copy`` if its family changed; entries whose family already
        matches the current rules are reused unchanged.
    """
    refreshed: list[PluginInfo] = []
    changed = False
    for plugin in inventory.plugins:
        current = product_family_for(plugin.plugin_id).value
        if current == plugin.product_family:
            refreshed.append(plugin)
            continue
        refreshed.append(plugin.model_copy(update={"product_family": current}))
        changed = True
    if not changed:
        return inventory
    return inventory.model_copy(update={"plugins": tuple(refreshed)})


def product_family_for(plugin_id: str) -> ProductFamily:
    """Return the curated ProductFamily for a plugin, or a keyword-derived one.

    Resolution order:
        1. Exact match against ``product_families.yaml``.
        2. Substring match against ``_KEYWORD_RULES``.
        3. SN-shipped prefixes (``com.glide.``, ``com.snc.``,
           ``com.servicenow.``, ``glide.``, ``sys.``) default to ``PLATFORM``
           -- these are SN-shipped plugins whose lack of a domain keyword
           indicates a platform feature rather than a product-family app.
        4. Fallback: ``UNCATEGORIZED`` (typically third-party / OEM apps).

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
    pid = plugin_id.lower()
    if any(pid.startswith(prefix) for prefix in _SN_SHIPPED_PREFIXES):
        return ProductFamily.PLATFORM
    return ProductFamily.UNCATEGORIZED
