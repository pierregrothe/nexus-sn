# tests/test_api_client.py
# API client layer tests.
# Author: Pierre Grothe
# Date: 2026-05-07
"""Tests for the NEXUS api layer."""

from typing import Any

from nexus.api.errors import AnthropicError
from nexus.api.logging_config import configure_logging
from nexus.config.paths import NexusPaths


def test_anthropic_error_has_status_code_and_message() -> None:
    exc = AnthropicError(429, "Rate limit exceeded")
    assert exc.status_code == 429
    assert exc.message == "Rate limit exceeded"
    assert "429" in str(exc)


def test_configure_logging_creates_logs_directory(tmp_path: Any) -> None:
    paths = NexusPaths(root=tmp_path / ".nexus")
    configure_logging(paths)
    assert (tmp_path / ".nexus" / "logs").is_dir()
