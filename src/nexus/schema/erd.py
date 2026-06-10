# src/nexus/schema/erd.py
# Renders a SchemaGraph to a Markdown + Mermaid erDiagram document.
# Author: Pierre Grothe
# Date: 2026-06-08
"""MermaidErdEmitter: SchemaGraph -> Markdown with a Mermaid erDiagram."""

from __future__ import annotations

import re

from nexus.schema.models import SchemaGraph, TableDef

__all__ = ["MermaidErdEmitter"]

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
            attrs = _entity_attributes(table)
            if not attrs:
                continue
            lines.append(f"    {table.name} {{")
            lines.extend(attrs)
            lines.append("    }")
        for edge in graph.reference_edges:
            cardinality = "}o--o{" if edge.is_list else "}o--||"
            lines.append(f'    {edge.from_table} {cardinality} {edge.to_table} : "{edge.field}"')
        for inh in graph.inheritance_edges:
            lines.append(f'    {inh.extends} ||--|| {inh.table} : "extends"')
        return "\n".join(lines)

    def render(self, graph: SchemaGraph) -> str:
        """Render the full Markdown document.

        Args:
            graph: The graph to render.

        Returns:
            A Markdown string with a Mermaid erDiagram, a cross-scope bridge
            list, and a per-table field appendix.
        """
        lines: list[str] = [
            f"# Schema ERD: {graph.area_key}",
            "",
            f"Instance: `{graph.instance_id}`  |  scopes: {', '.join(graph.scope_keys)}",
            f"Discovered: {graph.discovered_at.isoformat()}",
            "",
            "```mermaid",
            self.diagram(graph),
            "```",
            "",
        ]

        lines.append("## Cross-scope bridges")
        lines.append("")
        bridges = graph.cross_scope_edges()
        if bridges:
            for e in bridges:
                lines.append(f"- {e.from_table}.{e.field} -> {e.to_table}")
        else:
            lines.append("- (none)")
        lines.append("")

        lines.append("## Fields")
        lines.append("")
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
        return "\n".join(lines)
