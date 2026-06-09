# src/nexus/schema/erd.py
# Renders a SchemaGraph to a Markdown + Mermaid erDiagram document.
# Author: Pierre Grothe
# Date: 2026-06-08
"""MermaidErdEmitter: SchemaGraph -> Markdown with a Mermaid erDiagram."""

from __future__ import annotations

from nexus.schema.models import SchemaGraph

__all__ = ["MermaidErdEmitter"]


class MermaidErdEmitter:
    """Renders a SchemaGraph to a single-diagram Markdown ERD document."""

    def diagram(self, graph: SchemaGraph) -> str:
        """Render only the Mermaid ``erDiagram`` source (no Markdown wrapper).

        Args:
            graph: The graph to render.

        Returns:
            The Mermaid diagram source, suitable for a render service.
        """
        lines: list[str] = ["erDiagram"]
        for edge in graph.reference_edges:
            lines.append(f'    {edge.from_table} }}o--|| {edge.to_table} : "{edge.field}"')
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
