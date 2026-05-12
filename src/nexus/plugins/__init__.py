# src/nexus/plugins/__init__.py
# Public re-exports for the plugins layer.
# Author: Pierre Grothe
# Date: 2026-05-11
"""nexus.plugins: read-only plugin inventory layer.

Exports the data models, scanner, error type, product-family lookup,
the cross-instance diff/promote helpers, and the update-detection
filter.
"""

from nexus.plugins.diff import (
    PluginDiff,
    PluginDiffEntry,
    PromoteAction,
    PromotionPlan,
    compute_diff,
    project_to_promote_plan,
)
from nexus.plugins.errors import PluginScanError
from nexus.plugins.models import PluginInfo, PluginInventory, ProductFamily
from nexus.plugins.product_families import product_family_for
from nexus.plugins.scanner import PluginScanner
from nexus.plugins.updates import plugins_with_updates

__all__ = [
    "PluginDiff",
    "PluginDiffEntry",
    "PluginInfo",
    "PluginInventory",
    "PluginScanError",
    "PluginScanner",
    "ProductFamily",
    "PromoteAction",
    "PromotionPlan",
    "compute_diff",
    "plugins_with_updates",
    "product_family_for",
    "project_to_promote_plan",
]
