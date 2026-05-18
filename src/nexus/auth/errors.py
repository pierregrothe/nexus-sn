# nexus/auth/errors.py
# Authentication error types.
# Author: Pierre Grothe
# Date: 2026-05-07

"""Typed exceptions for the auth layer."""

__all__ = ["AuthError", "KeychainUnavailableError"]


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


class KeychainUnavailableError(Exception):
    """Raised when the OS keychain backend is not usable.

    Used by ``KeychainClient.check_available`` to fail-fast before any
    interactive prompt asks the user for a password the wizard cannot
    persist.

    Attributes:
        reason: One of "fail", "null", "locked", "no-backend" -- a
            short slug that callers can branch on in tests.
        hint: Distro-specific, human-readable suggestion for resolution.
    """

    def __init__(self, reason: str, hint: str) -> None:
        """Initialize with the failure reason and an actionable hint.

        Args:
            reason: Short slug describing the backend state.
            hint: Human-readable resolution suggestion.
        """
        super().__init__(f"Keychain unavailable ({reason}): {hint}")
        self.reason = reason
        self.hint = hint
