# tests/fakes/fake_keychain.py
# In-memory keychain fake for tests. No OS keychain interaction.
# Author: Pierre Grothe
# Date: 2026-05-07

"""FakeKeychainClient: in-memory substitute for KeychainClient."""

from nexus.auth.errors import AuthError

__all__ = ["FakeKeychainClient"]


class FakeKeychainClient:
    """In-memory keychain for tests. Pre-seeded with test credentials.

    Args:
        credentials: Optional initial credential map {(service, username): secret}.
    """

    def __init__(self, credentials: dict[tuple[str, str], str] | None = None) -> None:
        self._store: dict[tuple[str, str], str] = credentials or {}

    def get(self, service: str, username: str) -> str:
        """Return a credential or raise AuthError.

        Args:
            service: Service name.
            username: Username / key.

        Returns:
            The stored secret.

        Raises:
            AuthError: When the credential is not present.
        """
        key = (service, username)
        if key not in self._store:
            raise AuthError(service=service, username=username)
        return self._store[key]

    def set(self, service: str, username: str, secret: str) -> None:
        """Store a credential.

        Args:
            service: Service name.
            username: Username / key.
            secret: Secret value.
        """
        self._store[(service, username)] = secret

    def delete(self, service: str, username: str) -> None:
        """Remove a credential if present.

        Args:
            service: Service name.
            username: Username / key.
        """
        self._store.pop((service, username), None)
