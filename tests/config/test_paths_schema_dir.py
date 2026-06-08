# tests/config/test_paths_schema_dir.py
# Tests for NexusPaths.schema_dir.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Verify schema_dir resolves and is created by ensure_dirs."""

from pathlib import Path

from nexus.config.paths import NexusPaths


def test_schema_dir_is_under_root(tmp_path: Path) -> None:
    paths = NexusPaths(root=tmp_path)
    assert paths.schema_dir == tmp_path / "schema"


def test_ensure_dirs_creates_schema_dir(tmp_path: Path) -> None:
    paths = NexusPaths(root=tmp_path)
    paths.ensure_dirs()
    assert paths.schema_dir.is_dir()
