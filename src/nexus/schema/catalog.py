# src/nexus/schema/catalog.py
# Frozen Pydantic models for the AI-enriched mindmap catalog.
# Author: Pierre Grothe
# Date: 2026-06-08
"""TableDescription, Domain, and the MindmapCatalog aggregate."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

__all__ = ["Domain", "MindmapCatalog", "TableDescription"]

_CONFIG = ConfigDict(frozen=True, strict=True, extra="forbid")


class TableDescription(BaseModel):
    """One table's catalog entry.

    Args:
        table: Table API name.
        label: Table label (from the schema).
        description: One-line "Stores X" purpose.
        source: Where the description came from ("ai" or "label").
    """

    model_config = _CONFIG
    table: str
    label: str
    description: str
    source: str


class Domain(BaseModel):
    """A named business-domain grouping of tables.

    Args:
        name: Domain name (e.g. "Plan Management").
        tables: The tables in this domain.
    """

    model_config = _CONFIG
    name: str
    tables: tuple[TableDescription, ...]


class MindmapCatalog(BaseModel):
    """The full AI-enriched catalog for one area.

    Args:
        instance_id: Source instance profile name.
        area_key: Area key the catalog was built for.
        generated_at: UTC generation timestamp.
        display: Area display name (the mindmap root label).
        domains: The business domains and their tables.
    """

    model_config = _CONFIG
    instance_id: str
    area_key: str
    generated_at: datetime
    display: str
    domains: tuple[Domain, ...]
