# nexus/auth/keychain.py
# OS keychain abstraction built on the keyring library.
# Author: Pierre Grothe
# Date: 2026-05-07

"""KeychainClient: store and retrieve secrets from the OS keychain.

Wraps the keyring library. Raises AuthError (not KeyError) on missing
credentials so callers get a consistent error type.
"""

import logging
import platform
from typing import Final

import keyring
from keyring.backends import fail as _fail_backend
from keyring.backends import null as _null_backend
from keyring.errors import KeyringError, KeyringLocked, NoKeyringError, PasswordDeleteError

from nexus.auth.errors import AuthError, KeychainUnavailableError

log = logging.getLogger(__name__)

__all__ = ["KeychainClient"]

_PROBE_SERVICE: Final[str] = "probe"
_PROBE_USERNAME: Final[str] = "_check_available_"
_PROBE_SECRET: Final[str] = "ok"


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

    def check_available(self) -> None:
        """Probe the OS keychain backend; raise if it is not usable.

        First inspects ``keyring.get_keyring()`` for the well-known
        no-op backends (``fail`` and ``null``). Then round-trips a
        sentinel credential via the real ``keyring`` API. Any backend
        error during the round-trip is mapped to a
        ``KeychainUnavailableError`` with a distro-specific hint.

        The sentinel is deleted on the way out; a delete failure is
        ignored so a half-probed state never accrues over time.

        Raises:
            KeychainUnavailableError: When the backend is the fail or
                null sentinel, is locked, refuses to store, or has no
                usable native implementation.
        """
        backend = keyring.get_keyring()
        if isinstance(backend, _fail_backend.Keyring):
            raise KeychainUnavailableError("fail", _distro_hint("fail"))
        if isinstance(backend, _null_backend.Keyring):
            raise KeychainUnavailableError("null", _distro_hint("null"))
        service = self._service(_PROBE_SERVICE)
        try:
            keyring.set_password(service, _PROBE_USERNAME, _PROBE_SECRET)
            retrieved = keyring.get_password(service, _PROBE_USERNAME)
            if retrieved != _PROBE_SECRET:
                raise KeychainUnavailableError("no-backend", _distro_hint("no-backend"))
        except KeyringLocked as exc:
            raise KeychainUnavailableError("locked", _distro_hint("locked")) from exc
        except NoKeyringError as exc:
            raise KeychainUnavailableError("no-backend", _distro_hint("no-backend")) from exc
        except KeyringError as exc:
            raise KeychainUnavailableError("no-backend", _distro_hint("no-backend")) from exc
        finally:
            try:
                keyring.delete_password(service, _PROBE_USERNAME)
            except PasswordDeleteError, KeyringError:
                log.debug("probe sentinel could not be deleted; ignoring")


_HINTS_BY_SYSTEM: Final[dict[str, dict[str, str]]] = {
    "Darwin": {
        "fail": "Unlock your macOS login keychain in Keychain Access.",
        "null": "KEYRING_BACKEND is set to a null backend. Unset it and retry.",
        "locked": "Unlock your macOS login keychain in Keychain Access.",
        "no-backend": "Reinstall the 'keyring' package to restore the macOS backend.",
    },
    "Windows": {
        "fail": "Windows Credential Manager is not reachable. Ensure the service is running.",
        "null": "KEYRING_BACKEND is set to a null backend. Unset it and retry.",
        "locked": "Sign in to Windows interactively so the Credential Manager is unlocked.",
        "no-backend": "Reinstall the 'keyring' package to restore the Windows backend.",
    },
    "Linux": {
        "fail": (
            "No usable keyring backend. Install gnome-keyring or KWallet "
            "(e.g. 'sudo apt install gnome-keyring')."
        ),
        "null": "KEYRING_BACKEND is set to a null backend. Unset it and retry.",
        "locked": "Unlock your keyring (e.g. 'gnome-keyring-daemon --unlock').",
        "no-backend": ("No Secret Service backend is available. Install gnome-keyring or KWallet."),
    },
}

_FALLBACK_HINT: Final[str] = "Keychain is unavailable; verify your OS credential store."


def _distro_hint(kind: str, system: str | None = None) -> str:
    """Return a one-line resolution hint matched to ``system`` (defaulting to host).

    Args:
        kind: One of "fail", "null", "locked", "no-backend".
        system: Platform name as returned by ``platform.system()``
            (``"Darwin"``, ``"Windows"``, ``"Linux"``). Defaults to the
            running host; tests pass it explicitly to exercise the
            non-host branches.

    Returns:
        Human-readable hint string. Falls back to a generic message
        for unknown ``kind`` or ``system`` values rather than raising --
        the caller is already in an error path.
    """
    resolved = system if system is not None else platform.system()
    hints = _HINTS_BY_SYSTEM.get(resolved, _HINTS_BY_SYSTEM.get("Linux", {}))
    return hints.get(kind, _FALLBACK_HINT)
