# tests/test_api_client.py
# API client layer tests.
# Author: Pierre Grothe
# Date: 2026-05-07
"""Tests for the NEXUS api layer."""

import logging
import logging.handlers
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.api.client import _TIER_DEFAULTS, ModelTier, _discover_model
from nexus.api.errors import AnthropicError
from nexus.api.logging_config import configure_logging
from nexus.config.paths import NexusPaths


def test_anthropic_error_has_status_code_and_message() -> None:
    exc = AnthropicError(429, "Rate limit exceeded")
    assert exc.status_code == 429
    assert exc.message == "Rate limit exceeded"
    assert "429" in str(exc)


def test_configure_logging_creates_logs_directory_and_attaches_handlers(
    tmp_path: Path,
) -> None:
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    root.handlers.clear()
    try:
        paths = NexusPaths(root=tmp_path / ".nexus")
        configure_logging(paths)
        assert (tmp_path / ".nexus" / "logs").is_dir()
        handler_types = {type(h) for h in root.handlers}
        assert logging.handlers.TimedRotatingFileHandler in handler_types
        assert logging.StreamHandler in handler_types
        assert root.level == logging.INFO
    finally:
        for h in root.handlers:
            h.close()
        root.handlers.clear()
        root.handlers.extend(saved_handlers)
        root.level = saved_level


def test_model_tier_standard_default_is_sonnet() -> None:
    assert _TIER_DEFAULTS[ModelTier.STANDARD] == "claude-sonnet-4-6"


def test_discover_model_returns_newest_by_created_at() -> None:
    older = SimpleNamespace(
        id="claude-sonnet-4-5",
        created_at=datetime(2025, 9, 1, tzinfo=UTC),
    )
    newer = SimpleNamespace(
        id="claude-sonnet-4-6",
        created_at=datetime(2025, 12, 1, tzinfo=UTC),
    )

    class _FakeModels:
        def list(self) -> list:  # type: ignore[type-arg]
            return [older, newer]

    result = _discover_model(SimpleNamespace(models=_FakeModels()), ModelTier.STANDARD)
    assert result == "claude-sonnet-4-6"


def test_discover_model_falls_back_when_list_raises() -> None:
    class _FakeModels:
        def list(self) -> list:  # type: ignore[type-arg]
            raise RuntimeError("connection refused")

    result = _discover_model(SimpleNamespace(models=_FakeModels()), ModelTier.STANDARD)
    assert result == _TIER_DEFAULTS[ModelTier.STANDARD]


def test_discover_model_respects_env_var_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_MODEL_STANDARD", "claude-sonnet-4-99")
    result = _discover_model(SimpleNamespace(models=None), ModelTier.STANDARD)
    assert result == "claude-sonnet-4-99"
