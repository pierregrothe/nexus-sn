# src/nexus/schema/__init__.py
# Schema cartography layer: reverse-engineer a live SN data dictionary into an ERD.
# Author: Pierre Grothe
# Date: 2026-06-08
"""nexus.schema -- ServiceNow data-dictionary cartographer."""

from nexus.schema.engine import SchemaCartographer
from nexus.schema.models import SchemaArea, SchemaGraph, ScopeEntry
from nexus.schema.protocol import SchemaProtocol

__all__ = [
    "SchemaArea",
    "SchemaCartographer",
    "SchemaGraph",
    "SchemaProtocol",
    "ScopeEntry",
]
