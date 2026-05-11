# src/nexus/plugins/__init__.py
# Public re-exports for the plugins layer.
# Author: Pierre Grothe
# Date: 2026-05-11
"""nexus.plugins: read-only plugin inventory layer.

Exports the data models, scanner, error type, and product-family lookup.
The layer imports from cache/, config/, and connectors/ only -- never up.
"""

from nexus.plugins.errors import PluginScanError
from nexus.plugins.models import PluginInfo, PluginInventory, ProductFamily
from nexus.plugins.product_families import product_family_for
from nexus.plugins.scanner import PluginScanner

__all__ = [
    "PluginInfo",
    "PluginInventory",
    "PluginScanError",
    "PluginScanner",
    "ProductFamily",
    "product_family_for",
]
