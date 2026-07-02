# tests/fakes/replatform.py
# Builders for replatform classifier/diff test fixtures.
# Author: Pierre Grothe
# Date: 2026-06-29

"""Factory helpers for replatform tests.

Build real ScopeManifest and SchemaProductCatalog instances (and, for the diff
story, UseCaseInventory instances) without re-implementing the capture or schema
layers.
"""

from __future__ import annotations

from datetime import UTC, datetime

from nexus.capture.models import ScopeEntry, ScopeManifest
from nexus.replatform.models import UseCase, UseCaseInventory, WorkflowRef
from nexus.schema.models import ScopeEntry as SchemaScopeEntry
from nexus.schema.products import SchemaProduct, SchemaProductCatalog

__all__ = [
    "make_schema_catalog",
    "make_scope_manifest",
    "make_use_case",
    "make_use_case_inventory",
    "make_workflow_ref",
]

_DEFAULT_TS = datetime(2026, 6, 29, 12, 0, 0, tzinfo=UTC)


def make_scope_manifest(
    *,
    scopes: dict[str, str],
    names: dict[str, str] | None = None,
    instance_id: str = "dev",
    captured_at: datetime = _DEFAULT_TS,
) -> ScopeManifest:
    """Build a ScopeManifest from a ``sys_id -> technical-scope-key`` mapping.

    Args:
        scopes: Mapping of scope sys_id to technical scope key.
        names: Optional mapping of scope sys_id to display name; entries
            default to the scope key when absent.
        instance_id: Manifest instance profile.
        captured_at: Manifest capture timestamp.
    """
    entries = tuple(
        ScopeEntry(
            sys_id=sys_id,
            name=(names or {}).get(sys_id, scope_key),
            scope=scope_key,
            version="1.0",
            vendor="test",
            table_counts={},
        )
        for sys_id, scope_key in scopes.items()
    )
    return ScopeManifest(instance_id=instance_id, captured_at=captured_at, scopes=entries)


def make_schema_catalog(
    *,
    scope_to_product: dict[str, str],
    version: str = "1.0",
) -> SchemaProductCatalog:
    """Build a SchemaProductCatalog from a ``scope-key -> product-name`` mapping."""
    by_product: dict[str, list[str]] = {}
    for scope_key, product_name in scope_to_product.items():
        by_product.setdefault(product_name, []).append(scope_key)
    products = tuple(
        SchemaProduct(
            key=product_name.lower().replace(" ", "-"),
            acronym=product_name[:4].upper() or "X",
            name=product_name,
            scopes=tuple(SchemaScopeEntry(key=sk, label=product_name) for sk in scope_keys),
        )
        for product_name, scope_keys in by_product.items()
    )
    return SchemaProductCatalog(version=version, products=products)


def make_workflow_ref(
    *,
    scope: str = "x_acme_app",
    table: str = "sys_hub_flow",
    name: str = "Create Incident",
) -> WorkflowRef:
    """Build a WorkflowRef with a normalized key derived from its parts."""
    key = f"{scope}|{table}|{' '.join(name.split()).casefold()}"
    return WorkflowRef(key=key, name=name, type=table, scope=scope)


def make_use_case(
    *,
    key: str = "x_acme_app",
    name: str = "Acme",
    domain: str = "Uncategorized",
    workflows: tuple[WorkflowRef, ...] | None = None,
    evidence: tuple[str, ...] = ("x_acme_app",),
) -> UseCase:
    """Build a UseCase with one default workflow when none are supplied."""
    refs = workflows if workflows is not None else (make_workflow_ref(scope=key),)
    return UseCase(key=key, name=name, domain=domain, workflows=refs, evidence=evidence)


def make_use_case_inventory(
    *,
    profile: str = "dev",
    captured_at: datetime = _DEFAULT_TS,
    coverage: tuple[str, ...] = ("ai_automation",),
    use_cases: tuple[UseCase, ...] | None = None,
    skipped_tables: tuple[str, ...] = (),
) -> UseCaseInventory:
    """Build a UseCaseInventory with one default use case when none are supplied."""
    cases = use_cases if use_cases is not None else (make_use_case(),)
    return UseCaseInventory(
        profile=profile,
        captured_at=captured_at,
        coverage=coverage,
        use_cases=cases,
        skipped_tables=skipped_tables,
    )
