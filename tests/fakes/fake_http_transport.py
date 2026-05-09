# tests/fakes/fake_http_transport.py
# Fake synchronous httpx transport for OAuth tests.
# Author: Pierre Grothe
# Date: 2026-05-08
"""FakeOAuthTransport: returns canned OAuth token responses without HTTP."""

import httpx

__all__ = ["FakeOAuthTransport"]


class FakeOAuthTransport(httpx.BaseTransport):
    """Returns a canned /oauth_token.do response for SNOAuthClient tests.

    Args:
        access_token: Token to return on success.
        refresh_token: Refresh token to return on success.
        expires_in: Token lifetime in seconds.
        status_code: HTTP status code to return (200 = success, 400 = failure).
        error_description: Error description returned on non-200 responses.
        error_code: Structured error code returned in 'error' field on non-200 responses.
    """

    def __init__(
        self,
        *,
        access_token: str = "test-access-token",
        refresh_token: str = "test-refresh-token",
        expires_in: int = 1800,
        status_code: int = 200,
        error_description: str = "",
        error_code: str = "invalid_grant",
    ) -> None:
        """See class docstring."""
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._expires_in = expires_in
        self._status_code = status_code
        self._error_description = error_description
        self._error_code = error_code

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Return canned OAuth response regardless of request content.

        Args:
            request: Incoming httpx request (not inspected).

        Returns:
            httpx.Response with success or error body.
        """
        if self._status_code == 200:
            return httpx.Response(
                200,
                json={
                    "access_token": self._access_token,
                    "refresh_token": self._refresh_token,
                    "expires_in": self._expires_in,
                    "token_type": "Bearer",
                    "scope": "useraccount",
                },
            )
        return httpx.Response(
            self._status_code,
            json={
                "error": self._error_code,
                "error_description": self._error_description or self._error_code,
            },
        )
