# src/nexus/schema/products.py
# Pydantic models for the schema product catalog.
# Author: Pierre Grothe
# Date: 2026-06-11
"""SchemaProduct, SchemaProductCatalog: the community-maintained product catalog."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from nexus.schema.models import ScopeEntry

__all__ = [
    "SchemaProduct",
    "SchemaProductCatalog",
]

_CONFIG = ConfigDict(frozen=True, strict=True, extra="forbid")


class SchemaProduct(BaseModel):
    """One product entry in the schema catalog.

    Args:
        key: Machine slug, e.g. "ham".
        acronym: Short form, e.g. "HAM".
        name: Full product name.
        scopes: Ordered list of sys_scope keys to discover.
        bridge_targets: Tables used as bridge narrowing targets. Empty
            for unrestricted discovery. Products with empty scopes are
            bridge-only and cannot be used as the sole ERD argument.
    """

    model_config = _CONFIG

    key: str
    acronym: str
    name: str
    scopes: tuple[ScopeEntry, ...]
    bridge_targets: tuple[str, ...] = ()


class SchemaProductCatalog(BaseModel):
    """The full product catalog, either bundled or synced from GitHub.

    Args:
        version: Schema version string, e.g. "1.0".
        products: Ordered collection of products.
    """

    model_config = _CONFIG

    version: str
    products: tuple[SchemaProduct, ...]

    def resolve(self, ref: str) -> SchemaProduct | None:
        """Find a product by key, acronym, or name (case-insensitive).

        Args:
            ref: Key, acronym, or full product name.

        Returns:
            The matching SchemaProduct, or None if not found.
        """
        needle = ref.lower()
        for p in self.products:
            if needle in (p.key.lower(), p.acronym.lower(), p.name.lower()):
                return p
        return None
