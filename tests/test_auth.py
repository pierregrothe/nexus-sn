# tests/test_auth.py
# Tests for the auth layer: KeychainClient.
# Author: Pierre Grothe
# Date: 2026-05-07

"""Tests for nexus.auth."""

import pytest

from nexus.auth.errors import AuthError
from tests.fakes import FakeKeychainClient


def test_fake_keychain_get_returns_stored_value() -> None:
    keychain = FakeKeychainClient({("svc", "user"): "secret"})
    assert keychain.get("svc", "user") == "secret"


def test_fake_keychain_get_raises_auth_error_when_missing() -> None:
    keychain = FakeKeychainClient()
    with pytest.raises(AuthError):
        keychain.get("svc", "user")


def test_fake_keychain_set_then_get_roundtrip() -> None:
    keychain = FakeKeychainClient()
    keychain.set("svc", "user", "mysecret")
    assert keychain.get("svc", "user") == "mysecret"


def test_fake_keychain_delete_removes_credential() -> None:
    keychain = FakeKeychainClient({("svc", "user"): "secret"})
    keychain.delete("svc", "user")
    with pytest.raises(AuthError):
        keychain.get("svc", "user")
