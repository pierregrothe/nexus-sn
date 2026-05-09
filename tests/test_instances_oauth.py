# tests/test_instances_oauth.py
# Tests for SNOAuthClient token exchange and refresh.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for nexus.instances.oauth."""

from datetime import UTC, datetime, timedelta

import pytest

from nexus.auth.errors import AuthError
from nexus.instances.errors import OAuthError, TokenExpiredError
from nexus.instances.oauth import SNOAuthClient, TokenResponse
from tests.fakes import FakeKeychainClient
from tests.fakes.fake_http_transport import FakeOAuthTransport


def _client(
    keychain: FakeKeychainClient | None = None,
    transport: FakeOAuthTransport | None = None,
) -> SNOAuthClient:
    return SNOAuthClient(
        profile="dev12345",
        url="https://dev12345.service-now.com",
        client_id="client-123",
        username="admin",
        keychain=keychain or FakeKeychainClient(),
        transport=transport or FakeOAuthTransport(),
    )


def test_sn_oauth_client_exchange_returns_token_response() -> None:
    transport = FakeOAuthTransport(access_token="tok", refresh_token="ref", expires_in=1800)
    response = _client(transport=transport).exchange("secret", "password")
    assert isinstance(response, TokenResponse)
    assert response.access_token == "tok"
    assert response.expires_in == 1800


def test_sn_oauth_client_exchange_stores_all_three_keychain_entries() -> None:
    keychain = FakeKeychainClient()
    transport = FakeOAuthTransport(access_token="tok", refresh_token="ref")
    _client(keychain=keychain, transport=transport).exchange("secret", "password")
    assert keychain.get("sn-dev12345", "access-token") == "tok"
    assert keychain.get("sn-dev12345", "refresh-token") == "ref"
    assert keychain.get("sn-dev12345", "client-secret") == "secret"


def test_sn_oauth_client_exchange_raises_oauth_error_on_failure() -> None:
    transport = FakeOAuthTransport(status_code=400, error_description="bad credentials")
    with pytest.raises(OAuthError, match="bad credentials"):
        _client(transport=transport).exchange("bad-secret", "password")


def test_sn_oauth_client_get_bearer_token_returns_existing_when_valid() -> None:
    keychain = FakeKeychainClient({("sn-dev12345", "access-token"): "existing-token"})
    future = datetime.now(UTC) + timedelta(hours=1)
    token, expiry = _client(keychain=keychain).get_bearer_token(future)
    assert token == "existing-token"
    assert expiry == future


def test_sn_oauth_client_get_bearer_token_refreshes_when_near_expiry() -> None:
    keychain = FakeKeychainClient(
        {
            ("sn-dev12345", "client-secret"): "secret",
            ("sn-dev12345", "refresh-token"): "old-refresh",
        }
    )
    transport = FakeOAuthTransport(access_token="new-tok", refresh_token="new-ref", expires_in=1800)
    near_expiry = datetime.now(UTC) + timedelta(minutes=2)
    token, new_expiry = _client(keychain=keychain, transport=transport).get_bearer_token(
        near_expiry
    )
    assert token == "new-tok"
    assert keychain.get("sn-dev12345", "access-token") == "new-tok"
    assert new_expiry > near_expiry


def test_sn_oauth_client_get_bearer_token_raises_token_expired_on_invalid_grant() -> None:
    keychain = FakeKeychainClient(
        {
            ("sn-dev12345", "client-secret"): "secret",
            ("sn-dev12345", "refresh-token"): "expired-ref",
        }
    )
    transport = FakeOAuthTransport(status_code=400, error_description="invalid_grant")
    near_expiry = datetime.now(UTC) + timedelta(minutes=2)
    with pytest.raises(TokenExpiredError):
        _client(keychain=keychain, transport=transport).get_bearer_token(near_expiry)


def test_sn_oauth_client_delete_tokens_removes_all_keychain_entries() -> None:
    keychain = FakeKeychainClient(
        {
            ("sn-dev12345", "client-secret"): "s",
            ("sn-dev12345", "access-token"): "a",
            ("sn-dev12345", "refresh-token"): "r",
        }
    )
    _client(keychain=keychain).delete_tokens()
    with pytest.raises(AuthError):
        keychain.get("sn-dev12345", "access-token")
