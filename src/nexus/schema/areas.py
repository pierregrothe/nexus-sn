# src/nexus/schema/areas.py
# Pluggable registry of schema areas (scope groups) to map.
# Author: Pierre Grothe
# Date: 2026-06-08
"""SchemaArea registry: which SN application scopes form each cartography area."""

from nexus.schema.models import SchemaArea, ScopeEntry

# Backward-compat alias -- removed in Task 8 when areas.py is deleted.
ScopeRef = ScopeEntry

__all__ = [
    "BCM",
    "CMDB_BCM",
    "DEFAULT_AREAS",
    "DOC_DESIGNER",
    "HAM_ITSM",
    "SchemaArea",
    "ScopeEntry",
    "ScopeRef",
]

DOC_DESIGNER = SchemaArea(
    key="doc-designer",
    display="Document Designer",
    scopes=(
        ScopeEntry("sn_grc_doc_design", "Document Designer with Word"),
        ScopeEntry("sn_grc_rel_config", "Data Relationships Framework"),
    ),
)

BCM = SchemaArea(
    key="bcm",
    display="Business Continuity Management",
    scopes=(
        ScopeEntry("sn_bcm", "BCM Core"),
        ScopeEntry("sn_bcm_lite", "BCM User Lite"),
        ScopeEntry("sn_bcm_map", "Crisis Map"),
        ScopeEntry("sn_bcp", "Business Continuity Planning"),
    ),
)

CMDB_BCM = SchemaArea(
    key="cmdb-bcm",
    display="CMDB <-> BCM bridge",
    scopes=(
        ScopeEntry("sn_bcm", "BCM Core"),
        ScopeEntry("sn_bcp", "Business Continuity Planning"),
    ),
    bridge_targets=("cmdb_ci",),
)

HAM_ITSM = SchemaArea(
    key="ham-itsm",
    display="Hardware Asset Management -> ITSM bridge",
    scopes=(
        ScopeEntry("sn_hamp", "Hardware Asset Management Pro"),
    ),
    bridge_targets=("cmdb_ci",),
)

DEFAULT_AREAS: dict[str, SchemaArea] = {
    a.key: a for a in (DOC_DESIGNER, BCM, CMDB_BCM, HAM_ITSM)
}
