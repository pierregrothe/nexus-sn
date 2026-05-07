# tests/conftest.py
# Shared pytest fixtures for the NEXUS test suite.
# Author: Pierre Grothe
# Date: 2026-05-07

"""Pytest configuration and shared fixtures."""

import logging
from pathlib import Path

import pytest

from nexus.config.paths import NexusPaths
from nexus.config.settings import NexusConfig

# Configure logging for tests
logging.basicConfig(level=logging.DEBUG)


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
