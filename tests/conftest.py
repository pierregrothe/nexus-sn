# tests/conftest.py
# Shared pytest fixtures for the NEXUS test suite.
# Author: Pierre Grothe
# Date: 2026-05-07

"""Pytest configuration and shared fixtures."""

import logging
from pathlib import Path

import httpx
import pytest

from nexus.cache import clear_cache
from nexus.config.paths import NexusPaths
from nexus.config.settings import NexusConfig

# Configure logging for tests
logging.basicConfig(level=logging.DEBUG)


@pytest.fixture(autouse=True)
def _clear_cached_paths_between_tests() -> None:  # pyright: ignore[reportUnusedFunction]
    """Drop the cached NexusPaths.from_env result before each test.

    NexusPaths.from_env() is @cached(ttl=None) so the first call's result
    sticks for the lifetime of the process. Tests that monkeypatch
    NEXUS_CONFIG_PATH need a fresh cache; this fixture provides it.
    """
    clear_cache(NexusPaths.from_env)


@pytest.fixture
def nexus_paths(tmp_path: Path) -> NexusPaths:
    """Return a NexusPaths instance rooted at the pytest tmp directory.

    Args:
        tmp_path: Pytest-provided temporary directory.

    Returns:
        NexusPaths with root set to tmp_path / ".nexus".
    """
    return NexusPaths(root=tmp_path / ".nexus")


@pytest.fixture
def default_config() -> NexusConfig:
    """Return a default NexusConfig instance for testing.

    Returns:
        NexusConfig with all fields at default values.
    """
    return NexusConfig.default()


def transport_returning(response: httpx.Response) -> httpx.MockTransport:
    """Build an httpx.MockTransport that always returns ``response``."""
    return httpx.MockTransport(lambda req: response)


def transport_raising(exc: Exception) -> httpx.MockTransport:
    """Build an httpx.MockTransport whose handler raises ``exc``."""

    def handler(req: httpx.Request) -> httpx.Response:
        raise exc

    return httpx.MockTransport(handler)
