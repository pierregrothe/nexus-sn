# tests/cli/test_commands_schema.py
# Tests for the `nexus schema` CLI commands.
# Author: Pierre Grothe
# Date: 2026-06-08
"""areas lists the registry; erd writes a Markdown file via an injected fake."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nexus.api.errors import KrokiError
from nexus.cli import commands_schema
from nexus.cli.apps import app
from nexus.cli.help_text import SCHEMA_HELP, SCHEMA_PARENT, TOP_LEVEL_HELP
from nexus.schema.errors import ScopeNotFoundError
from nexus.schema.models import SchemaGraph, TableDef
from tests.schema.fakes.fake_schema_cartographer import FakeSchemaCartographer


def _patch_builder(monkeypatch: pytest.MonkeyPatch, fake: FakeSchemaCartographer) -> None:
    """Replace _build_schema_cartographer with a factory returning the fake twice."""

    def _build(*_: object) -> tuple[FakeSchemaCartographer, FakeSchemaCartographer]:
        return fake, fake

    monkeypatch.setattr(commands_schema, "_build_schema_cartographer", _build)


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
    _patch_builder(monkeypatch, fake)
    out = tmp_path / "erd.md"
    result = CliRunner().invoke(
        app, ["schema", "erd", "doc-designer", "--profile", "alectri", "-o", str(out)]
    )
    assert result.exit_code == 0, result.stdout
    assert out.is_file()
    assert "erDiagram" in out.read_text(encoding="utf-8")


def test_schema_erd_writes_image_when_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeSchemaCartographer(_graph(), image=b"<svg/>")
    _patch_builder(monkeypatch, fake)
    out = tmp_path / "erd.md"
    result = CliRunner().invoke(
        app,
        ["schema", "erd", "doc-designer", "--profile", "alectri", "-o", str(out), "--image", "svg"],
    )
    assert result.exit_code == 0, result.stdout
    assert (tmp_path / "erd.svg").read_bytes() == b"<svg/>"


def test_schema_erd_zero_tables_prints_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = _graph().model_copy(update={"tables": ()})
    fake = FakeSchemaCartographer(empty)
    _patch_builder(monkeypatch, fake)
    out = tmp_path / "erd.md"
    result = CliRunner().invoke(
        app, ["schema", "erd", "doc-designer", "--profile", "alectri", "-o", str(out)]
    )
    assert result.exit_code == 0, result.stdout
    assert "No tables discovered" in result.stdout
    assert out.is_file()


def test_schema_erd_unknown_area_exits_two_without_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    def _forbid(*_: object) -> tuple[object, object]:
        raise AssertionError("auth path must not run")

    monkeypatch.setattr(commands_schema, "_build_schema_cartographer", _forbid)
    result = CliRunner().invoke(app, ["schema", "erd", "no-such-area"])
    assert result.exit_code == 2, result.stdout
    assert "doc-designer" in result.stdout
    assert "bcm" in result.stdout
    assert "nexus schema areas" in result.stdout


def test_schema_erd_discover_error_prints_notice_and_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    error = ScopeNotFoundError(["sn_grc_doc_design"], "alectri")
    fake = FakeSchemaCartographer(_graph(), discover_error=error)
    _patch_builder(monkeypatch, fake)
    out = tmp_path / "erd.md"
    result = CliRunner().invoke(
        app, ["schema", "erd", "doc-designer", "--profile", "alectri", "-o", str(out)]
    )
    assert result.exit_code == 1, result.stdout
    assert "No scopes" in result.stdout
    assert not out.exists()


def test_schema_erd_kroki_error_keeps_markdown_and_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeSchemaCartographer(_graph(), image_error=KrokiError(None, "boom"))
    _patch_builder(monkeypatch, fake)
    out = tmp_path / "erd.md"
    result = CliRunner().invoke(
        app,
        ["schema", "erd", "doc-designer", "--profile", "alectri", "-o", str(out), "--image", "svg"],
    )
    assert result.exit_code == 1, result.stdout
    assert out.is_file()
    assert "Wrote ERD" in result.stdout
    assert "boom" in result.stdout
    assert "--kroki-url" in result.stdout
    assert not (tmp_path / "erd.svg").exists()


def test_schema_callback_renders_themed_help() -> None:
    result = CliRunner().invoke(app, ["schema"])
    assert result.exit_code == 0, result.stdout
    assert "nexus schema" in result.stdout
    assert "available commands" in result.stdout


def test_help_text_registers_schema_entries() -> None:
    assert any(entry.command == "schema" for entry in TOP_LEVEL_HELP)
    assert SCHEMA_PARENT.command == "schema"
    commands = [entry.command for entry in SCHEMA_HELP]
    assert "areas" in commands
    assert "erd <area>" in commands
