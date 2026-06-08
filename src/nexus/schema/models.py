# src/nexus/schema/models.py
# Frozen Pydantic models for the schema cartography graph.
# Author: Pierre Grothe
# Date: 2026-06-08
"""TableDef, FieldDef, edge models, and the SchemaGraph aggregate."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

__all__ = [
    "FieldDef",
    "InheritanceEdge",
    "ReferenceEdge",
    "RelationshipEdge",
    "SchemaGraph",
    "TableDef",
]

_CONFIG = ConfigDict(frozen=True, strict=True, extra="forbid")


class FieldDef(BaseModel):
    """One column on a table.

    Args:
        name: Field (element) name.
        label: Column label.
        type: "reference" for reference fields, "field" otherwise.
        reference_target: Target table name for reference fields, else None.
        mandatory: Whether the field is mandatory.
    """

    model_config = _CONFIG
    name: str
    label: str
    type: str
    reference_target: str | None = None
    mandatory: bool = False


class TableDef(BaseModel):
    """One table in the area (in-scope or a pulled-in neighbor).

    Args:
        name: Table API name.
        label: Table label.
        scope: Owning scope key, or "" for a neighbor.
        super_class: Parent table name (inheritance), or None.
        is_neighbor: True when pulled in via an edge rather than a scope.
        fields: The table's fields (empty for neighbors).
    """

    model_config = _CONFIG
    name: str
    label: str
    scope: str
    super_class: str | None = None
    is_neighbor: bool = False
    fields: tuple[FieldDef, ...] = ()


class ReferenceEdge(BaseModel):
    """A reference-field edge from one table to another.

    Args:
        from_table: Table carrying the reference field.
        field: The reference field element name.
        to_table: Target table name.
        cross_scope: True when from/to live in different scopes.
    """

    model_config = _CONFIG
    from_table: str
    field: str
    to_table: str
    cross_scope: bool


class InheritanceEdge(BaseModel):
    """A table-inheritance (extends) edge.

    Args:
        table: The child table.
        extends: The parent (super_class) table name.
        cross_scope: True when child/parent live in different scopes.
    """

    model_config = _CONFIG
    table: str
    extends: str
    cross_scope: bool


class RelationshipEdge(BaseModel):
    """A defined sys_relationship related-list edge.

    Args:
        name: Relationship name.
        apply_to: Parent table (the table the related list shows on).
        query_from: Related table.
    """

    model_config = _CONFIG
    name: str
    apply_to: str
    query_from: str


class SchemaGraph(BaseModel):
    """The full reverse-engineered graph for one area.

    Args:
        instance_id: Source instance profile name.
        area_key: Area key the graph was built for.
        discovered_at: UTC discovery timestamp.
        scope_keys: Scopes that resolved on the instance.
        tables: All tables (in-scope + neighbors).
        reference_edges: Reference-field edges.
        inheritance_edges: super_class edges.
        relationship_edges: Defined sys_relationship edges.
    """

    model_config = _CONFIG
    instance_id: str
    area_key: str
    discovered_at: datetime
    scope_keys: tuple[str, ...]
    tables: tuple[TableDef, ...]
    reference_edges: tuple[ReferenceEdge, ...]
    inheritance_edges: tuple[InheritanceEdge, ...]
    relationship_edges: tuple[RelationshipEdge, ...]

    def cross_scope_edges(self) -> tuple[ReferenceEdge, ...]:
        """Return reference edges that bridge two scopes.

        Returns:
            The subset of reference_edges whose cross_scope is True.
        """
        return tuple(e for e in self.reference_edges if e.cross_scope)
