# src/nexus/replatform/classifier.py
# Deterministic use-case classifier for the replatform analysis layer.
# Author: Pierre Grothe
# Date: 2026-06-29

"""Pure, LLM-free classification of captured artifacts into a UseCaseInventory.

The classifier consumes already-loaded capture data (``CaptureResult`` tuples
plus a ``ScopeManifest``) and the schema product catalog. It performs no I/O, no
LLM call, and no MCP call. Custom scopes absent from the catalog collapse to the
``Uncategorized`` domain.
"""

from nexus.capture.models import CaptureResult, ScopeManifest, SnFieldValue
from nexus.replatform.models import UseCase, UseCaseInventory, WorkflowRef
from nexus.schema.products import SchemaProductCatalog

__all__ = ["classify"]

_UNCATEGORIZED = "Uncategorized"


def classify(
    captures: tuple[CaptureResult, ...],
    scopes: ScopeManifest,
    catalog: SchemaProductCatalog,
    *,
    profile: str,
    skipped_tables: tuple[str, ...] = (),
) -> UseCaseInventory:
    """Classify captured artifacts into a deterministic use-case inventory.

    Args:
        captures: Captures for one instance. Plural for forward-compat with
            future table groups; one ``AI_AUTOMATION`` capture suffices today.
        scopes: Scope manifest used to resolve ``ConfigRecord.scope_sys_id`` to
            the technical scope key (``ScopeEntry.scope``).
        catalog: Schema product catalog. Its ``{scope.key: product.name}`` map
            supplies each use case's domain; unknown scopes -> ``Uncategorized``.
        profile: Instance profile name recorded on the inventory.
        skipped_tables: Tables absent on this instance (HTTP 400/404 during the
            live listing), recorded on the inventory sorted for transparency.

    Returns:
        A frozen ``UseCaseInventory`` whose use cases are grouped by domain and
        sorted by ``(domain, workflow key)`` for byte-stable output.
    """
    sys_to_scope = {entry.sys_id: entry.scope for entry in scopes.scopes}
    scope_to_domain = {
        scope.key: product.name for product in catalog.products for scope in product.scopes
    }
    by_domain: dict[str, list[WorkflowRef]] = {}
    evidence: dict[str, set[str]] = {}
    coverage: set[str] = set()
    for capture in captures:
        coverage.add(capture.table_group)
        for record in capture.records:
            scope_key = sys_to_scope.get(record.scope_sys_id) or record.scope_name
            domain = scope_to_domain.get(scope_key, _UNCATEGORIZED)
            name = _display_name(record.fields.get("name", ""))
            # Unnamed records have no stable cross-instance identity; fall back to
            # the sys_id so the natural key stays unique (no collision/over-count).
            key_segment = _normalize(name) or record.sys_id
            ref = WorkflowRef(
                key=f"{scope_key}|{record.table}|{key_segment}",
                name=name,
                type=record.table,
                scope=scope_key,
            )
            by_domain.setdefault(domain, []).append(ref)
            evidence.setdefault(domain, set()).add(scope_key)
    use_cases = tuple(
        UseCase(
            key=domain,
            name=domain,
            domain=domain,
            workflows=tuple(sorted(refs, key=lambda ref: ref.key)),
            evidence=tuple(sorted(evidence[domain])),
        )
        for domain, refs in sorted(by_domain.items())
    )
    return UseCaseInventory(
        profile=profile,
        captured_at=scopes.captured_at,
        coverage=tuple(sorted(coverage)),
        use_cases=use_cases,
        skipped_tables=tuple(sorted(skipped_tables)),
    )


def _display_name(raw: SnFieldValue) -> str:
    """Return the display string from a captured field value.

    Args:
        raw: A captured field value -- either a plain string or a reference
            field carrying ``value`` + ``display_value``.

    Returns:
        The display string (``display_value`` for reference fields).
    """
    if isinstance(raw, dict):
        return raw["display_value"]
    return raw


def _normalize(name: str) -> str:
    """Casefold and collapse whitespace for a stable natural-key segment."""
    return " ".join(name.split()).casefold()
