# tests/test_auth_keychain.py
# Tests for KeychainClient.check_available against real keyring backends.
# Author: Pierre Grothe
# Date: 2026-05-18
"""Tests for KeychainClient.check_available."""

from __future__ import annotations

from collections.abc import Generator
from typing import override

import keyring
import pytest
from keyring.backend import KeyringBackend
from keyring.backends import fail as fail_backend
from keyring.backends import null as null_backend
from keyring.errors import KeyringError, KeyringLocked, NoKeyringError

from nexus.auth.errors import KeychainUnavailableError
from nexus.auth.keychain import KeychainClient, _distro_hint
from tests.fakes import FakeKeychainClient


@pytest.fixture
def restore_keyring() -> Generator[None]:
    """Snapshot and restore the global keyring backend around each test."""
    original = keyring.get_keyring()
    try:
        yield
    finally:
        keyring.set_keyring(original)


class _LockedBackend(KeyringBackend):
    """Real Keyring impl that always raises KeyringLocked on writes."""

    @override
    def set_password(self, service: str, username: str, password: str) -> None:
        raise KeyringLocked

    @override
    def get_password(self, service: str, username: str) -> str | None:
        raise KeyringLocked

    @override
    def delete_password(self, service: str, username: str) -> None:
        raise KeyringLocked


class _NoBackend(KeyringBackend):
    """Real Keyring impl that raises NoKeyringError on writes."""

    @override
    def set_password(self, service: str, username: str, password: str) -> None:
        raise NoKeyringError

    @override
    def get_password(self, service: str, username: str) -> str | None:
        return None

    @override
    def delete_password(self, service: str, username: str) -> None:
        return None


class _GenericFailingBackend(KeyringBackend):
    """Real Keyring impl that raises a generic KeyringError on writes."""

    @override
    def set_password(self, service: str, username: str, password: str) -> None:
        raise KeyringError("generic")

    @override
    def get_password(self, service: str, username: str) -> str | None:
        return None

    @override
    def delete_password(self, service: str, username: str) -> None:
        return None


class _InMemoryBackend(KeyringBackend):
    """Real Keyring impl backed by a dict; passes the round-trip probe."""

    priority = 1  # type: ignore[assignment]

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    @override
    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    @override
    def get_password(self, service: str, username: str) -> str | None:
        return self._store.get((service, username))

    @override
    def delete_password(self, service: str, username: str) -> None:
        self._store.pop((service, username), None)


def test_check_available_returns_none_when_backend_is_usable(
    restore_keyring: None,
) -> None:
    keyring.set_keyring(_InMemoryBackend())
    client = KeychainClient()
    client.check_available()


def test_check_available_raises_when_backend_is_fail(restore_keyring: None) -> None:
    keyring.set_keyring(fail_backend.Keyring())
    client = KeychainClient()
    with pytest.raises(KeychainUnavailableError) as excinfo:
        client.check_available()
    assert excinfo.value.reason == "fail"
    assert excinfo.value.hint != ""


def test_check_available_raises_when_backend_is_null(restore_keyring: None) -> None:
    keyring.set_keyring(null_backend.Keyring())
    client = KeychainClient()
    with pytest.raises(KeychainUnavailableError) as excinfo:
        client.check_available()
    assert excinfo.value.reason == "null"


def test_check_available_raises_locked_when_set_password_raises_locked(
    restore_keyring: None,
) -> None:
    keyring.set_keyring(_LockedBackend())
    client = KeychainClient()
    with pytest.raises(KeychainUnavailableError) as excinfo:
        client.check_available()
    assert excinfo.value.reason == "locked"


def test_check_available_raises_no_backend_when_set_password_raises_no_keyring(
    restore_keyring: None,
) -> None:
    keyring.set_keyring(_NoBackend())
    client = KeychainClient()
    with pytest.raises(KeychainUnavailableError) as excinfo:
        client.check_available()
    assert excinfo.value.reason == "no-backend"


