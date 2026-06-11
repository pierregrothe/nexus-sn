# tests/cli/test_commands_schema.py
# Tests for the `nexus schema` CLI commands.
# Author: Pierre Grothe
# Date: 2026-06-08
"""products lists the catalog; erd writes a Markdown file via an injected fake."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nexus.api.errors import KrokiError
from nexus.cli import commands_schema
from nexus.cli import commands_schema as _cs_module
from nexus.cli.apps import app
from nexus.cli.help_text import SCHEMA_HELP, SCHEMA_PARENT, TOP_LEVEL_HELP
from nexus.schema.archive import SchemaArchiveReader
from nexus.schema.erd import MermaidErdEmitter
from nexus.schema.errors import SchemaArchiveError, SchemaError, ScopeNotFoundError
from nexus.schema.models import SchemaGraph, ScopeEntry, TableDef
from nexus.schema.products import SchemaProduct, SchemaProductCatalog
from tests.fakes.fake_kroki_client import FakeKrokiClient
from tests.fakes.fake_product_registry import FakeProductRegistry
from tests.schema.fakes.fake_schema_cartographer import FakeSchemaCartographer


def _patch_builder(monkeypatch: pytest.MonkeyPatch, fake: FakeSchemaCartographer) -> None:
    """Replace _build_schema_cartographer with a factory returning the fake twice."""

    def _build(*_: object, **__: object) -> tuple[FakeSchemaCartographer, FakeSchemaCartographer]:
        return fake, fake

    monkeypatch.setattr(commands_schema, "_build_schema_cartographer", _build)


def _fake_registry() -> FakeProductRegistry:
    return FakeProductRegistry(
        SchemaProductCatalog(
            version="1.0",
            products=(
                SchemaProduct(
                    key="doc-designer",
                    acronym="DOC",
                    name="Document Designer",
                    scopes=(
                        ScopeEntry(key="sn_grc_doc_design", label="Document Designer with Word"),
                        ScopeEntry(key="sn_grc_rel_config", label="Data Relationships Framework"),
                    ),
                    bridge_targets=(),
                ),
                SchemaProduct(
                    key="bcm",
                    acronym="BCM",
                    name="Business Continuity Management",
                    scopes=(ScopeEntry(key="sn_bcm", label="BCM Core"),),
                    bridge_targets=(),
                ),
            ),
        )
    )


def _patch_registry(monkeypatch: pytest.MonkeyPatch, registry: FakeProductRegistry) -> None:
    monkeypatch.setattr(_cs_module, "ProductRegistry", lambda _path: registry)


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


def test_schema_products_lists_products(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_registry(monkeypatch, _fake_registry())
    result = CliRunner().invoke(app, ["schema", "products"])
    assert result.exit_code == 0
    assert "doc-designer" in result.stdout


def test_schema_erd_writes_markdown_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_registry(monkeypatch, _fake_registry())
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
    _patch_registry(monkeypatch, _fake_registry())
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
    _patch_registry(monkeypatch, _fake_registry())
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


def test_schema_erd_unknown_product_exits_two_without_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _forbid(*_: object) -> tuple[object, object]:
        raise AssertionError("auth path must not run")

    monkeypatch.setattr(commands_schema, "_build_schema_cartographer", _forbid)
    _patch_registry(monkeypatch, _fake_registry())
    result = CliRunner().invoke(app, ["schema", "erd", "no-such-product"])
    assert result.exit_code == 2, result.stdout
    assert "no-such-product" in result.stdout
    assert "nexus schema products" in result.stdout


def test_schema_erd_discover_error_prints_notice_and_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_registry(monkeypatch, _fake_registry())
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
    _patch_registry(monkeypatch, _fake_registry())
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


def _snapshot(tmp_path: Path) -> Path:
    """Write the canned graph as a real JSON snapshot under tmp_path."""
    path = tmp_path / "snap.json"
    path.write_text(_graph().model_dump_json(indent=2), encoding="utf-8")
    return path


def test_schema_erd_save_archive_writes_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_registry(monkeypatch, _fake_registry())
    fake = FakeSchemaCartographer(_graph())
    _patch_builder(monkeypatch, fake)
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "erd.md"
    result = CliRunner().invoke(
        app,
        [
            "schema",
            "erd",
            "doc-designer",
            "--profile",
            "alectri",
            "-o",
            str(out),
            "--save-archive",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "Wrote archive to" in result.stdout
    snapshot = tmp_path / "doc-designer.json"
    assert snapshot.is_file()
    assert SchemaGraph.model_validate_json(snapshot.read_text(encoding="utf-8")) == _graph()


def test_schema_erd_from_archive_renders_without_auth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _forbid(*_: object) -> tuple[object, object]:
        raise AssertionError("auth path must not run")

    monkeypatch.setattr(commands_schema, "_build_schema_cartographer", _forbid)
    _patch_registry(monkeypatch, _fake_registry())
    out = tmp_path / "erd.md"
    result = CliRunner().invoke(
        app,
        [
            "schema",
            "erd",
            "doc-designer",
            "--from-archive",
            str(_snapshot(tmp_path)),
            "-o",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert out.is_file()
    assert "erDiagram" in out.read_text(encoding="utf-8")


def test_schema_erd_from_archive_area_mismatch_warns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_registry(monkeypatch, _fake_registry())
    out = tmp_path / "erd.md"
    result = CliRunner().invoke(
        app,
        ["schema", "erd", "bcm", "--from-archive", str(_snapshot(tmp_path)), "-o", str(out)],
    )
    assert result.exit_code == 0, result.stdout
    assert "archive contains area doc-designer" in result.stdout
    assert "# Schema ERD: doc-designer" in out.read_text(encoding="utf-8")


def test_schema_erd_from_archive_missing_file_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert issubclass(SchemaArchiveError, SchemaError)
    _patch_registry(monkeypatch, _fake_registry())
    result = CliRunner().invoke(
        app,
        ["schema", "erd", "doc-designer", "--from-archive", str(tmp_path / "nope.json")],
    )
    assert result.exit_code == 1, result.stdout
    assert "missing or invalid" in result.stdout


def test_schema_erd_from_archive_with_save_archive_exits_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_registry(monkeypatch, _fake_registry())
    result = CliRunner().invoke(
        app,
        [
            "schema",
            "erd",
            "doc-designer",
            "--from-archive",
            str(_snapshot(tmp_path)),
            "--save-archive",
        ],
    )
    assert result.exit_code == 2, result.stdout
    assert "cannot be combined" in result.stdout


def test_schema_erd_from_archive_with_image_writes_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_kroki = FakeKrokiClient(canned=b"<svg/>")

    def _offline(*_: object) -> tuple[SchemaArchiveReader, MermaidErdEmitter, FakeKrokiClient]:
        return SchemaArchiveReader(), MermaidErdEmitter(), fake_kroki

    monkeypatch.setattr(commands_schema, "_build_offline_schema_renderer", _offline)
    _patch_registry(monkeypatch, _fake_registry())
    out = tmp_path / "erd.md"
    result = CliRunner().invoke(
        app,
        [
            "schema",
            "erd",
            "doc-designer",
            "--from-archive",
            str(_snapshot(tmp_path)),
            "-o",
            str(out),
            "--image",
            "svg",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert (tmp_path / "erd.svg").read_bytes() == b"<svg/>"
    assert fake_kroki.calls
    assert fake_kroki.calls[0]["fmt"] == "svg"


def _grouped_graph() -> SchemaGraph:
    """Canned graph spanning both doc-designer scopes (for --grouped tests)."""
    return SchemaGraph(
        instance_id="alectri",
        area_key="doc-designer",
        discovered_at=datetime(2026, 6, 8, tzinfo=UTC),
        scope_keys=("sn_grc_doc_design", "sn_grc_rel_config"),
        tables=(
            TableDef(name="content_config", label="Content", scope="sn_grc_doc_design"),
            TableDef(name="rel_filter", label="Filter", scope="sn_grc_rel_config"),
        ),
        reference_edges=(),
        inheritance_edges=(),
        relationship_edges=(),
    )


def test_schema_erd_grouped_writes_multi_diagram_markdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_registry(monkeypatch, _fake_registry())
    fake = FakeSchemaCartographer(_grouped_graph())
    _patch_builder(monkeypatch, fake)
    out = tmp_path / "erd.md"
    result = CliRunner().invoke(
        app,
        ["schema", "erd", "doc-designer", "--profile", "alectri", "-o", str(out), "--grouped"],
    )
    assert result.exit_code == 0, result.stdout
    text = out.read_text(encoding="utf-8")
    assert "## Document Designer with Word" in text
    assert "## Data Relationships Framework" in text


def test_schema_erd_grouped_image_writes_file_per_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_registry(monkeypatch, _fake_registry())
    fake = FakeSchemaCartographer(_grouped_graph(), image=b"<svg/>")
    _patch_builder(monkeypatch, fake)
    out = tmp_path / "erd.md"
    result = CliRunner().invoke(
        app,
        [
            "schema",
            "erd",
            "doc-designer",
            "--profile",
            "alectri",
            "-o",
            str(out),
            "--grouped",
            "--image",
            "svg",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert (tmp_path / "erd-sn_grc_doc_design.svg").read_bytes() == b"<svg/>"
    assert (tmp_path / "erd-sn_grc_rel_config.svg").read_bytes() == b"<svg/>"


def test_schema_erd_from_archive_grouped_renders_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _forbid(*_: object) -> tuple[object, object]:
        raise AssertionError("auth path must not run")

    monkeypatch.setattr(commands_schema, "_build_schema_cartographer", _forbid)
    _patch_registry(monkeypatch, _fake_registry())
    snapshot = tmp_path / "snap.json"
    snapshot.write_text(_grouped_graph().model_dump_json(indent=2), encoding="utf-8")
    out = tmp_path / "erd.md"
    result = CliRunner().invoke(
        app,
        [
            "schema",
            "erd",
            "doc-designer",
            "--from-archive",
            str(snapshot),
            "-o",
            str(out),
            "--grouped",
        ],
    )
    assert result.exit_code == 0, result.stdout
    text = out.read_text(encoding="utf-8")
    assert "## Document Designer with Word" in text
    assert "## Data Relationships Framework" in text
    assert "## Cross-scope bridges" in text


def test_schema_erd_from_archive_grouped_unknown_area_falls_back_to_scope_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_registry(monkeypatch, _fake_registry())
    graph = _grouped_graph().model_copy(update={"area_key": "mystery"})
    snapshot = tmp_path / "snap.json"
    snapshot.write_text(graph.model_dump_json(indent=2), encoding="utf-8")
    out = tmp_path / "erd.md"
    result = CliRunner().invoke(
        app,
        ["schema", "erd", "mystery", "--from-archive", str(snapshot), "-o", str(out), "--grouped"],
    )
    assert result.exit_code == 0, result.stdout
    text = out.read_text(encoding="utf-8")
    assert "## sn_grc_doc_design" in text
    assert "## sn_grc_rel_config" in text


def test_schema_erd_from_archive_grouped_image_writes_file_per_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_kroki = FakeKrokiClient(canned=b"<svg/>")

    def _offline(*_: object) -> tuple[SchemaArchiveReader, MermaidErdEmitter, FakeKrokiClient]:
        return SchemaArchiveReader(), MermaidErdEmitter(), fake_kroki

    monkeypatch.setattr(commands_schema, "_build_offline_schema_renderer", _offline)
    _patch_registry(monkeypatch, _fake_registry())
    snapshot = tmp_path / "snap.json"
    snapshot.write_text(_grouped_graph().model_dump_json(indent=2), encoding="utf-8")
    out = tmp_path / "erd.md"
    result = CliRunner().invoke(
        app,
        [
            "schema",
            "erd",
            "doc-designer",
            "--from-archive",
            str(snapshot),
            "-o",
            str(out),
            "--grouped",
            "--image",
            "svg",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert (tmp_path / "erd-sn_grc_doc_design.svg").read_bytes() == b"<svg/>"
    assert (tmp_path / "erd-sn_grc_rel_config.svg").read_bytes() == b"<svg/>"
    assert len(fake_kroki.calls) == 2


def test_schema_callback_renders_themed_help() -> None:
    result = CliRunner().invoke(app, ["schema"])
    assert result.exit_code == 0, result.stdout
    assert "nexus schema" in result.stdout
    assert "available commands" in result.stdout


def test_help_text_registers_schema_entries() -> None:
    assert any(entry.command == "schema" for entry in TOP_LEVEL_HELP)
    assert SCHEMA_PARENT.command == "schema"
    commands = [entry.command for entry in SCHEMA_HELP]
    assert "products" in commands
    assert "erd <product> [product2]" in commands


def test_schema_erd_two_products_union_scopes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = SchemaProductCatalog(
        version="1.0",
        products=(
            SchemaProduct(
                key="ham",
                acronym="HAM",
                name="Hardware Asset Management",
                scopes=(ScopeEntry(key="sn_hamp", label="HAM Pro"),),
                bridge_targets=("cmdb_ci",),
            ),
            SchemaProduct(
                key="itsm",
                acronym="ITSM",
                name="IT Service Management",
                scopes=(),
                bridge_targets=("incident", "cmdb_ci"),
            ),
        ),
    )
    graph = _graph().model_copy(update={"area_key": "ham-itsm"})
    fake = FakeSchemaCartographer(graph)
    _patch_builder(monkeypatch, fake)
    _patch_registry(monkeypatch, FakeProductRegistry(catalog))
    out = tmp_path / "erd.md"
    result = CliRunner().invoke(
        app, ["schema", "erd", "ham", "itsm", "--profile", "alectri", "-o", str(out)]
    )
    assert result.exit_code == 0, result.stdout
    assert out.is_file()


def test_schema_erd_two_bridge_only_products_exits_two(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = SchemaProductCatalog(
        version="1.0",
        products=(
            SchemaProduct(
                key="a", acronym="A", name="Product A", scopes=(), bridge_targets=("t1",)
            ),
            SchemaProduct(
                key="b", acronym="B", name="Product B", scopes=(), bridge_targets=("t2",)
            ),
        ),
    )
    _patch_registry(monkeypatch, FakeProductRegistry(catalog))
    result = CliRunner().invoke(app, ["schema", "erd", "a", "b"])
    assert result.exit_code == 2, result.stdout
    assert "bridge-only" in result.stdout


def test_schema_products_command_shows_bundled_footer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_registry(monkeypatch, _fake_registry())
    result = CliRunner().invoke(app, ["schema", "products"])
    assert result.exit_code == 0
    assert "(bundled)" in result.stdout
