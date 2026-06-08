# src/nexus/schema/areas.py
# Pluggable registry of schema areas (scope groups) to map.
# Author: Pierre Grothe
# Date: 2026-06-08
"""SchemaArea registry: which SN application scopes form each cartography area."""

from dataclasses import dataclass

__all__ = [
    "BCM",
    "CMDB_BCM",
    "DEFAULT_AREAS",
    "DOC_DESIGNER",
    "SchemaArea",
    "ScopeRef",
]


@dataclass(slots=True, frozen=True)
class ScopeRef:
    """One application scope included in an area.

    Args:
        scope: The sys_scope.scope key, e.g. "sn_grc_doc_design".
        label: Human-readable product label.
    """

    scope: str
    label: str


@dataclass(slots=True, frozen=True)
class SchemaArea:
    """A named group of scopes to reverse-engineer together.

    Args:
        key: Machine-readable area key used in CLI and archives.
        display: Human-readable label.
        scopes: Scopes whose tables form the area.
        neighbor_hops: How many reference/inheritance hops outside the scopes
            to pull in as bridge nodes.
    """

    key: str
    display: str
    scopes: tuple[ScopeRef, ...]
    neighbor_hops: int = 1


DOC_DESIGNER = SchemaArea(
    key="doc-designer",
    display="Document Designer",
    scopes=(
        ScopeRef("sn_grc_doc_design", "Document Designer with Word"),
        ScopeRef("sn_grc_rel_config", "Data Relationships Framework"),
    ),
)

BCM = SchemaArea(
    key="bcm",
    display="Business Continuity Management",
    scopes=(
        ScopeRef("sn_bcm", "BCM Core"),
        ScopeRef("sn_bcm_lite", "BCM User Lite"),
        ScopeRef("sn_bcm_map", "Crisis Map"),
        ScopeRef("sn_bcp", "Business Continuity Planning"),
    ),
)

CMDB_BCM = SchemaArea(
    key="cmdb-bcm",
    display="CMDB <-> BCM bridge",
    scopes=(
        ScopeRef("sn_bcm", "BCM Core"),
        ScopeRef("sn_bcp", "Business Continuity Planning"),
    ),
)

DEFAULT_AREAS: dict[str, SchemaArea] = {a.key: a for a in (DOC_DESIGNER, BCM, CMDB_BCM)}
