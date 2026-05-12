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
from nexus.plugins.diff import (
    PluginDiff,
    PluginDiffEntry,
    PromoteAction,
    PromotionPlan,
    compute_diff,
    project_to_promote_plan,
)
from nexus.plugins.errors import (
    PluginAdvisoryDataError,
    PluginImpactError,
    PluginScanError,
)
from nexus.plugins.impact import compute_impact, reverse_dependencies
from nexus.plugins.models import (
    AdvisoryFinding,
    AdvisorySet,
    AdvisoryType,
    PluginImpact,
    PluginInfo,
    PluginInventory,
    ProductFamily,
    ReverseDependency,
    ScopeRecordCount,
    Severity,
)
from nexus.plugins.orphans import orphan_candidates
from nexus.plugins.product_families import product_family_for
from nexus.plugins.scanner import PluginScanner
from nexus.plugins.updates import plugins_with_updates

__all__ = [
    "AdvisoryDatabase",
    "AdvisoryFinding",
    "AdvisorySet",
    "AdvisoryType",
    "PluginAdvisoryDataError",
    "PluginDiff",
    "PluginDiffEntry",
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
    "compute_advisories",
    "compute_diff",
    "compute_impact",
    "orphan_candidates",
    "plugins_with_updates",
    "product_family_for",
    "project_to_promote_plan",
    "reverse_dependencies",
]
