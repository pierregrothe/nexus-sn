# src/nexus/api/errors.py
# Anthropic API error types.
# Author: Pierre Grothe
# Date: 2026-05-07
"""Typed exceptions for the Anthropic API layer."""

__all__ = ["AnthropicError", "KrokiError"]


class AnthropicError(Exception):
    """Raised when the Anthropic API returns an error status.

    Args:
        status_code: HTTP status code from the API response.
        message: Error message from the API response body.
    """

    def __init__(self, status_code: int, message: str) -> None:
        """Initialize with HTTP status code and error message."""
        self.status_code = status_code
        self.message = message
        super().__init__(f"Anthropic API error {status_code}: {message}")


class KrokiError(Exception):
    """Raised when the Kroki render service returns a non-2xx status.

    Args:
        status_code: HTTP status code from the Kroki response.
        message: Error message from the Kroki response body (truncated).
    """

    def __init__(self, status_code: int, message: str) -> None:
        """Initialize with HTTP status code and error message."""
        self.status_code = status_code
        self.message = message
        super().__init__(f"Kroki render error {status_code}: {message}")
