# src/nexus/schema/mindmap_emitter.py
# Renders a MindmapCatalog to Markdown with a Mermaid mindmap.
# Author: Pierre Grothe
# Date: 2026-06-08
"""MindmapEmitter: MindmapCatalog -> Markdown (mindmap block + grouped catalog)."""

from __future__ import annotations

from nexus.schema.catalog import MindmapCatalog

__all__ = ["MindmapEmitter"]


class MindmapEmitter:
    """Renders a MindmapCatalog to a Markdown mindmap document."""

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
            "mindmap",
            f"  root(({catalog.display}))",
        ]
        for domain in catalog.domains:
            lines.append(f"    {domain.name}")
            for table in domain.tables:
                lines.append(f"      {table.label} -- {table.table}")
        lines.append("```")
        lines.append("")
        for domain in catalog.domains:
            lines.append(f"## {domain.name}")
            lines.append("")
            for table in domain.tables:
                lines.append(f"- **{table.label}** [{table.table}]: {table.description}")
            lines.append("")
        return "\n".join(lines)
