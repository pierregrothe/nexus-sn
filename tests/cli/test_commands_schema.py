# tests/cli/test_commands_schema.py
# Tests for the `nexus schema` CLI commands.
# Author: Pierre Grothe
# Date: 2026-06-08
"""areas lists the registry; erd writes a Markdown file via an injected fake."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nexus.cli import commands_schema
from nexus.cli.apps import app
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


def test_schema_areas_lists_registered_areas() -> None:
    result = CliRunner().invoke(app, ["schema", "areas"])
    assert result.exit_code == 0
    assert "doc-designer" in result.stdout


def test_schema_erd_writes_markdown_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeSchemaCartographer(_graph())
    monkeypatch.setattr(
        commands_schema, "_build_schema_cartographer", lambda _profile: (fake, fake)
    )
    out = tmp_path / "erd.md"
    result = CliRunner().invoke(
        app, ["schema", "erd", "doc-designer", "--profile", "alectri", "-o", str(out)]
    )
    assert result.exit_code == 0, result.stdout
    assert out.is_file()
    assert "erDiagram" in out.read_text(encoding="utf-8")
