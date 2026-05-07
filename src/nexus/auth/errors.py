# nexus/auth/errors.py
# Authentication error types.
# Author: Pierre Grothe
# Date: 2026-05-07

"""Typed exceptions for the auth layer."""

__all__ = ["AuthError"]


class AuthError(Exception):
    """Raised when a credential cannot be found or is invalid.

    Args:
        service: Keychain service name.
        username: Keychain username / key.
        suggestion: Human-readable suggestion for resolution.
    """

    def __init__(self, service: str, username: str, suggestion: str = "") -> None:
        """Initialize with service name, username, and optional suggestion."""
        self.service = service
        self.username = username
        self.suggestion = suggestion
        super().__init__(f"Credential not found: service={service!r} username={username!r}")
