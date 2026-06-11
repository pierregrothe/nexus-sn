# tests/fakes/fake_product_registry.py
# In-memory ProductRegistry for CLI tests.
# Author: Pierre Grothe
# Date: 2026-06-11
"""FakeProductRegistry: injectable stand-in backed by a fixed catalog."""

from __future__ import annotations

from pathlib import Path

from nexus.schema.product_registry import CachedSchemaProductCatalog, ProductRegistry
from nexus.schema.products import SchemaProduct, SchemaProductCatalog

__all__ = ["FakeProductRegistry"]


class FakeProductRegistry(ProductRegistry):
    """ProductRegistry that reads from a fixed in-memory catalog.

    Args:
        catalog: The catalog to serve from load_catalog() and resolve().
    """

    def __init__(self, catalog: SchemaProductCatalog) -> None:
        """See class docstring."""
        super().__init__(Path("/fake"))
        self._catalog = catalog

    def load_catalog(self) -> SchemaProductCatalog:
        """Return the fixed catalog."""
        return self._catalog

    def load_cached(self) -> CachedSchemaProductCatalog | None:
        """Always returns None -- no on-disk state."""
        return None

    def resolve(self, ref: str) -> SchemaProduct | None:
        """Resolve against the fixed catalog."""
        return self._catalog.resolve(ref)
