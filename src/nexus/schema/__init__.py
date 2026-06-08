# src/nexus/schema/__init__.py
# Schema cartography layer: reverse-engineer a live SN data dictionary into an ERD.
# Author: Pierre Grothe
# Date: 2026-06-08
"""nexus.schema -- ServiceNow data-dictionary cartographer."""

from nexus.schema.areas import DEFAULT_AREAS, SchemaArea, ScopeRef
from nexus.schema.catalog import MindmapCatalog
from nexus.schema.engine import SchemaCartographer
from nexus.schema.models import SchemaGraph
from nexus.schema.protocol import SchemaProtocol

__all__ = [
    "DEFAULT_AREAS",
    "MindmapCatalog",
    "SchemaArea",
    "SchemaCartographer",
    "SchemaGraph",
    "SchemaProtocol",
    "ScopeRef",
]
