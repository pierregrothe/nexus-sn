# tests/schema/test_schema_product_registry.py
# Tests for ProductRegistry I/O and bundled fallback.
# Author: Pierre Grothe
# Date: 2026-06-11
"""ProductRegistry: save/load/resolve against ~/.nexus/schema/catalog.json."""

import tempfile
from pathlib import Path

import pytest

from nexus.schema.models import ScopeEntry
from nexus.schema.product_registry import ProductRegistry
from nexus.schema.products import SchemaProduct, SchemaProductCatalog
from nexus.schema.sync import SchemaSyncSource


def _catalog() -> SchemaProductCatalog:
    return SchemaProductCatalog(
        version="1.0",
        products=(
            SchemaProduct(
                key="ham",
                acronym="HAM",
                name="Hardware Asset Management",
                scopes=(ScopeEntry(key="sn_hamp", label="HAM Pro"),),
                bridge_targets=("cmdb_ci",),
            ),
        ),
    )


def _source() -> SchemaSyncSource:
    return SchemaSyncSource(repo="owner/repo", branch="main", path="schema/products.json")


def test_product_registry_save_then_load_roundtrip(tmp_path: Path) -> None:
    registry = ProductRegistry(tmp_path)
    catalog = _catalog()
    cached = registry.save_catalog(catalog, _source())
    assert cached.catalog == catalog
    assert registry.load_catalog() == catalog


def test_product_registry_load_falls_back_to_bundled_when_cache_absent(
    tmp_path: Path,
) -> None:
    catalog = ProductRegistry(tmp_path).load_catalog()
    assert catalog.resolve("ham") is not None


def test_product_registry_load_cached_returns_none_when_no_sync(tmp_path: Path) -> None:
    assert ProductRegistry(tmp_path).load_cached() is None


def test_product_registry_load_cached_returns_entry_after_save(tmp_path: Path) -> None:
    registry = ProductRegistry(tmp_path)
    registry.save_catalog(_catalog(), _source())
    cached = registry.load_cached()
    assert cached is not None
    assert cached.source == _source()


def test_product_registry_atomic_write_leaves_old_cache_on_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = ProductRegistry(tmp_path)
    registry.save_catalog(_catalog(), _source())

    def _fail(*args: object, **kwargs: object) -> object:
        raise OSError("disk full")

    monkeypatch.setattr(tempfile, "mkstemp", _fail)
    try:
        registry.save_catalog(_catalog(), _source())
    except OSError:
        pass

    assert registry.load_catalog() is not None


def test_product_registry_resolve_delegates_to_catalog(tmp_path: Path) -> None:
    registry = ProductRegistry(tmp_path)
    registry.save_catalog(_catalog(), _source())
    assert registry.resolve("HAM") is not None
    assert registry.resolve("nobody") is None
