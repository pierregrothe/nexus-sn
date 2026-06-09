# src/nexus/schema/mindmap_emitter.py
# Renders a MindmapCatalog to Markdown with a Mermaid mindmap.
# Author: Pierre Grothe
# Date: 2026-06-08
"""MindmapEmitter: MindmapCatalog -> Markdown (mindmap block + grouped catalog)."""

from __future__ import annotations

from nexus.schema.catalog import MindmapCatalog

__all__ = ["MindmapEmitter"]

# Characters that Mermaid mindmap parses as node-shape delimiters; stripped from
# plain (root/branch) node text so a label never accidentally opens a shape.
_SHAPE_CHARS = str.maketrans("", "", '()[]"`')


def _plain(text: str) -> str:
    """Sanitize text used as a bare (root/branch) mindmap node.

    Args:
        text: Raw node text.

    Returns:
        The text with shape-delimiter characters removed.
    """
    return text.translate(_SHAPE_CHARS).strip()


def _md(text: str) -> str:
    """Neutralize the Mermaid markdown-string delimiters in node content.

    Args:
        text: Raw text destined for a ``["`...`"]`` markdown-string node.

    Returns:
        The text with backticks and double quotes replaced by apostrophes.
    """
    return text.replace("`", "'").replace('"', "'")


class MindmapEmitter:
    """Renders a MindmapCatalog to a Markdown mindmap document."""

    def diagram(self, catalog: MindmapCatalog) -> str:
        """Render only the Mermaid ``mindmap`` source (no Markdown wrapper).

        Each leaf is a markdown-string node carrying the friendly label, the
        table name, and the "Stores X" description, so the rendered image is a
        self-contained "which table stores what" reference.

        Args:
            catalog: The catalog to render.

        Returns:
            The Mermaid mindmap source, suitable for a render service.
        """
        lines: list[str] = ["mindmap", f"  root(({_plain(catalog.display)}))"]
        for section in catalog.sections:
            lines.append(f"    {_plain(section.name)}")
            for domain in section.domains:
                lines.append(f"      {_plain(domain.name)}")
                for table in domain.tables:
                    node = f"**{_md(table.label)}** [{table.table}]: {_md(table.description)}"
                    lines.append(f'        {table.table}["`{node}`"]')
        return "\n".join(lines)

    def render(self, catalog: MindmapCatalog) -> str:
        """Render the catalog.

        Args:
            catalog: The enriched catalog to render.

        Returns:
            Markdown with a Mermaid ``mindmap`` block and a grouped catalog list.
        """
        lines: list[str] = [
            f"# Schema mindmap: {catalog.area_key}",
            "",
            f"Instance: `{catalog.instance_id}`  |  generated: {catalog.generated_at.isoformat()}",
            "",
            "```mermaid",
            self.diagram(catalog),
            "```",
            "",
        ]
        for section in catalog.sections:
            lines.append(f"## {section.name}")
            lines.append("")
            for domain in section.domains:
                lines.append(f"### {domain.name}")
                lines.append("")
                for table in domain.tables:
                    lines.append(f"- **{table.label}** [{table.table}]: {table.description}")
                lines.append("")
        return "\n".join(lines)
