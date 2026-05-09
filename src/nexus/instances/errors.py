# src/nexus/instances/errors.py
# Error hierarchy for instance management.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Instance management errors."""

__all__ = [
    "InstanceError",
    "InstanceNotFoundError",
    "OAuthError",
    "SnapshotError",
    "TokenExpiredError",
]


class InstanceError(Exception):
    """Base class for all instance management errors."""


class InstanceNotFoundError(InstanceError):
    """Raised when a profile directory does not exist in the registry."""

    def __init__(self, profile: str) -> None:
        """Initialize with the missing profile name.

        Args:
            profile: The profile name that was not found.
        """
        super().__init__(
            f"Instance {profile!r} not found. " f"Run 'nexus instance register {profile}'."
        )
        self.profile = profile


class OAuthError(InstanceError):
    """Raised when OAuth token exchange or refresh fails."""

    def __init__(self, message: str) -> None:
        """Initialize with the OAuth error description.

        Args:
            message: The OAuth error description from the server.
        """
        super().__init__(f"OAuth error: {message}")


class TokenExpiredError(InstanceError):
    """Raised when the refresh token has exceeded its 100-day TTL."""

    def __init__(self, profile: str) -> None:
        """Initialize with the profile whose token expired.

        Args:
            profile: The profile name whose refresh token expired.
        """
        super().__init__(
            f"Refresh token for {profile!r} has expired. "
            f"Run 'nexus instance connect {profile}' to re-authenticate."
        )
        self.profile = profile


class SnapshotError(InstanceError):
    """Raised when a REST call fails during instance refresh."""

    def __init__(self, table: str, status_code: int) -> None:
        """Initialize with the failing table and HTTP status code.

        Args:
            table: The SN table name that failed.
            status_code: The HTTP status code returned.
        """
        super().__init__(f"Failed to snapshot table {table!r}: HTTP {status_code}")
        self.table = table
        self.status_code = status_code
