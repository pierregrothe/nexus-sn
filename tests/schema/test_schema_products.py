# tests/schema/test_schema_products.py
# Tests for SchemaProduct and SchemaProductCatalog models.
# Author: Pierre Grothe
# Date: 2026-06-11
"""SchemaProduct model validation and catalog resolution."""

import importlib.resources

import pytest
from pydantic import ValidationError

from nexus.schema.models import ScopeEntry
from nexus.schema.products import SchemaProduct, SchemaProductCatalog


def _ham() -> SchemaProduct:
    return SchemaProduct(
        key="ham",
        acronym="HAM",
        name="Hardware Asset Management",
        scopes=(ScopeEntry(key="sn_hamp", label="Hardware Asset Management Pro"),),
        bridge_targets=("cmdb_ci",),
    )


def _itsm() -> SchemaProduct:
    return SchemaProduct(
        key="itsm",
        acronym="ITSM",
        name="IT Service Management",
        scopes=(),
        bridge_targets=("incident", "task", "cmdb_ci"),
    )


def _catalog() -> SchemaProductCatalog:
    return SchemaProductCatalog(version="1.0", products=(_ham(), _itsm()))


def test_schema_product_is_frozen() -> None:
    p = _ham()
    with pytest.raises(ValidationError):
        p.key = "new"  # type: ignore[misc]


def test_schema_product_catalog_resolves_by_key() -> None:
    assert _catalog().resolve("ham") == _ham()


def test_schema_product_catalog_resolves_by_acronym() -> None:
    assert _catalog().resolve("HAM") == _ham()


def test_schema_product_catalog_resolves_by_name() -> None:
    assert _catalog().resolve("Hardware Asset Management") == _ham()


def test_schema_product_catalog_resolve_is_case_insensitive() -> None:
    assert _catalog().resolve("hardware asset management") == _ham()
    assert _catalog().resolve("ham") == _ham()


def test_schema_product_catalog_resolve_unknown_returns_none() -> None:
    assert _catalog().resolve("NoSuchProduct") is None


def test_schema_product_bridge_only_has_no_scopes() -> None:
    p = _itsm()
    assert not p.scopes
    assert p.bridge_targets


def test_schema_product_catalog_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        SchemaProduct(
            key="x",
            acronym="X",
            name="X",
            scopes=(),
            bridge_targets=(),
            unknown_field="bad",  # type: ignore[call-arg]
        )


def test_bundled_catalog_parses_and_contains_required_products() -> None:
    data = importlib.resources.files("nexus.schema").joinpath("products.json").read_text(encoding="utf-8")
    catalog = SchemaProductCatalog.model_validate_json(data)
    keys = {p.key for p in catalog.products}
    assert {"ham", "itsm", "doc-designer", "bcm"} <= keys
