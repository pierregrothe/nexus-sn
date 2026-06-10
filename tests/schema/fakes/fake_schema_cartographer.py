# tests/schema/fakes/fake_schema_cartographer.py
# In-memory SchemaProtocol fake for CLI tests.
# Author: Pierre Grothe
# Date: 2026-06-08
"""FakeSchemaCartographer: canned-graph substitute for SchemaCartographer."""

from __future__ import annotations

from pathlib import Path

from nexus.api.kroki_client import ImageFormat
from nexus.schema.models import SchemaGraph

__all__ = ["FakeSchemaCartographer"]


class FakeSchemaCartographer:
    """Returns a canned SchemaGraph and round-trips it through JSON.

    Doubles as the async client used in ``async with client`` in CLI tests.

    Args:
        graph: The graph returned by discover() and persisted by save_archive().
        image: Canned image bytes returned by render_erd_image().
        discover_error: When set, discover() raises it instead of returning.
        image_error: When set, render_erd_image() raises it instead of returning.
    """

    def __init__(
        self,
        graph: SchemaGraph,
        image: bytes = b"<svg/>",
        discover_error: Exception | None = None,
        image_error: Exception | None = None,
    ) -> None:
        """Initialize with the canned graph, image bytes, and optional errors."""
        self._graph = graph
        self._image = image
        self._discover_error = discover_error
        self._image_error = image_error

    async def __aenter__(self) -> FakeSchemaCartographer:
        """Enter the async context (returns self)."""
        return self

    async def __aexit__(self, *_: object) -> None:
        """Exit the async context (no-op)."""

    async def discover(self, instance_id: str, area_key: str) -> SchemaGraph:
        """Return the canned graph regardless of inputs.

        Args:
            instance_id: Ignored.
            area_key: Ignored.

        Returns:
            The canned SchemaGraph.

        Raises:
            Exception: The configured ``discover_error`` when set.
        """
        del instance_id, area_key
        if self._discover_error is not None:
            raise self._discover_error
        return self._graph

    def save_archive(self, graph: SchemaGraph, dest: Path | None = None) -> Path:
        """Write the graph JSON under dest (defaults to cwd) and return the path.

        Args:
            graph: The graph to persist.
            dest: Destination directory; defaults to the current directory.

        Returns:
            Path to the written JSON file.
        """
        root = dest or Path.cwd()
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"{graph.area_key}.json"
        path.write_text(graph.model_dump_json(indent=2), encoding="utf-8")
        return path

    def load_archive(self, path: Path) -> SchemaGraph:
        """Reload a graph snapshot from JSON.

        Args:
            path: Path to a snapshot JSON file.

        Returns:
            The reconstructed SchemaGraph.
        """
        return SchemaGraph.model_validate_json(path.read_text(encoding="utf-8"))

    def render_erd(self, graph: SchemaGraph) -> str:
        """Return a trivial Markdown stub mentioning the area key.

        Args:
            graph: The graph to render.

        Returns:
            A minimal Markdown string containing the area key.
        """
        return f"# {graph.area_key}\n\nerDiagram"

    async def render_erd_image(self, graph: SchemaGraph, *, fmt: ImageFormat) -> bytes:
        """Return canned image bytes (ignores inputs).

        Args:
            graph: Ignored.
            fmt: Ignored.

        Returns:
            The canned image bytes.

        Raises:
            Exception: The configured ``image_error`` when set.
        """
        del graph, fmt
        if self._image_error is not None:
            raise self._image_error
        return self._image
