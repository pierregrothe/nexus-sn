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


def product_family_for(plugin_id: str) -> ProductFamily:
    """Return the curated ProductFamily for a plugin, or UNCATEGORIZED.

    Args:
        plugin_id: SN plugin identifier (v_plugin.id or sys_store_app.scope).

    Returns:
        ProductFamily enum member.
    """
    family_value = load_product_families().get(plugin_id)
    if family_value is None:
        return ProductFamily.UNCATEGORIZED
    return ProductFamily(family_value)
