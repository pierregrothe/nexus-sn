# tests/test_templates_github_sync.py
# Tests for the GitHubSync orchestrator + SyncReport.
# Author: Pierre Grothe
# Date: 2026-05-18
"""Tests for nexus.templates.sync.GitHubSync."""

from __future__ import annotations

from pathlib import Path
from typing import override

import pytest

from nexus.templates.models import TemplateEntry, TemplateManifest
from nexus.templates.registry import TemplateRegistry
from nexus.templates.sync import GitHubSync, GitHubTemplateClient


class _StubClient(GitHubTemplateClient):
    """GitHubTemplateClient subclass that returns a canned response."""

    def __init__(self, manifest: TemplateManifest | None) -> None:
        super().__init__(httpx_client=None)
        self._canned = manifest
        self.calls: list[tuple[str, str, str]] = []

    @override
    def fetch_manifest(self, repo: str, branch: str, path: str) -> TemplateManifest | None:
        self.calls.append((repo, branch, path))
        return self._canned


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


def test_run_returns_no_config_when_repo_empty(tmp_path: Path) -> None:
    client = _StubClient(_wire())
    registry = TemplateRegistry(tmp_path)
    report = GitHubSync(client=client, registry=registry).run(
        repo="", branch="main", path="templates/manifest.json"
    )
    assert report.outcome == "no-config"
    assert report.manifest is None
    assert report.reason is not None
    assert client.calls == []  # no HTTP issued


def test_run_returns_invalid_repo_on_url_input(tmp_path: Path) -> None:
    client = _StubClient(_wire())
    registry = TemplateRegistry(tmp_path)
    report = GitHubSync(client=client, registry=registry).run(
        repo="https://github.com/x/y", branch="main", path="templates/manifest.json"
    )
    assert report.outcome == "invalid-repo"
    assert report.manifest is None
    assert report.reason is not None
    assert "url not allowed" in report.reason
    assert client.calls == []


def test_run_returns_fetch_failed_when_client_returns_none(tmp_path: Path) -> None:
    client = _StubClient(None)
    registry = TemplateRegistry(tmp_path)
    report = GitHubSync(client=client, registry=registry).run(
        repo="owner/name", branch="main", path="templates/manifest.json"
    )
    assert report.outcome == "fetch-failed"
    assert report.manifest is None
    # Cache untouched.
    assert registry.load_manifest() is None


def test_run_returns_ok_with_cached_manifest_on_happy_path(tmp_path: Path) -> None:
    client = _StubClient(_wire(entries=3))
    registry = TemplateRegistry(tmp_path)
    report = GitHubSync(client=client, registry=registry).run(
        repo="owner/name", branch="main", path="templates/manifest.json"
    )
    assert report.outcome == "ok"
    assert report.manifest is not None
    assert len(report.manifest.wire.templates) == 3
    assert report.manifest.source.repo == "owner/name"
    # Cache hits disk.
    loaded = registry.load_manifest()
    assert loaded == report.manifest


def test_run_accepts_empty_templates_array_as_ok(tmp_path: Path) -> None:
    client = _StubClient(_wire(entries=0))
    registry = TemplateRegistry(tmp_path)
    report = GitHubSync(client=client, registry=registry).run(
        repo="owner/name", branch="main", path="templates/manifest.json"
    )
    assert report.outcome == "ok"
    assert report.manifest is not None
    assert report.manifest.wire.templates == ()


def test_run_returns_fetch_failed_when_registry_raises_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _StubClient(_wire(entries=1))
    registry = TemplateRegistry(tmp_path)

    def _exploding_replace(self: Path, target: Path) -> Path:
        if target.name == "manifest.json":
            raise OSError("simulated disk full")
        return target

    monkeypatch.setattr(Path, "replace", _exploding_replace)
    report = GitHubSync(client=client, registry=registry).run(
        repo="owner/name", branch="main", path="templates/manifest.json"
    )
    assert report.outcome == "fetch-failed"
    assert report.reason is not None
    assert "OSError" in report.reason


def test_run_preserves_previous_cache_on_fetch_failure(tmp_path: Path) -> None:
    client_ok = _StubClient(_wire(entries=2))
    registry = TemplateRegistry(tmp_path)
    GitHubSync(client=client_ok, registry=registry).run(
        repo="owner/name", branch="main", path="templates/manifest.json"
    )
    snapshot = registry.load_manifest()

    client_fail = _StubClient(None)
    report = GitHubSync(client=client_fail, registry=registry).run(
        repo="owner/name", branch="main", path="templates/manifest.json"
    )
    assert report.outcome == "fetch-failed"
    assert registry.load_manifest() == snapshot
