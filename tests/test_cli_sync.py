# tests/test_cli_sync.py
# Tests for nexus.cli.commands_sync._sync_main.
# Author: Pierre Grothe
# Date: 2026-05-18
"""Tests for the `nexus sync` command body."""

from __future__ import annotations

import io
from pathlib import Path
from typing import override

import pytest
from rich.console import Console

from nexus.cache import clear_cache
from nexus.cli.commands_sync import _sync_main
from nexus.config.manager import ConfigManager
from nexus.config.paths import NexusPaths
from nexus.config.settings import NexusConfig, PreferencesConfig
from nexus.templates.models import TemplateEntry, TemplateManifest
from nexus.templates.sync import GitHubTemplateClient


class _StubClient(GitHubTemplateClient):
    """Test double that returns a canned manifest."""

    def __init__(self, manifest: TemplateManifest | None) -> None:
        super().__init__(httpx_client=None)
        self._canned = manifest

    @override
    def fetch_manifest(self, repo: str, branch: str, path: str) -> TemplateManifest | None:
        del repo, branch, path
        return self._canned


def _paths(tmp_path: Path) -> NexusPaths:
    return NexusPaths(root=tmp_path)


def _config_manager(
    tmp_path: Path, *, github_repo: str, github_branch: str = "main"
) -> ConfigManager:
    paths = _paths(tmp_path)
    manager = ConfigManager(paths=paths)
    config = NexusConfig(
        preferences=PreferencesConfig(github_repo=github_repo, github_branch=github_branch)
    )
    manager.save(config)
    # Clear the cache so the next load() reads fresh from disk.
    clear_cache(manager.load)
    return manager


def _captured_console() -> tuple[Console, io.StringIO]:
    buf = io.StringIO()
    return Console(file=buf, force_terminal=False, width=120), buf


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


def test_sync_returns_1_when_github_repo_empty(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    manager = _config_manager(tmp_path, github_repo="")
    out, _ = _captured_console()
    err, err_buf = _captured_console()
    code = _sync_main(
        paths=paths,
        config_manager=manager,
        client=_StubClient(_wire()),
        console_out=out,
        console_err=err,
    )
    assert code == 1
    assert "not configured" in err_buf.getvalue().lower()


def test_sync_returns_1_when_github_repo_is_url(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    manager = _config_manager(tmp_path, github_repo="https://github.com/x/y")
    out, _ = _captured_console()
    err, err_buf = _captured_console()
    code = _sync_main(
        paths=paths,
        config_manager=manager,
        client=_StubClient(_wire()),
        console_out=out,
        console_err=err,
    )
    assert code == 1
    assert "url not allowed" in err_buf.getvalue()


def test_sync_returns_0_on_happy_path_and_writes_cache(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    manager = _config_manager(tmp_path, github_repo="owner/name")
    out, out_buf = _captured_console()
    err, _ = _captured_console()
    code = _sync_main(
        paths=paths,
        config_manager=manager,
        client=_StubClient(_wire(entries=3)),
        console_out=out,
        console_err=err,
    )
    assert code == 0
    assert (paths.templates_dir / "manifest.json").exists()
    assert "Synced 3 templates" in out_buf.getvalue()


def test_sync_returns_0_on_empty_catalog(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    manager = _config_manager(tmp_path, github_repo="owner/name")
    out, out_buf = _captured_console()
    err, _ = _captured_console()
    code = _sync_main(
        paths=paths,
        config_manager=manager,
        client=_StubClient(_wire(entries=0)),
        console_out=out,
        console_err=err,
    )
    assert code == 0
    assert "Synced 0 templates" in out_buf.getvalue()


def test_sync_returns_1_when_fetch_fails(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    manager = _config_manager(tmp_path, github_repo="owner/name")
    out, _ = _captured_console()
    err, err_buf = _captured_console()
    code = _sync_main(
        paths=paths,
        config_manager=manager,
        client=_StubClient(None),
        console_out=out,
        console_err=err,
    )
    assert code == 1
    assert "Fetch failed" in err_buf.getvalue()
    assert not (paths.templates_dir / "manifest.json").exists()


def test_sync_returns_1_when_registry_oserror_during_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)
    manager = _config_manager(tmp_path, github_repo="owner/name")

    def _exploding_replace(self: Path, target: Path) -> Path:
        if target.name == "manifest.json":
            raise OSError("disk full")
        return target

    monkeypatch.setattr(Path, "replace", _exploding_replace)
    out, _ = _captured_console()
    err, err_buf = _captured_console()
    code = _sync_main(
        paths=paths,
        config_manager=manager,
        client=_StubClient(_wire(entries=1)),
        console_out=out,
        console_err=err,
    )
    assert code == 1
    assert "Cache write failed" in err_buf.getvalue()


def test_sync_prints_count_and_repo_in_summary(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    manager = _config_manager(tmp_path, github_repo="owner/name", github_branch="develop")
    out, out_buf = _captured_console()
    err, _ = _captured_console()
    _sync_main(
        paths=paths,
        config_manager=manager,
        client=_StubClient(_wire(entries=2)),
        console_out=out,
        console_err=err,
    )
    output = out_buf.getvalue()
    assert "Synced 2 templates" in output
    assert "owner/name" in output
    assert "develop" in output
