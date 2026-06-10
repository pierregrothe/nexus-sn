# tests/schema/test_fake_schema_cartographer.py
# Tests for the FakeSchemaCartographer test double.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Verify the fake returns its canned graph and round-trips."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from nexus.api.kroki_client import ImageFormat
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
    assert await fake.render_erd_image(_graph(), fmt=ImageFormat.png) == b"PNG"


def test_fake_render_erd_grouped_contains_label_headings() -> None:
    fake = FakeSchemaCartographer(_graph())
    out = fake.render_erd_grouped(_graph(), {"sn_grc_doc_design": "Doc Design"})
    assert "## Doc Design" in out
    assert "doc-designer" in out


def test_fake_render_erd_grouped_falls_back_to_scope_key() -> None:
    fake = FakeSchemaCartographer(_graph())
    assert "## sn_grc_doc_design" in fake.render_erd_grouped(_graph(), {})


@pytest.mark.asyncio
async def test_fake_render_erd_group_images_returns_pair_per_scope() -> None:
    fake = FakeSchemaCartographer(_graph(), image=b"PNG")
    images = await fake.render_erd_group_images(_graph(), {}, fmt=ImageFormat.png)
    assert images == (("sn_grc_doc_design", b"PNG"),)


@pytest.mark.asyncio
async def test_fake_render_erd_group_images_raises_configured_error() -> None:
    fake = FakeSchemaCartographer(_graph(), image_error=RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        await fake.render_erd_group_images(_graph(), {}, fmt=ImageFormat.png)
