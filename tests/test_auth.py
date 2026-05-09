# tests/test_auth.py
# Tests for the auth layer: KeychainClient, ClaudeAuth, SNAuth.
# Author: Pierre Grothe
# Date: 2026-05-07

"""Tests for nexus.auth."""

import pytest

from nexus.auth.claude import ClaudeAuth
from nexus.auth.errors import AuthError
from nexus.auth.servicenow import SNAuth
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


def test_claude_auth_get_api_key_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_CLAUDE_API_KEY", "test-key-from-env")
    auth = ClaudeAuth(keychain=FakeKeychainClient())
    assert auth.get_api_key() == "test-key-from-env"


def test_claude_auth_get_api_key_from_keychain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEXUS_CLAUDE_API_KEY", raising=False)
    keychain = FakeKeychainClient({("claude", "api_key"): "keychain-key"})
    auth = ClaudeAuth(keychain=keychain)
    assert auth.get_api_key() == "keychain-key"


def test_claude_auth_get_api_key_raises_when_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NEXUS_CLAUDE_API_KEY", raising=False)
    auth = ClaudeAuth(keychain=FakeKeychainClient())
    with pytest.raises(AuthError):
        auth.get_api_key()


def test_claude_auth_is_configured_returns_true_with_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEXUS_CLAUDE_API_KEY", "any-key")
    auth = ClaudeAuth(keychain=FakeKeychainClient())
    assert auth.is_configured() is True


def test_claude_auth_is_configured_returns_false_with_no_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NEXUS_CLAUDE_API_KEY", raising=False)
    auth = ClaudeAuth(keychain=FakeKeychainClient())
    assert auth.is_configured() is False


def test_sn_auth_get_password_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_SN_PASSWORD_DEV12345", "env-pass")
    with pytest.warns(DeprecationWarning, match="SNAuth is deprecated"):
        auth = SNAuth(keychain=FakeKeychainClient())
    assert auth.get_password("dev12345", "admin") == "env-pass"


def test_sn_auth_get_password_from_keychain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEXUS_SN_PASSWORD_DEV12345", raising=False)
    keychain = FakeKeychainClient({("sn-dev12345", "admin"): "sn-pass"})
    with pytest.warns(DeprecationWarning, match="SNAuth is deprecated"):
        auth = SNAuth(keychain=keychain)
    assert auth.get_password("dev12345", "admin") == "sn-pass"


def test_sn_auth_get_password_raises_when_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NEXUS_SN_PASSWORD_DEV12345", raising=False)
    with pytest.warns(DeprecationWarning, match="SNAuth is deprecated"):
        auth = SNAuth(keychain=FakeKeychainClient())
    with pytest.raises(AuthError):
        auth.get_password("dev12345", "admin")
