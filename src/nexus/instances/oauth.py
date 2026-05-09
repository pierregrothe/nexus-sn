# src/nexus/instances/oauth.py
# ServiceNow OAuth2 client: token exchange, auto-refresh, keychain I/O.
# Author: Pierre Grothe
# Date: 2026-05-08
"""SNOAuthClient: manages OAuth2 token lifecycle for one SN instance."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

from nexus.auth.keychain import KeychainClient
from nexus.instances.errors import OAuthError, TokenExpiredError

log = logging.getLogger(__name__)

__all__ = ["SNOAuthClient", "TokenResponse"]

_REFRESH_BUFFER = timedelta(minutes=5)
_OAUTH_PATH = "/oauth_token.do"


@dataclass(slots=True, frozen=True)
class TokenResponse:
    """Parsed response from a successful /oauth_token.do POST."""

    access_token: str
    refresh_token: str
    expires_in: int


class SNOAuthClient:
    """Manages OAuth2 token lifecycle for one SN instance.

    Args:
        profile: Instance profile name (used as keychain service key component).
        url: Full instance URL including scheme.
        client_id: OAuth application client_id (not a secret).
        username: SN login username.
        keychain: KeychainClient for token storage. Defaults to a standard client.
        transport: Optional httpx transport for testing. Omit in production.
    """

    def __init__(
        self,
        *,
        profile: str,
        url: str,
        client_id: str,
        username: str,
        keychain: KeychainClient | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """See class docstring."""
        self._profile = profile
        self._url = url
        self._client_id = client_id
        self._username = username
        self._keychain = keychain or KeychainClient()
        self._transport = transport

    def exchange(self, client_secret: str, password: str) -> TokenResponse:
        """POST Password Grant to obtain an initial token pair.

        Stores client_secret, access_token, and refresh_token in the keychain.
        The password is used once for the exchange and never stored.

        Args:
            client_secret: OAuth application client secret.
            password: SN user password. Discarded after the exchange.

        Returns:
            TokenResponse with access_token, refresh_token, expires_in.

        Raises:
            OAuthError: If the token exchange fails.
        """
        response = self._post_grant(
            grant_type="password",
            client_secret=client_secret,
            extra={"username": self._username, "password": password},
        )
        self._store_tokens(client_secret, response.access_token, response.refresh_token)
        return response

    def get_bearer_token(self, token_expires_at: datetime) -> tuple[str, datetime]:
        """Return a valid bearer token, refreshing automatically if near expiry.

        Args:
            token_expires_at: Current token expiry from meta.json (UTC-aware).

        Returns:
            Tuple of (access_token, updated_expiry). updated_expiry equals
            token_expires_at when no refresh was needed, or the new expiry
            after a successful refresh.

        Raises:
            TokenExpiredError: If the refresh token itself has expired.
            OAuthError: If the refresh call fails for any other reason.
        """
        now = datetime.now(UTC)
        if now + _REFRESH_BUFFER < token_expires_at:
            return (
                self._keychain.get(f"sn-{self._profile}", "access-token"),
                token_expires_at,
            )

        client_secret = self._keychain.get(f"sn-{self._profile}", "client-secret")
        refresh_token = self._keychain.get(f"sn-{self._profile}", "refresh-token")

        try:
            response = self._post_grant(
                grant_type="refresh_token",
                client_secret=client_secret,
                extra={"refresh_token": refresh_token},
            )
        except OAuthError as exc:
            if exc.error_code == "invalid_grant":
                raise TokenExpiredError(self._profile) from exc
            raise

        self._store_tokens(client_secret, response.access_token, response.refresh_token)
        return response.access_token, now + timedelta(seconds=response.expires_in)

    def delete_tokens(self) -> None:
        """Remove all keychain entries for this profile."""
        for account in ("client-secret", "access-token", "refresh-token"):
            self._keychain.delete(f"sn-{self._profile}", account)

    def _post_grant(
        self,
        *,
        grant_type: str,
        client_secret: str,
        extra: dict[str, str],
    ) -> TokenResponse:
        data: dict[str, str] = {
            "grant_type": grant_type,
            "client_id": self._client_id,
            "client_secret": client_secret,
            **extra,
        }
        if self._transport is not None:
            client_ctx = httpx.Client(timeout=30.0, transport=self._transport)
        else:
            client_ctx = httpx.Client(timeout=30.0)
        with client_ctx as client:
            resp = client.post(f"{self._url}{_OAUTH_PATH}", data=data)

        if resp.status_code != 200:
            try:
                body = resp.json()
                desc = str(body.get("error_description", f"HTTP {resp.status_code}"))
                code = str(body.get("error", ""))
            except ValueError, KeyError:
                desc = f"HTTP {resp.status_code}"
                code = ""
            raise OAuthError(desc, error_code=code)

        try:
            body = resp.json()
            return TokenResponse(
                access_token=str(body["access_token"]),
                refresh_token=str(body["refresh_token"]),
                expires_in=int(body["expires_in"]),
            )
        except (ValueError, KeyError) as exc:
            raise OAuthError(f"Malformed token response: {exc}") from exc

    def _store_tokens(self, client_secret: str, access_token: str, refresh_token: str) -> None:
        profile = self._profile
        self._keychain.set(f"sn-{profile}", "client-secret", client_secret)
        self._keychain.set(f"sn-{profile}", "access-token", access_token)
        self._keychain.set(f"sn-{profile}", "refresh-token", refresh_token)
