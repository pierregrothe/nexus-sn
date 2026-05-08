# tests/test_updater_runner.py
# Tests for the auto-update runner orchestration.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for nexus.updater.runner.check_and_maybe_update."""

import fcntl
import os
import subprocess
import sys
from pathlib import Path
from typing import TypedDict

import httpx
import pytest

from nexus.config.paths import NexusPaths
from nexus.updater import runner as runner_module
from nexus.updater.client import GitHubReleasesClient, ReleaseInfo
from nexus.updater.errors import UpdaterError
from nexus.updater.runner import check_and_maybe_update
from tests.fakes.fake_github_releases import FakeGitHubReleasesClient


class _Calls(TypedDict):
    """Recorded side-effects from monkeypatched runner internals."""

    execv: tuple[str, list[str]] | None
    exit: int | None
    install: bool


def _patch_runner(
    monkeypatch: pytest.MonkeyPatch,
    *,
    editable: bool,
    current: str | None,
    info: ReleaseInfo | None,
    install_succeeds: bool = True,
) -> _Calls:
    """Wire up monkeypatches for runner internals; return a calls-record dict."""
    calls: _Calls = {"execv": None, "exit": None, "install": False}

    monkeypatch.setattr(runner_module, "is_editable_install", lambda: editable)
    monkeypatch.setattr(runner_module, "current_version", lambda: current)

    def fake_build_client() -> FakeGitHubReleasesClient:
        return FakeGitHubReleasesClient(info=info)

    monkeypatch.setattr(runner_module, "_build_client", fake_build_client)

    def fake_install(wheel_path: Path) -> None:
        calls["install"] = True
        if not install_succeeds:
            raise UpdaterError("simulated install failure")

    monkeypatch.setattr(runner_module, "pip_install_wheel", fake_install)

    def fake_download(
        url: str,
        *,
        dest_dir: Path,
        httpx_client: httpx.Client | None = None,
    ) -> Path:
        path = dest_dir / "fake.whl"
        path.write_bytes(b"")
        return path

    monkeypatch.setattr(runner_module, "download_wheel", fake_download)

    def fake_execv(path: str, argv: list[str]) -> None:
        calls["execv"] = (path, argv)

    monkeypatch.setattr(os, "execv", fake_execv)

    def fake_exit(code: int) -> None:
        calls["exit"] = code

    monkeypatch.setattr(sys, "exit", fake_exit)
    return calls


def test_runner_skips_when_editable_install(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_runner(monkeypatch, editable=True, current="2026.05.1", info=None)
    check_and_maybe_update()
    assert calls["install"] is False
    assert calls["execv"] is None


def test_runner_skips_when_env_var_disables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_AUTO_UPDATE", "0")
    calls = _patch_runner(monkeypatch, editable=False, current="2026.05.1", info=None)
    check_and_maybe_update()
    assert calls["install"] is False


def test_runner_skips_when_current_version_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    info = ReleaseInfo(tag_name="2026.06.0", wheel_url="https://example.com/x.whl")
    calls = _patch_runner(monkeypatch, editable=False, current=None, info=info)
    check_and_maybe_update()
    assert calls["install"] is False


def test_runner_skips_when_github_returns_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runner_module, "_lock_path", lambda: tmp_path / "update.lock")
    calls = _patch_runner(monkeypatch, editable=False, current="2026.05.1", info=None)
    check_and_maybe_update()
    assert calls["install"] is False


