# nexus/connectors/servicenow/errors.py
# ServiceNow REST client error hierarchy.
# Author: Pierre Grothe
# Date: 2026-05-07

"""Typed exceptions for the ServiceNow connector."""

__all__ = ["SNClientError", "SNAuthError", "SNNotFoundError", "SNRateLimitError"]


class SNClientError(Exception):
    """Base class for ServiceNow client errors.

    Args:
        message: Human-readable error description.
        status_code: HTTP status code, if available.
        suggestion: Recommended remediation step.
    """

    def __init__(self, message: str, status_code: int | None = None, suggestion: str = "") -> None:
        self.status_code = status_code
        self.suggestion = suggestion
        super().__init__(message)


class SNAuthError(SNClientError):
    """Raised on HTTP 401 or 403 responses."""


class SNNotFoundError(SNClientError):
    """Raised on HTTP 404 responses."""


class SNRateLimitError(SNClientError):
    """Raised on HTTP 429 responses."""
