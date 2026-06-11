# tests/schema/test_schema_exports.py
# Tests that the schema package re-exports its public API.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Verify top-level imports resolve and implementations satisfy SchemaProtocol."""

from datetime import UTC, datetime
from pathlib import Path

from nexus.schema import (
    SchemaArea,
    SchemaCartographer,
    SchemaGraph,
    SchemaProtocol,
    ScopeEntry,
)
from tests.fakes.fake_kroki_client import FakeKrokiClient
from tests.fakes.fake_sn_client import FakeServiceNowClient
from tests.schema.fakes.fake_schema_cartographer import FakeSchemaCartographer


def _conforms(c: SchemaProtocol) -> None:
    del c


def _graph() -> SchemaGraph:
    return SchemaGraph(
        instance_id="alectri",
        area_key="doc-designer",
        discovered_at=datetime(2026, 6, 8, tzinfo=UTC),
        scope_keys=("sn_grc_doc_design",),
        tables=(),
        reference_edges=(),
        inheritance_edges=(),
        relationship_edges=(),
    )


def _area() -> SchemaArea:
    return SchemaArea(
        key="doc-designer",
        display="Document Designer",
        scopes=(ScopeEntry(key="sn_grc_doc_design", label="Document Designer with Word"),),
    )


def test_public_symbols_importable() -> None:
    assert SchemaArea is not None
    assert ScopeEntry is not None
    assert SchemaCartographer is not None
    assert SchemaGraph is not None
    assert SchemaProtocol is not None


def test_schema_protocol_engine_and_fake_conform(tmp_path: Path) -> None:
    _conforms(
        SchemaCartographer(
            FakeServiceNowClient(),
            areas={_area().key: _area()},
            archive_root=tmp_path,
            kroki=FakeKrokiClient(),
        )
    )
    _conforms(FakeSchemaCartographer(_graph()))
