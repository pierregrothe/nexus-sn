# src/nexus/schema/protocol.py
# Structural protocol the CLI binds to for schema cartography.
# Author: Pierre Grothe
# Date: 2026-06-08
"""SchemaProtocol: the surface CLI/TUI depend on (not the concrete engine)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from nexus.api.kroki_client import ImageFormat
from nexus.schema.models import SchemaGraph

__all__ = ["SchemaProtocol"]


class SchemaProtocol(Protocol):
    """Discover, persist, and render schema graphs."""

    async def discover(self, instance_id: str, area_key: str) -> SchemaGraph:
        """Reverse-engineer one area into a SchemaGraph."""
        ...

    def save_archive(self, graph: SchemaGraph, dest: Path | None = None) -> Path:
        """Persist a graph as JSON; return the written path."""
        ...

    def load_archive(self, path: Path) -> SchemaGraph:
        """Load a graph snapshot from JSON."""
        ...

    def render_erd(self, graph: SchemaGraph) -> str:
        """Render a graph to Markdown + Mermaid."""
        ...

    async def render_erd_image(self, graph: SchemaGraph, *, fmt: ImageFormat) -> bytes:
        """Render a graph's ERD to image bytes via the Kroki service."""
        ...
