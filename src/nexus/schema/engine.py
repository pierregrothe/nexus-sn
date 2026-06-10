# src/nexus/schema/engine.py
# Concrete SchemaCartographer wiring discoverer + archive + emitter.
# Author: Pierre Grothe
# Date: 2026-06-08
"""SchemaCartographer: implements SchemaProtocol over a live client."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path

from nexus.api.kroki_client import ImageFormat, KrokiClientProtocol
from nexus.connectors.servicenow.protocol import ServiceNowClientProtocol
from nexus.schema.archive import SchemaArchiveReader, SchemaArchiveWriter
from nexus.schema.areas import DEFAULT_AREAS, SchemaArea
from nexus.schema.discoverer import SchemaDiscoverer
from nexus.schema.erd import MermaidErdEmitter
from nexus.schema.models import SchemaGraph

__all__ = ["SchemaCartographer"]


class SchemaCartographer:
    """Wires discovery, archiving, and ERD rendering behind one object.

    Args:
        client: Open ServiceNow client.
        areas: Area registry.
        archive_root: Root directory for JSON snapshots.
        kroki: Kroki render client for diagram image export.
        clock: UTC clock (injectable for tests).
    """

    def __init__(
        self,
        client: ServiceNowClientProtocol,
        areas: Mapping[str, SchemaArea] = DEFAULT_AREAS,
        *,
        archive_root: Path,
        kroki: KrokiClientProtocol,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """Initialize the cartographer and its components."""
        self._discoverer = SchemaDiscoverer(client, areas, clock)
        self._reader = SchemaArchiveReader()
        self._emitter = MermaidErdEmitter()
        self._kroki = kroki
        self._archive_root = archive_root

    async def discover(self, instance_id: str, area_key: str) -> SchemaGraph:
        """Reverse-engineer one area into a SchemaGraph.

        Args:
            instance_id: Registered instance profile name.
            area_key: Key into the area registry.

        Returns:
            The discovered SchemaGraph.
        """
        return await self._discoverer.discover(instance_id, area_key)

    def save_archive(self, graph: SchemaGraph, dest: Path | None = None) -> Path:
        """Persist a graph as JSON under dest or the configured archive root.

        Args:
            graph: The graph to persist.
            dest: Optional override root; defaults to the configured archive root.

        Returns:
            Path to the written JSON file.
        """
        return SchemaArchiveWriter(dest or self._archive_root).write(graph)

    def load_archive(self, path: Path) -> SchemaGraph:
        """Load a graph snapshot from JSON.

        Args:
            path: Path to a snapshot JSON file.

        Returns:
            The reconstructed SchemaGraph.
        """
        return self._reader.read(path)

    def render_erd(self, graph: SchemaGraph) -> str:
        """Render a graph to Markdown + Mermaid.

        Args:
            graph: The graph to render.

        Returns:
            The Markdown ERD document.
        """
        return self._emitter.render(graph)

    async def render_erd_image(self, graph: SchemaGraph, *, fmt: ImageFormat) -> bytes:
        """Render a graph's ERD to image bytes via the Kroki service.

        Args:
            graph: The graph to render.
            fmt: Output image format.

        Returns:
            The rendered image bytes.
        """
        return await self._kroki.render(self._emitter.diagram(graph), fmt=fmt)

    def render_erd_grouped(self, graph: SchemaGraph, labels: Mapping[str, str]) -> str:
        """Render a graph to Markdown with one Mermaid diagram per scope.

        Args:
            graph: The graph to render.
            labels: Scope-key to display-label mapping for group headings.

        Returns:
            The grouped Markdown ERD document.
        """
        return self._emitter.render_grouped(graph, labels)

    async def render_erd_group_images(
        self, graph: SchemaGraph, labels: Mapping[str, str], *, fmt: ImageFormat
    ) -> tuple[tuple[str, bytes], ...]:
        """Render one image per scope group via the Kroki service.

        Args:
            graph: The graph to render.
            labels: Scope-key to display-label mapping (group labels).
            fmt: Output image format.

        Returns:
            (scope key, image bytes) pairs in group (scope-key) order.
        """
        rendered: list[tuple[str, bytes]] = []
        for group in self._emitter.group_diagrams(graph, labels):
            rendered.append((group.key, await self._kroki.render(group.source, fmt=fmt)))
        return tuple(rendered)
