# tests/fakes/fake_keychain.py
# In-memory keychain fake for tests. No OS keychain interaction.
# Author: Pierre Grothe
# Date: 2026-05-07

"""FakeKeychainClient: in-memory substitute for KeychainClient."""

from nexus.auth.errors import AuthError, KeychainUnavailableError
from nexus.auth.keychain import KeychainClient

__all__ = ["FakeKeychainClient"]


class FakeKeychainClient(KeychainClient):
    """In-memory keychain for tests. Pre-seeded with test credentials.

    Args:
        credentials: Optional initial credential map {(service, username): secret}.
        failure_kind: Optional failure reason that ``check_available`` will
            raise as a ``KeychainUnavailableError``. One of ``None``
            (available), ``"fail"``, ``"null"``, ``"locked"``,
            ``"no-backend"``. Defaults to ``None``.
    """

    def __init__(
        self,
        credentials: dict[tuple[str, str], str] | None = None,
        *,
        failure_kind: str | None = None,
    ) -> None:
        self._store: dict[tuple[str, str], str] = credentials or {}
        self._failure_kind: str | None = failure_kind

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

    def check_available(self) -> None:
        """Raise ``KeychainUnavailableError`` when constructed with ``failure_kind``.

        Args:
            None.

        Raises:
            KeychainUnavailableError: When ``failure_kind`` was set at
                construction time.
        """
        if self._failure_kind is None:
            return
        hints = {
            "fail": "no usable keyring backend (test)",
            "null": "null backend (test)",
            "locked": "keychain is locked (test)",
            "no-backend": "no native backend available (test)",
        }
        hint = hints.get(self._failure_kind, f"unknown failure_kind: {self._failure_kind}")
        raise KeychainUnavailableError(self._failure_kind, hint)
