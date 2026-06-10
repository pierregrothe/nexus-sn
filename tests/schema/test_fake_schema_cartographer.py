# tests/schema/test_fake_schema_cartographer.py
# Tests for the FakeSchemaCartographer test double.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Verify the fake returns its canned graph and round-trips."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from nexus.schema.models import SchemaGraph, TableDef
from tests.schema.fakes.fake_schema_cartographer import FakeSchemaCartographer


def _graph() -> SchemaGraph:
    return SchemaGraph(
        instance_id="alectri",
        area_key="doc-designer",
        discovered_at=datetime(2026, 6, 8, tzinfo=UTC),
        scope_keys=("sn_grc_doc_design",),
        tables=(TableDef(name="t", label="T", scope="sn_grc_doc_design"),),
        reference_edges=(),
        inheritance_edges=(),
        relationship_edges=(),
    )


@pytest.mark.asyncio
async def test_fake_discover_returns_canned_graph() -> None:
    fake = FakeSchemaCartographer(_graph())
    assert await fake.discover("alectri", "doc-designer") == _graph()


def test_fake_render_erd_returns_string() -> None:
    fake = FakeSchemaCartographer(_graph())
    assert "doc-designer" in fake.render_erd(_graph())


def test_fake_save_and_load_roundtrips(tmp_path: Path) -> None:
    fake = FakeSchemaCartographer(_graph())
    path = fake.save_archive(_graph(), dest=tmp_path)
    assert fake.load_archive(path) == _graph()


@pytest.mark.asyncio
async def test_fake_render_erd_image_returns_canned_bytes() -> None:
    fake = FakeSchemaCartographer(_graph(), image=b"PNG")
    assert await fake.render_erd_image(_graph(), fmt="png") == b"PNG"
