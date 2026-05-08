# tests/test_updater_current.py
# Tests for current_version and is_editable_install.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for nexus.updater.current."""

from importlib import metadata
from importlib.metadata import PackageNotFoundError

import pytest

from nexus.updater.current import current_version, is_editable_install


def test_current_version_returns_string_when_installed() -> None:
    version = current_version()
    # In dev (pip install -e .) we ARE installed, so a version is present.
    assert version is not None
    assert isinstance(version, str)


def test_current_version_returns_none_when_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_pnf(name: str) -> str:
        raise PackageNotFoundError(name)

    monkeypatch.setattr(metadata, "version", raise_pnf)
    assert current_version() is None


def test_is_editable_install_true_in_dev_environment() -> None:
    # The dev environment uses `pip install -e .`, so this should be True.
    assert is_editable_install() is True


def test_is_editable_install_false_when_origin_says_not_editable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeDirInfo:
        editable = False

    class _FakeOrigin:
        dir_info = _FakeDirInfo()

    class _FakeDistribution:
        @property
        def origin(self) -> _FakeOrigin:
            return _FakeOrigin()

    def fake_distribution(name: str) -> _FakeDistribution:
        return _FakeDistribution()

    monkeypatch.setattr(metadata, "distribution", fake_distribution)
    assert is_editable_install() is False


def test_is_editable_install_false_when_package_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_pnf(name: str) -> str:
        raise PackageNotFoundError(name)

    monkeypatch.setattr(metadata, "distribution", raise_pnf)
    assert is_editable_install() is False


def test_is_editable_install_false_when_origin_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeDistributionNoOrigin:
        origin = None

    def fake_distribution(name: str) -> _FakeDistributionNoOrigin:
        return _FakeDistributionNoOrigin()

    monkeypatch.setattr(metadata, "distribution", fake_distribution)
    assert is_editable_install() is False


def test_is_editable_install_false_when_dir_info_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeOriginNoDirInfo:
        dir_info = None

    class _FakeDistributionNoDirInfo:
        @property
        def origin(self) -> _FakeOriginNoDirInfo:
            return _FakeOriginNoDirInfo()

    def fake_distribution(name: str) -> _FakeDistributionNoDirInfo:
        return _FakeDistributionNoDirInfo()

    monkeypatch.setattr(metadata, "distribution", fake_distribution)
    assert is_editable_install() is False