def test_runner_skips_when_already_current(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(runner_module, "_lock_path", lambda: tmp_path / "update.lock")
    info = ReleaseInfo(tag_name="2026.05.1", wheel_url="https://example.com/x.whl")
    calls = _patch_runner(monkeypatch, editable=False, current="2026.05.1", info=info)
    check_and_maybe_update()
    assert calls["install"] is False


def test_runner_skips_when_release_lacks_wheel(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runner_module, "_lock_path", lambda: tmp_path / "update.lock")
    info = ReleaseInfo(tag_name="2026.06.0", wheel_url=None)
    calls = _patch_runner(monkeypatch, editable=False, current="2026.05.1", info=info)
    check_and_maybe_update()
    assert calls["install"] is False


def test_runner_skips_when_tag_is_invalid_version(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runner_module, "_lock_path", lambda: tmp_path / "update.lock")
    info = ReleaseInfo(tag_name="not-a-version", wheel_url="https://example.com/x.whl")
    calls = _patch_runner(monkeypatch, editable=False, current="2026.05.1", info=info)
    check_and_maybe_update()
    assert calls["install"] is False


def test_runner_installs_and_re_execs_when_newer_version_available(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runner_module, "_lock_path", lambda: tmp_path / "update.lock")
    info = ReleaseInfo(tag_name="2026.06.0", wheel_url="https://example.com/x.whl")
    calls = _patch_runner(monkeypatch, editable=False, current="2026.05.1", info=info)
    check_and_maybe_update()
    assert calls["install"] is True
    assert calls["execv"] is not None


def test_runner_continues_when_install_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runner_module, "_lock_path", lambda: tmp_path / "update.lock")
    info = ReleaseInfo(tag_name="2026.06.0", wheel_url="https://example.com/x.whl")
    calls = _patch_runner(
        monkeypatch,
        editable=False,
        current="2026.05.1",
        info=info,
        install_succeeds=False,
    )
    check_and_maybe_update()
    assert calls["install"] is True
    assert calls["execv"] is None


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX flock test")
def test_runner_skips_when_lockfile_held(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate another nexus invocation holding the lock; runner skips."""
    info = ReleaseInfo(tag_name="2026.06.0", wheel_url="https://example.com/x.whl")
    calls = _patch_runner(monkeypatch, editable=False, current="2026.05.1", info=info)

    lock_path = tmp_path / "update.lock"
    monkeypatch.setattr(runner_module, "_lock_path", lambda: lock_path)
    held_lock = lock_path.open("w")
    fcntl.flock(held_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        check_and_maybe_update()
    finally:
        fcntl.flock(held_lock.fileno(), fcntl.LOCK_UN)
        held_lock.close()
    assert calls["install"] is False


def test_runner_re_exec_uses_subprocess_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """On Windows, re-exec falls back to subprocess.run + sys.exit."""
    info = ReleaseInfo(tag_name="2026.06.0", wheel_url="https://example.com/x.whl")
    calls = _patch_runner(monkeypatch, editable=False, current="2026.05.1", info=info)

    # Skip lock acquisition because msvcrt is not importable on POSIX test runners.
    def fake_acquire() -> str:
        return "stub-lock"

    def fake_release(lock: object) -> None:
        return None

    monkeypatch.setattr(runner_module, "_try_acquire_lock", fake_acquire)
    monkeypatch.setattr(runner_module, "_release_lock", fake_release)

    captured: list[list[str]] = []

    def fake_run(cmd: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        captured.append(cmd)
        return subprocess.CompletedProcess(args=cmd, returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(sys, "platform", "win32")
    check_and_maybe_update()
    assert captured  # subprocess.run was called
    assert calls["exit"] == 0


def test_runner_logs_when_re_exec_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """OSError during execv is caught; user keeps current code."""
    monkeypatch.setattr(runner_module, "_lock_path", lambda: tmp_path / "update.lock")
    info = ReleaseInfo(tag_name="2026.06.0", wheel_url="https://example.com/x.whl")
    _patch_runner(monkeypatch, editable=False, current="2026.05.1", info=info)

    def raise_oserror(path: str, argv: list[str]) -> None:
        raise OSError("execv blew up")

    monkeypatch.setattr(os, "execv", raise_oserror)
    check_and_maybe_update()  # must not raise


def test_runner_skips_when_download_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """download_wheel raising UpdaterError is caught; runner continues."""
    monkeypatch.setattr(runner_module, "_lock_path", lambda: tmp_path / "update.lock")
    info = ReleaseInfo(tag_name="2026.06.0", wheel_url="https://example.com/x.whl")
    calls = _patch_runner(monkeypatch, editable=False, current="2026.05.1", info=info)

    def raise_updater_error(
        url: str,
        *,
        dest_dir: Path,
        httpx_client: httpx.Client | None = None,
    ) -> Path:
        raise UpdaterError("simulated download failure")

    monkeypatch.setattr(runner_module, "download_wheel", raise_updater_error)
    check_and_maybe_update()
    assert calls["execv"] is None


def test_build_client_returns_real_github_releases_client() -> None:
    client = runner_module._build_client()
    assert isinstance(client, GitHubReleasesClient)


def test_lock_path_uses_nexus_paths_cache_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_lock_path resolves under NexusPaths.from_env().root / cache."""

    def fake_from_env() -> NexusPaths:
        return NexusPaths(root=tmp_path)

    monkeypatch.setattr(NexusPaths, "from_env", fake_from_env)
    lock = runner_module._lock_path()
    assert lock == tmp_path / "cache" / "update.lock"
    assert lock.parent.is_dir()
