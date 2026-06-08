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

# Configure logging for tests. WARNING (not DEBUG) keeps per-test overhead
# and captured-output noise down across the full suite; individual tests that
# assert on lower-level records use caplog.set_level() locally.
logging.basicConfig(level=logging.WARNING)


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
    """Build an httpx.MockTransport that always returns ``response``.

    Args:
        response: The response every request should receive.

    Returns:
        An httpx.MockTransport that returns ``response`` for any request.
    """
    return httpx.MockTransport(lambda req: response)


def transport_raising(exc: Exception) -> httpx.MockTransport:
    """Build an httpx.MockTransport whose handler raises ``exc``.

    Args:
        exc: The exception raised on every request.

    Returns:
        An httpx.MockTransport whose handler raises ``exc``.
    """

    def handler(req: httpx.Request) -> httpx.Response:
        raise exc

    return httpx.MockTransport(handler)


def isolate_home(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    """Redirect ``Path.home()`` to ``home`` on POSIX and Windows.

    Sets both ``HOME`` (POSIX) and ``USERPROFILE`` (Windows) so
    ``Path.home()`` resolves identically on both platforms. Setting only
    ``HOME`` is insufficient on Windows where ``Path.home()`` consults
    ``USERPROFILE``.

    Args:
        monkeypatch: The pytest monkeypatch fixture.
        home: Directory that ``Path.home()`` should resolve to.
    """
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))


def scripted_prompt(answers: list[str]) -> object:
    """Return a ``typer.prompt`` replacement that yields ``answers`` in order.

    Use with ``monkeypatch.setattr(typer, "prompt", scripted_prompt([...]))`` to
    drive a Typer command's interactive prompts from a test.

    Args:
        answers: Strings to return on successive prompt calls.

    Returns:
        A callable with the same surface as ``typer.prompt`` that returns
        ``answers[i]`` on the ``i``-th invocation.
    """
    queue = iter(answers)

    def _prompt(*_args: object, **_kwargs: object) -> str:
        return next(queue)

    return _prompt
