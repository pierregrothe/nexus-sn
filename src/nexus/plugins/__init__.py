# src/nexus/plugins/__init__.py
# Public re-exports for the plugins layer.
# Author: Pierre Grothe
# Date: 2026-05-11
"""nexus.plugins: read-only plugin inventory layer.

Exports the data models, scanner, error types, product-family lookup,
the cross-instance diff/promote helpers, the update-detection filter,
the advisory checkers (EOL, CVE, license), the impact analyzer
(reverse-dep graph + scope record counts), and the orphan filter.
"""

from nexus.plugins.advisories import AdvisoryDatabase, compute_advisories
from nexus.plugins.baselines import DEFAULT_BASELINE_NAME, validate_baseline_name
from nexus.plugins.diff import (
    PluginDiff,
    PluginDiffEntry,
    PromoteAction,
    PromotionPlan,
    compute_diff,
    project_to_promote_plan,
)
from nexus.plugins.drift import (
    PluginDriftEntry,
    PluginDriftReport,
    compute_drift,
)
from nexus.plugins.errors import (
    AdvisoryOverrideError,
    BaselineNotFoundError,
    InvalidBaselineNameError,
    PluginAdvisoryDataError,
    PluginBaselineNotFoundError,
    PluginImpactError,
    PluginScanError,
)
from nexus.plugins.impact import compute_impact, reverse_dependencies
from nexus.plugins.models import (
    AdvisoryFinding,
    AdvisorySet,
    AdvisoryType,
    CrossScopeRef,
    PluginImpact,
    PluginInfo,
    PluginInventory,
    ProductFamily,
    ReverseDependency,
    ScopeRecordCount,
    Severity,
)
from nexus.plugins.orphans import orphan_candidates
from nexus.plugins.recommendations import (
    AI_MODEL,
    build_deactivation_context,
    build_explain_context,
    build_roadmap_context,
)
from nexus.plugins.overrides import AdvisoryOverride, AdvisoryOverrideSet, apply_overrides
from nexus.plugins.product_families import product_family_for
from nexus.plugins.scanner import PluginScanner
from nexus.plugins.updates import plugins_with_updates

__all__ = [
    "DEFAULT_BASELINE_NAME",
    "AdvisoryDatabase",
    "AdvisoryFinding",
    "AdvisoryOverride",
    "AdvisoryOverrideError",
    "AdvisoryOverrideSet",
    "AdvisorySet",
    "AdvisoryType",
    "BaselineNotFoundError",
    "CrossScopeRef",
    "InvalidBaselineNameError",
    "PluginAdvisoryDataError",
    "PluginBaselineNotFoundError",
    "PluginDiff",
    "PluginDiffEntry",
    "PluginDriftEntry",
    "PluginDriftReport",
    "PluginImpact",
    "PluginImpactError",
    "PluginInfo",
    "PluginInventory",
    "PluginScanError",
    "PluginScanner",
    "ProductFamily",
    "PromoteAction",
    "PromotionPlan",
    "ReverseDependency",
    "ScopeRecordCount",
    "Severity",
    "apply_overrides",
    "compute_advisories",
    "compute_diff",
    "compute_drift",
    "compute_impact",
    "AI_MODEL",
    "build_deactivation_context",
    "build_explain_context",
    "build_roadmap_context",
    "orphan_candidates",
    "plugins_with_updates",
    "product_family_for",
    "project_to_promote_plan",
    "reverse_dependencies",
    "validate_baseline_name",
]
