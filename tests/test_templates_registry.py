# tests/test_templates_registry.py
# Tests for TemplateRegistry save / load with atomic semantics.
# Author: Pierre Grothe
# Date: 2026-05-18
"""Tests for nexus.templates.registry.TemplateRegistry."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from nexus.templates.models import (
    CachedManifest,
    SyncSource,
    TemplateEntry,
    TemplateManifest,
)
from nexus.templates.registry import TemplateRegistry


def _wire(entries: int = 0) -> TemplateManifest:
    return TemplateManifest(
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


def _source() -> SyncSource:
    return SyncSource(repo="owner/name", branch="main", path="templates/manifest.json")


def test_load_manifest_returns_none_when_cache_missing(tmp_path: Path) -> None:
    registry = TemplateRegistry(tmp_path / "nonexistent")
    assert registry.load_manifest() is None


def test_save_manifest_writes_file_and_returns_cached_wrapper(tmp_path: Path) -> None:
    registry = TemplateRegistry(tmp_path)
    cached = registry.save_manifest(_wire(), _source())
    assert (tmp_path / "manifest.json").exists()
    assert isinstance(cached, CachedManifest)
    assert cached.wire == _wire()
    assert cached.source == _source()


def test_save_manifest_stamps_cached_at_in_utc(tmp_path: Path) -> None:
    registry = TemplateRegistry(tmp_path)
    before = datetime.now(UTC)
    cached = registry.save_manifest(_wire(), _source())
    after = datetime.now(UTC)
    assert before - timedelta(seconds=1) <= cached.cached_at <= after + timedelta(seconds=1)
    assert cached.cached_at.tzinfo is not None


def test_save_then_load_round_trips_manifest(tmp_path: Path) -> None:
    registry = TemplateRegistry(tmp_path)
    cached = registry.save_manifest(_wire(entries=2), _source())
    loaded = registry.load_manifest()
    assert loaded == cached


def test_load_manifest_returns_none_on_malformed_json(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "manifest.json").write_text("{ not json", encoding="utf-8")
    registry = TemplateRegistry(tmp_path)
    with caplog.at_level(logging.WARNING, logger="nexus.templates.registry"):
        assert registry.load_manifest() is None
    assert any("invalid JSON" in r.message for r in caplog.records)


def test_load_manifest_returns_none_on_schema_mismatch(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "manifest.json").write_text(
        json.dumps({"wire": {"version": "1.0"}}), encoding="utf-8"
    )
    registry = TemplateRegistry(tmp_path)
    with caplog.at_level(logging.WARNING, logger="nexus.templates.registry"):
        assert registry.load_manifest() is None
    assert any("schema mismatch" in r.message for r in caplog.records)


def test_save_manifest_creates_parent_directories(tmp_path: Path) -> None:
    deep = tmp_path / "a" / "b" / "templates"
    registry = TemplateRegistry(deep)
    registry.save_manifest(_wire(), _source())
    assert (deep / "manifest.json").exists()


def test_save_manifest_preserves_previous_cache_when_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = TemplateRegistry(tmp_path)
    first = registry.save_manifest(_wire(entries=1), _source())
    original_replace = Path.replace

    def _exploding_replace(self: Path, target: Path) -> Path:
        if target.name == "manifest.json":
            raise OSError("simulated disk full")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", _exploding_replace)
    with pytest.raises(OSError, match="simulated disk full"):
        registry.save_manifest(_wire(entries=2), _source())
    loaded = registry.load_manifest()
    assert loaded == first


def test_load_manifest_returns_none_when_directory_exists_but_file_missing(
    tmp_path: Path,
) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    registry = TemplateRegistry(tmp_path)
    assert registry.load_manifest() is None
