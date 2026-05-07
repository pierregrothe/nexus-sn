# tests/test_api_client.py
# API client layer tests.
# Author: Pierre Grothe
# Date: 2026-05-07
"""Tests for the NEXUS api layer."""

from nexus.api.errors import AnthropicError


def test_anthropic_error_has_status_code_and_message() -> None:
    exc = AnthropicError(429, "Rate limit exceeded")
    assert exc.status_code == 429
    assert exc.message == "Rate limit exceeded"
    assert "429" in str(exc)
