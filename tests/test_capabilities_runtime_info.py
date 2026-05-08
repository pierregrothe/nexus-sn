# tests/test_capabilities_runtime_info.py
# Tests for the runtime info collector behind `nexus status`.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for nexus.capabilities.runtime_info."""

import os
import time
from pathlib import Path

import pytest

from nexus.capabilities import runtime_info as runtime_module
from nexus.capabilities.runtime_info import collect_runtime_info
from nexus.config.paths import NexusPaths


def _patch_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> NexusPaths:
    """Redirect NexusPaths.from_env to tmp_path."""
    paths = NexusPaths(root=tmp_path)
    monkeypatch.setattr(NexusPaths, "from_env", lambda: paths)
    return paths


def test_collect_runtime_info_returns_dataclass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_paths(monkeypatch, tmp_path)
    info = collect_runtime_info()
    assert info.python_version.count(".") == 2
    assert info.platform_label
    assert info.config_root == tmp_path


def test_install_mode_is_editable_in_dev_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_paths(monkeypatch, tmp_path)
    info = collect_runtime_info()
    # Dev runs `pip install -e .` so editable is the truthful answer.
    assert info.install_mode == "editable"


def test_install_mode_is_source_when_package_not_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(runtime_module, "current_version", lambda: None)
    info = collect_runtime_info()
    assert info.install_mode == "source"


def test_install_mode_is_wheel_when_installed_non_editable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(runtime_module, "current_version", lambda: "2026.05.1")
    monkeypatch.setattr(runtime_module, "is_editable_install", lambda: False)
    info = collect_runtime_info()
    assert info.install_mode == "wheel"


def test_auto_update_disabled_when_env_var_is_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_paths(monkeypatch, tmp_path)
    monkeypatch.setenv("NEXUS_AUTO_UPDATE", "0")
    info = collect_runtime_info()
    assert info.auto_update_enabled is False


def test_auto_update_enabled_when_env_var_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_paths(monkeypatch, tmp_path)
    monkeypatch.delenv("NEXUS_AUTO_UPDATE", raising=False)
    info = collect_runtime_info()
    assert info.auto_update_enabled is True


def test_cache_size_is_zero_when_cache_dir_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_paths(monkeypatch, tmp_path)
    info = collect_runtime_info()
    assert info.cache_size_bytes == 0


def test_cache_size_sums_files_in_cache_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _patch_paths(monkeypatch, tmp_path)
    paths.cache_dir.mkdir()
    (paths.cache_dir / "a.bin").write_bytes(b"x" * 1000)
    (paths.cache_dir / "b.bin").write_bytes(b"y" * 500)
    info = collect_runtime_info()
    assert info.cache_size_bytes == 1500


def test_cache_size_returns_zero_on_oserror_during_walk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _patch_paths(monkeypatch, tmp_path)
    paths.cache_dir.mkdir()
    (paths.cache_dir / "a.bin").write_bytes(b"x" * 5)

    def boom(_self: Path, _pattern: str) -> list[Path]:
        raise OSError("simulated permission denied")

    monkeypatch.setattr(Path, "rglob", boom)
    info = collect_runtime_info()
    assert info.cache_size_bytes == 0


def test_last_check_age_none_when_marker_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_paths(monkeypatch, tmp_path)
    info = collect_runtime_info()
    assert info.last_update_check_ago_seconds is None


def test_last_check_age_returns_none_on_oserror_during_stat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _patch_paths(monkeypatch, tmp_path)
    paths.cache_dir.mkdir()
    (paths.cache_dir / "update.last_check").touch()

    def boom(_self: Path, **_kwargs: object) -> object:
        raise OSError("simulated permission denied")

    monkeypatch.setattr(Path, "stat", boom)
    info = collect_runtime_info()
    assert info.last_update_check_ago_seconds is None


def test_last_check_age_in_seconds_when_marker_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _patch_paths(monkeypatch, tmp_path)
    paths.cache_dir.mkdir()
    marker = paths.cache_dir / "update.last_check"
    marker.touch()
    aged = time.time() - 30
    os.utime(marker, (aged, aged))
    info = collect_runtime_info()
    assert info.last_update_check_ago_seconds is not None
    assert 25 <= info.last_update_check_ago_seconds <= 60
