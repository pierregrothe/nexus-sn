# tests/test_plugins_product_families.py
# Tests for the product-family YAML loader.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for product_family_for() and load_product_families()."""

from nexus.plugins.models import ProductFamily
from nexus.plugins.product_families import (
    load_product_families,
    product_family_for,
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
