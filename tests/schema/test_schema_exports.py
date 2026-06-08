# tests/schema/test_schema_exports.py
# Tests that the schema package re-exports its public API.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Verify top-level imports resolve."""

from nexus.schema import (
    DEFAULT_AREAS,
    SchemaCartographer,
    SchemaGraph,
    SchemaProtocol,
)


def test_public_symbols_importable() -> None:
    assert "doc-designer" in DEFAULT_AREAS
    assert SchemaCartographer is not None
    assert SchemaGraph is not None
    assert SchemaProtocol is not None
