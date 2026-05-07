# tests/test_api_client.py
# API client layer tests.
# Author: Pierre Grothe
# Date: 2026-05-07
"""Tests for the NEXUS api layer."""

import logging
import logging.handlers
from pathlib import Path

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
