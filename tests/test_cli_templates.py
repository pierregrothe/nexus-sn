# tests/test_cli_templates.py
# Tests for nexus.cli.commands_sync._templates_main.
# Author: Pierre Grothe
# Date: 2026-05-18
"""Tests for the `nexus templates` command body."""

from __future__ import annotations

import io
from pathlib import Path

from rich.console import Console

from nexus.cli.commands_sync import _templates_main
from nexus.config.paths import NexusPaths
from nexus.templates.models import SyncSource, TemplateEntry, TemplateManifest
from nexus.templates.registry import TemplateRegistry


def _paths(tmp_path: Path) -> NexusPaths:
    return NexusPaths(root=tmp_path)


def _captured_console() -> tuple[Console, io.StringIO]:
    buf = io.StringIO()
    return Console(file=buf, force_terminal=False, width=120), buf


def _seed_cache(paths: NexusPaths, *, entries: int) -> None:
    wire = TemplateManifest(
        version="1.0",
        generated="2026-05-07",
        templates=tuple(
            TemplateEntry(
                name=f"t-{i}",
                template_type="workflow",
                version=f"0.{i}.0",
                path=f"workflows/t{i}.yaml",
            )
            for i in range(entries)
        ),
    )
    source = SyncSource(repo="owner/name", branch="main", path="templates/manifest.json")
    TemplateRegistry(paths.templates_dir).save_manifest(wire, source)


def test_templates_prints_hint_when_cache_missing(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    out, buf = _captured_console()
    code = _templates_main(paths=paths, console_out=out)
    assert code == 0
    text = buf.getvalue()
    assert "No catalog cached" in text
    assert "nexus sync" in text


def test_templates_prints_empty_notice_when_catalog_has_no_entries(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    _seed_cache(paths, entries=0)
    out, buf = _captured_console()
    code = _templates_main(paths=paths, console_out=out)
    assert code == 0
    text = buf.getvalue()
    assert "Catalog is empty" in text
    assert "owner/name" in text


def test_templates_prints_datatable_with_entries(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _seed_cache(paths, entries=3)
    out, buf = _captured_console()
    code = _templates_main(paths=paths, console_out=out)
    assert code == 0
    text = buf.getvalue()
    assert "Templates" in text
    assert "t-0" in text
    assert "t-1" in text
    assert "t-2" in text
    assert "workflow" in text


def test_templates_footer_shows_synced_age_and_source(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _seed_cache(paths, entries=1)
    out, buf = _captured_console()
    _templates_main(paths=paths, console_out=out)
    text = buf.getvalue()
    assert "synced" in text
    assert "owner/name" in text
    assert "main" in text


def test_templates_sorts_entries_by_name(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    # Seed with deliberately out-of-order entries.
    wire = TemplateManifest(
        version="1.0",
        generated="2026-05-07",
        templates=(
            TemplateEntry(
                name="zebra",
                template_type="workflow",
                version="0.1.0",
                path="zebra.yaml",
            ),
            TemplateEntry(
                name="alpha",
                template_type="workflow",
                version="0.1.0",
                path="alpha.yaml",
            ),
        ),
    )
    source = SyncSource(repo="owner/name", branch="main", path="templates/manifest.json")
    TemplateRegistry(paths.templates_dir).save_manifest(wire, source)
    out, buf = _captured_console()
    _templates_main(paths=paths, console_out=out)
    text = buf.getvalue()
    assert text.index("alpha") < text.index("zebra")
