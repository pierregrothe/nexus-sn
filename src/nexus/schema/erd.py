# src/nexus/schema/erd.py
# Renders a SchemaGraph to a Markdown + Mermaid erDiagram document.
# Author: Pierre Grothe
# Date: 2026-06-08
"""MermaidErdEmitter: SchemaGraph -> Markdown with a Mermaid erDiagram."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from nexus.schema.models import InheritanceEdge, ReferenceEdge, SchemaGraph, TableDef

__all__ = ["GroupDiagram", "MermaidErdEmitter"]

_NON_TOKEN = re.compile(r"[^A-Za-z0-9_]")


def _token(text: str, fallback: str) -> str:
    """Reduce text to a Mermaid attribute token (word characters only).

    Args:
        text: Raw type or element name.
        fallback: Value to use when sanitizing leaves an empty string.

    Returns:
        A single word-character token safe for a Mermaid attribute line.
    """
    return _NON_TOKEN.sub("_", text) or fallback


def _entity_attributes(table: TableDef) -> list[str]:
    """Build the key-field attribute lines for one entity box.

    Shows the primary key (``sys_id``) first, then business columns, then
    foreign keys; business and FK sections are sorted by field name.
    ``sys_*`` audit columns are hidden to keep boxes legible.

    Args:
        table: The table whose key fields to render.

    Returns:
        Indented Mermaid attribute lines, ordered PK, business, FK.
    """
    pk: list[str] = []
    business: list[str] = []
    fks: list[str] = []
    for fld in sorted(table.fields, key=lambda f: f.name):
        ftype = _token(fld.type, "field")
        fname = _token(fld.name, "field")
        if fld.name == "sys_id":
            pk.append(f"        {ftype} {fname} PK")
        elif fld.name.startswith("sys_"):
            continue
        elif fld.reference_target:
            fks.append(f"        {ftype} {fname} FK")
        else:
            business.append(f"        {ftype} {fname}")
    return pk + business + fks


def _entity_block(table: TableDef) -> list[str]:
    """Build one full entity block (open line, attributes, close line).

    Args:
        table: The table to render.

    Returns:
        The block lines, or an empty list when the table has no visible
        attributes (the no-attrs-no-block rule).
    """
    attrs = _entity_attributes(table)
    if not attrs:
        return []
    return [f"    {table.name} {{", *attrs, "    }"]


def _reference_line(edge: ReferenceEdge) -> str:
    """Render one reference edge as a Mermaid relationship line.

    Args:
        edge: The reference edge to render.

    Returns:
        The indented Mermaid relationship line.
    """
    cardinality = "}o--o{" if edge.is_list else "}o--||"
    return f'    {edge.from_table} {cardinality} {edge.to_table} : "{edge.field}"'


def _inheritance_line(edge: InheritanceEdge) -> str:
    """Render one inheritance (extends) edge as a Mermaid relationship line.

    Args:
        edge: The inheritance edge to render.

    Returns:
        The indented Mermaid relationship line.
    """
    return f'    {edge.extends} ||--|| {edge.table} : "extends"'


def _header_lines(graph: SchemaGraph) -> list[str]:
    """Build the document title, instance, and discovered preamble lines.

    Args:
        graph: The graph whose metadata to render.

    Returns:
        The Markdown preamble lines shared by all document renders.
    """
    return [
        f"# Schema ERD: {graph.area_key}",
        "",
        f"Instance: `{graph.instance_id}`  |  scopes: {', '.join(graph.scope_keys)}",
        f"Discovered: {graph.discovered_at.isoformat()}",
        "",
    ]


def _bridge_lines(graph: SchemaGraph) -> list[str]:
    """Build the cross-scope bridges section lines.

    Args:
        graph: The graph whose cross-scope edges to list.

    Returns:
        The bridge-section Markdown lines.
    """
    lines = ["## Cross-scope bridges", ""]
    bridges = graph.cross_scope_edges()
    if bridges:
        for e in bridges:
            lines.append(f"- {e.from_table}.{e.field} -> {e.to_table}")
    else:
        lines.append("- (none)")
    lines.append("")
    return lines


def _field_lines(graph: SchemaGraph) -> list[str]:
    """Build the per-table field appendix lines.

    Args:
        graph: The graph whose in-scope tables to list.

    Returns:
        The field-appendix Markdown lines.
    """
    lines = ["## Fields", ""]
    for table in graph.tables:
        if table.is_neighbor:
            continue
        lines.append(f"### {table.name} -- {table.label}")
        lines.append("")
        lines.append("| Field | Type | References |")
        lines.append("| --- | --- | --- |")
        for fld in table.fields:
            lines.append(f"| {fld.name} | {fld.type} | {fld.reference_target or ''} |")
        lines.append("")
    return lines


@dataclass(slots=True)
class GroupDiagram:
    """One per-scope diagram produced by a grouped render.

    Args:
        key: The scope key the group owns.
        label: Human-readable group label (falls back to the scope key).
        source: Bare Mermaid ``erDiagram`` source for the group.
    """

    key: str
    label: str
    source: str


class MermaidErdEmitter:
    """Renders a SchemaGraph to a single-diagram Markdown ERD document."""

    def diagram(self, graph: SchemaGraph) -> str:
        """Render only the Mermaid ``erDiagram`` source (no Markdown wrapper).

        Each in-scope entity carries its key fields (PK, foreign keys, and
        business columns) inside the box; neighbors stay as bare boxes.
        Entity blocks are emitted in table-name order so output is
        deterministic regardless of graph tuple order.

        Args:
            graph: The graph to render.

        Returns:
            The Mermaid diagram source, suitable for a render service.
        """
        lines: list[str] = ["erDiagram"]
        for table in sorted(graph.tables, key=lambda t: t.name):
            if table.is_neighbor:
                continue
            lines.extend(_entity_block(table))
        for edge in graph.reference_edges:
            lines.append(_reference_line(edge))
        for inh in graph.inheritance_edges:
            lines.append(_inheritance_line(inh))
        return "\n".join(lines)

    def group_diagrams(
        self, graph: SchemaGraph, labels: Mapping[str, str]
    ) -> tuple[GroupDiagram, ...]:
        """Split the graph into one bare Mermaid diagram per owning scope.

        Groups are the distinct scope keys of non-neighbor tables, sorted by
        scope key. Each reference edge lands in its ``from_table``'s group
        and each inheritance edge in its child's group; edges whose owning
        table is unknown or a neighbor are skipped defensively. Edge targets
        not owned by the group appear bare (name-only, via the edge line),
        exactly how neighbors render in :meth:`diagram`. Entity blocks sort
        by table name; reference edges sort by (from_table, field) and
        precede inheritance edges, which sort by (extends, table).

        Args:
            graph: The graph to split.
            labels: Scope-key to display-label mapping; missing keys fall
                back to the scope key itself.

        Returns:
            One GroupDiagram per scope, in scope-key order.
        """
        by_name = {t.name: t for t in graph.tables}
        scopes = sorted({t.scope for t in graph.tables if not t.is_neighbor})
        refs: dict[str, list[ReferenceEdge]] = {s: [] for s in scopes}
        inhs: dict[str, list[InheritanceEdge]] = {s: [] for s in scopes}
        for edge in graph.reference_edges:
            owner = by_name.get(edge.from_table)
            if owner is not None and not owner.is_neighbor:
                refs[owner.scope].append(edge)
        for inh in graph.inheritance_edges:
            child = by_name.get(inh.table)
            if child is not None and not child.is_neighbor:
                inhs[child.scope].append(inh)
        diagrams: list[GroupDiagram] = []
        for scope in scopes:
            owned = (t for t in graph.tables if not t.is_neighbor and t.scope == scope)
            lines: list[str] = ["erDiagram"]
            for table in sorted(owned, key=lambda t: t.name):
                lines.extend(_entity_block(table))
            for edge in sorted(refs[scope], key=lambda e: (e.from_table, e.field)):
                lines.append(_reference_line(edge))
            for inh in sorted(inhs[scope], key=lambda e: (e.extends, e.table)):
                lines.append(_inheritance_line(inh))
            diagrams.append(
                GroupDiagram(key=scope, label=labels.get(scope, scope), source="\n".join(lines))
            )
        return tuple(diagrams)

    def render(self, graph: SchemaGraph) -> str:
        """Render the full Markdown document.

        Args:
            graph: The graph to render.

        Returns:
            A Markdown string with a Mermaid erDiagram, a cross-scope bridge
            list, and a per-table field appendix.
        """
        lines = _header_lines(graph)
        lines.extend(["```mermaid", self.diagram(graph), "```", ""])
        lines.extend(_bridge_lines(graph))
        lines.extend(_field_lines(graph))
        return "\n".join(lines)

    def render_grouped(self, graph: SchemaGraph, labels: Mapping[str, str]) -> str:
        """Render the full Markdown document with one diagram per scope.

        Same frame as :meth:`render` (title, instance, discovered lines, the
        cross-scope bridge list, and the field appendix exactly once), but
        the single dense diagram is replaced by one ``## {label}`` heading
        plus Mermaid fence per scope group.

        Args:
            graph: The graph to render.
            labels: Scope-key to display-label mapping for group headings.

        Returns:
            The grouped Markdown ERD document.
        """
        lines = _header_lines(graph)
        for group in self.group_diagrams(graph, labels):
            lines.extend([f"## {group.label}", "", "```mermaid", group.source, "```", ""])
        lines.extend(_bridge_lines(graph))
        lines.extend(_field_lines(graph))
        return "\n".join(lines)
