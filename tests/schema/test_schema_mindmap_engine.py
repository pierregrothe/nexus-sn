# tests/schema/test_schema_mindmap_engine.py
# Tests for SchemaCartographer mindmap methods.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Engine discovers then enriches into a catalog and renders it."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from nexus.schema.areas import SchemaArea, ScopeRef
from nexus.schema.engine import SchemaCartographer
from tests.fakes.fake_agent_client import FakeAgentClient
from tests.fakes.fake_kroki_client import FakeKrokiClient
from tests.fakes.fake_sn_client import FakeServiceNowClient

_AREAS = {"dd": SchemaArea(key="dd", display="DD", scopes=(ScopeRef("sn_grc_doc_design", "DD"),))}
_AI_JSON = '{"domains":[{"name":"Core","tables":[{"table":"t1","description":"Stores t1."}]}]}'


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
        "sys_documentation": [],
    }


def _engine(tmp_path: Path, kroki: FakeKrokiClient | None = None) -> SchemaCartographer:
    return SchemaCartographer(
        FakeServiceNowClient(_seed()),
        areas=_AREAS,
        archive_root=tmp_path,
        agent_client=FakeAgentClient(canned_response=_AI_JSON),
        kroki=kroki or FakeKrokiClient(),
        clock=lambda: datetime(2026, 6, 8, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_build_mindmap_discovers_then_enriches(tmp_path: Path) -> None:
    catalog = await _engine(tmp_path).build_mindmap("alectri", "dd")
    assert catalog.display == "DD"
    assert catalog.domains[0].tables[0].description == "Stores t1."


@pytest.mark.asyncio
async def test_render_mindmap_returns_markdown(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    catalog = await engine.build_mindmap("alectri", "dd")
    assert "mindmap" in engine.render_mindmap(catalog)


@pytest.mark.asyncio
async def test_render_erd_image_calls_kroki_with_diagram_source(tmp_path: Path) -> None:
    kroki = FakeKrokiClient(canned=b"<svg/>")
    engine = _engine(tmp_path, kroki=kroki)
    graph = await engine.discover("alectri", "dd")
    out = await engine.render_erd_image(graph, fmt="svg")
    assert out == b"<svg/>"
    assert kroki.calls[0]["fmt"] == "svg"
    assert str(kroki.calls[0]["source"]).startswith("erDiagram")


@pytest.mark.asyncio
async def test_render_mindmap_image_calls_kroki_with_diagram_source(tmp_path: Path) -> None:
    kroki = FakeKrokiClient(canned=b"PNGDATA")
    engine = _engine(tmp_path, kroki=kroki)
    catalog = await engine.build_mindmap("alectri", "dd")
    out = await engine.render_mindmap_image(catalog, fmt="png")
    assert out == b"PNGDATA"
    assert kroki.calls[0]["fmt"] == "png"
    assert str(kroki.calls[0]["source"]).startswith("mindmap")