def test_check_available_raises_no_backend_on_generic_keyring_error(
    restore_keyring: None,
) -> None:
    keyring.set_keyring(_GenericFailingBackend())
    client = KeychainClient()
    with pytest.raises(KeychainUnavailableError) as excinfo:
        client.check_available()
    assert excinfo.value.reason == "no-backend"


def test_check_available_raises_no_backend_when_round_trip_mismatches(
    restore_keyring: None,
) -> None:
    class _DropWritesBackend(KeyringBackend):
        priority = 1  # type: ignore[assignment]

        @override
        def set_password(self, service: str, username: str, password: str) -> None:
            return None

        @override
        def get_password(self, service: str, username: str) -> str | None:
            return None

        @override
        def delete_password(self, service: str, username: str) -> None:
            return None

    keyring.set_keyring(_DropWritesBackend())
    client = KeychainClient()
    with pytest.raises(KeychainUnavailableError) as excinfo:
        client.check_available()
    assert excinfo.value.reason == "no-backend"


def test_check_available_does_not_leave_probe_sentinel(restore_keyring: None) -> None:
    backend = _InMemoryBackend()
    keyring.set_keyring(backend)
    client = KeychainClient()
    client.check_available()
    assert backend._store == {}


def test_check_available_swallows_delete_failure(restore_keyring: None) -> None:
    class _SetGetDeleteRaises(KeyringBackend):
        """set/get succeed; delete raises -- check_available must not bubble it."""

        priority = 1  # type: ignore[assignment]

        def __init__(self) -> None:
            self._stored: str | None = None

        @override
        def set_password(self, service: str, username: str, password: str) -> None:
            self._stored = password

        @override
        def get_password(self, service: str, username: str) -> str | None:
            return self._stored

        @override
        def delete_password(self, service: str, username: str) -> None:
            raise KeyringError("delete blocked")

    keyring.set_keyring(_SetGetDeleteRaises())
    client = KeychainClient()
    client.check_available()


def test_fake_keychain_check_available_is_noop_by_default() -> None:
    FakeKeychainClient().check_available()


@pytest.mark.parametrize("kind", ["fail", "null", "locked", "no-backend"])
def test_fake_keychain_check_available_raises_with_configured_failure_kind(
    kind: str,
) -> None:
    keychain = FakeKeychainClient(failure_kind=kind)
    with pytest.raises(KeychainUnavailableError) as excinfo:
        keychain.check_available()
    assert excinfo.value.reason == kind


@pytest.mark.parametrize(
    ("system", "kind", "snippet"),
    [
        ("Darwin", "fail", "Keychain Access"),
        ("Darwin", "null", "KEYRING_BACKEND"),
        ("Darwin", "locked", "Keychain Access"),
        ("Darwin", "no-backend", "keyring"),
        ("Windows", "fail", "Credential Manager"),
        ("Windows", "null", "KEYRING_BACKEND"),
        ("Windows", "locked", "Credential Manager"),
        ("Windows", "no-backend", "keyring"),
        ("Linux", "fail", "gnome-keyring"),
        ("Linux", "null", "KEYRING_BACKEND"),
        ("Linux", "locked", "gnome-keyring"),
        ("Linux", "no-backend", "Secret Service"),
    ],
)
def test_distro_hint_returns_platform_specific_message(
    system: str, kind: str, snippet: str
) -> None:
    assert snippet in _distro_hint(kind, system=system)


def test_distro_hint_falls_back_to_generic_for_unknown_kind() -> None:
    assert "Keychain is unavailable" in _distro_hint("bogus", system="Linux")


def test_distro_hint_falls_back_to_linux_for_unknown_system() -> None:
    assert "gnome-keyring" in _distro_hint("fail", system="Plan9")


def test_distro_hint_uses_running_platform_when_system_not_passed() -> None:
    """Covers the ``platform.system()`` default branch."""
    result = _distro_hint("fail")
    assert isinstance(result, str)
    assert result != ""
