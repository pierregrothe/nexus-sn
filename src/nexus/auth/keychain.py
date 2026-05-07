# nexus/auth/keychain.py
# OS keychain abstraction built on the keyring library.
# Author: Pierre Grothe
# Date: 2026-05-07

"""KeychainClient: store and retrieve secrets from the OS keychain.

Wraps the keyring library. Raises AuthError (not KeyError) on missing
credentials so callers get a consistent error type.
"""

import logging

import keyring
from keyring.errors import PasswordDeleteError

from nexus.auth.errors import AuthError

log = logging.getLogger(__name__)

__all__ = ["KeychainClient"]


class KeychainClient:
    """Thin wrapper around keyring for consistent error handling.

    Args:
        service_prefix: Prefix prepended to all service names, e.g. "nexus".
    """

    def __init__(self, service_prefix: str = "nexus") -> None:
        """Initialize with optional service name prefix."""
        self._prefix = service_prefix

    def _service(self, name: str) -> str:
        return f"{self._prefix}-{name}"

    def get(self, service: str, username: str) -> str:
        """Retrieve a credential from the keychain.

        Args:
            service: Logical service name (prefix is prepended automatically).
            username: Key / account name.

        Returns:
            The stored secret string.

        Raises:
            AuthError: When no credential exists for service + username.
        """
        value = keyring.get_password(self._service(service), username)
        if value is None:
            log.debug("credential not found: service=%s username=%s", service, username)
            raise AuthError(
                service=service,
                username=username,
                suggestion=f"Run 'nexus setup' to configure credentials for {service!r}.",
            )
        log.debug("credential retrieved: service=%s username=%s", service, username)
        return value

    def set(self, service: str, username: str, secret: str) -> None:
        """Store a credential in the keychain.

        Args:
            service: Logical service name.
            username: Key / account name.
            secret: Secret value to store. Never logged.
        """
        keyring.set_password(self._service(service), username, secret)
        log.debug("credential stored: service=%s username=%s", service, username)

    def delete(self, service: str, username: str) -> None:
        """Remove a credential from the keychain.

        Args:
            service: Logical service name.
            username: Key / account name.
        """
        try:
            keyring.delete_password(self._service(service), username)
            log.debug("credential deleted: service=%s username=%s", service, username)
        except PasswordDeleteError:
            log.debug("credential not present, nothing to delete: service=%s", service)
