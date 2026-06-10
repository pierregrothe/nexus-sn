# tests/schema/test_schema_cartographer.py
# Tests for the SchemaCartographer engine.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Engine wires discover -> archive -> render through one object."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from nexus.schema.areas import SchemaArea, ScopeRef
from nexus.schema.engine import SchemaCartographer
from tests.fakes.fake_kroki_client import FakeKrokiClient
from tests.fakes.fake_sn_client import FakeServiceNowClient

_AREAS = {"dd": SchemaArea(key="dd", display="DD", scopes=(ScopeRef("sn_grc_doc_design", "DD"),))}


def _seed() -> dict[str, list[dict[str, object]]]:
    return {
        "sys_scope": [{"sys_id": "SCID", "scope": "sn_grc_doc_design"}],
        "sys_db_object": [
            {
                "sys_id": "T1",
                "name": "t1",
                "label": "T1",
                "super_class": "",
                "sys_scope": {"link": "x", "value": "SCID"},
            },
        ],
        "sys_dictionary": [],
        "sys_relationship": [],
    }


def _engine(tmp_path: Path) -> SchemaCartographer:
    return SchemaCartographer(
        FakeServiceNowClient(_seed()),
        areas=_AREAS,
        archive_root=tmp_path,
        kroki=FakeKrokiClient(),
        clock=lambda: datetime(2026, 6, 8, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_discover_then_save_then_load_roundtrips(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    graph = await engine.discover("alectri", "dd")
    path = engine.save_archive(graph)
    assert engine.load_archive(path) == graph


@pytest.mark.asyncio
async def test_render_erd_returns_markdown(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    graph = await engine.discover("alectri", "dd")
    assert "erDiagram" in engine.render_erd(graph)


@pytest.mark.asyncio
async def test_save_archive_default_dest_uses_archive_root(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    graph = await engine.discover("alectri", "dd")
    path = engine.save_archive(graph)
    assert tmp_path in path.parents


@pytest.mark.asyncio
async def test_render_erd_image_renders_via_kroki(tmp_path: Path) -> None:
    kroki = FakeKrokiClient(canned=b"IMG")
    engine = SchemaCartographer(
        FakeServiceNowClient(_seed()),
        areas=_AREAS,
        archive_root=tmp_path,
        kroki=kroki,
        clock=lambda: datetime(2026, 6, 8, tzinfo=UTC),
    )
    graph = await engine.discover("alectri", "dd")
    assert await engine.render_erd_image(graph, fmt="svg") == b"IMG"
    assert kroki.calls[0]["fmt"] == "svg"
