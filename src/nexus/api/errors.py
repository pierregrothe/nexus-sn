# src/nexus/api/errors.py
# API-layer error types (Anthropic and Kroki).
# Author: Pierre Grothe
# Date: 2026-05-07
"""Typed exceptions for the API layer: Anthropic and Kroki services."""

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
    """Raised when a Kroki render fails.

    Args:
        status_code: HTTP status code from the Kroki response, or ``None``
            for a transport-level failure (DNS, connect, timeout) before
            any HTTP status was received.
        message: Error message from the Kroki response body (truncated) or
            the transport error detail.
    """

    def __init__(self, status_code: int | None, message: str) -> None:
        """Initialize with an optional HTTP status code and error message."""
        self.status_code = status_code
        self.message = message
        prefix = (
            "Kroki render error" if status_code is None else f"Kroki render error {status_code}"
        )
        super().__init__(f"{prefix}: {message}")
