# tests/test_servicenow_client_refresh.py
# Tests for ServiceNowClient token-refresh integration (proactive + reactive).
# Author: Pierre Grothe
# Date: 2026-05-16
"""Tests for the OAuth refresh integration on `ServiceNowClient`.

Exercises both refresh paths added for long-running batch upgrades:

* Reactive -- on 401/403, call the refresh callback and retry once.
* Proactive -- when the stored expiry is within 60s of now, refresh
  before issuing the request.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from nexus.connectors.servicenow.client import ServiceNowClient
from nexus.connectors.servicenow.errors import SNAuthError, SNClientError

__all__: list[str] = []


def _install_transport(client: ServiceNowClient, transport: httpx.MockTransport) -> None:
    """Replace the live httpx client with one wired to ``transport``.

    Mirrors the pattern used in ``test_servicenow_appmanager.py``: the
    public ``ServiceNowClient.__aenter__`` builds a real client, then we
    swap in a MockTransport-backed client preserving the Authorization
    header so refresh-swap logic operates on the mock.
    """
    bearer = (
        client._client.headers["Authorization"]  # pyright: ignore[reportPrivateUsage]
        if client._client is not None  # pyright: ignore[reportPrivateUsage]
        else f"Bearer {client._token}"  # pyright: ignore[reportPrivateUsage]
    )
    client._client = httpx.AsyncClient(  # pyright: ignore[reportPrivateUsage]
        base_url=client._base_url,  # pyright: ignore[reportPrivateUsage]
        headers={
            "Authorization": bearer,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        transport=transport,
    )


@pytest.mark.asyncio
async def test_request_retries_after_refresh_when_first_response_is_401() -> None:
    """401 -> refresh callback fires -> request retried with fresh token -> 200."""
    refresh_calls: list[int] = []
    request_tokens: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        request_tokens.append(request.headers["Authorization"])
        if len(request_tokens) == 1:
            return httpx.Response(401, json={"error": "Token expired"})
        return httpx.Response(200, json={"result": {"ok": True}})

    async def _refresh() -> tuple[str, datetime]:
        refresh_calls.append(1)
        return "fresh-token", datetime.now(UTC) + timedelta(hours=1)

    async with ServiceNowClient(
        "test.service-now.com",
        token="stale-token",
        refresh_token_callback=_refresh,
    ) as c:
        _install_transport(c, httpx.MockTransport(handler))
        raw = await c.fetch_progress("tracker-x")

    assert raw == {"ok": True}
    assert len(refresh_calls) == 1
    assert request_tokens == ["Bearer stale-token", "Bearer fresh-token"]


@pytest.mark.asyncio
async def test_request_raises_when_retry_also_returns_401() -> None:
    """If the refreshed token also gets 401, surface SNAuthError (no infinite loop)."""
    refresh_calls: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "Still bad"})

    async def _refresh() -> tuple[str, datetime]:
        refresh_calls.append(1)
        return "still-bad-token", datetime.now(UTC) + timedelta(hours=1)

    async with ServiceNowClient(
        "test.service-now.com",
        token="stale",
        refresh_token_callback=_refresh,
    ) as c:
        _install_transport(c, httpx.MockTransport(handler))
        with pytest.raises(SNAuthError):
            await c.fetch_progress("tracker-x")

    # Refresh fired exactly once -- one retry, no infinite loop.
    assert len(refresh_calls) == 1


@pytest.mark.asyncio
async def test_request_raises_immediately_when_no_refresh_callback_configured() -> None:
    """Without a refresh callback, 401 still raises SNAuthError on first response."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "Token expired"})

    async with ServiceNowClient("test.service-now.com", token="stale") as c:
        _install_transport(c, httpx.MockTransport(handler))
        with pytest.raises(SNAuthError):
            await c.fetch_progress("tracker-x")


@pytest.mark.asyncio
async def test_request_does_not_refresh_on_403_because_acl_denial_is_not_an_auth_issue() -> None:
    """403 must NOT trigger refresh -- it's ACL/role denial, not a token problem."""
    refresh_calls: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "ACL denied"})

    async def _refresh() -> tuple[str, datetime]:
        refresh_calls.append(1)
        return "new", datetime.now(UTC) + timedelta(hours=1)

    async with ServiceNowClient(
        "test.service-now.com",
        token="ok",
        refresh_token_callback=_refresh,
    ) as c:
        _install_transport(c, httpx.MockTransport(handler))
        with pytest.raises(SNAuthError):
            await c.fetch_progress("tracker-x")

    assert refresh_calls == []


@pytest.mark.asyncio
async def test_request_refreshes_proactively_when_expiry_is_imminent() -> None:
    """Expiry within 60s of now -> refresh before issuing the request."""
    refresh_calls: list[int] = []
    request_tokens: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        request_tokens.append(request.headers["Authorization"])
        return httpx.Response(200, json={"result": {"ok": True}})

    async def _refresh() -> tuple[str, datetime]:
        refresh_calls.append(1)
        return "fresh-token", datetime.now(UTC) + timedelta(hours=1)

    # Expiry 10s in the past -- well inside the 60s lead window.
    stale_expiry = datetime.now(UTC) - timedelta(seconds=10)
    async with ServiceNowClient(
        "test.service-now.com",
        token="about-to-die",
        refresh_token_callback=_refresh,
        token_expires_at=stale_expiry,
    ) as c:
        _install_transport(c, httpx.MockTransport(handler))
        raw = await c.fetch_progress("tracker-x")

    assert raw == {"ok": True}
    assert len(refresh_calls) == 1
    # First (and only) request must have used the fresh token, not the stale one.
    assert request_tokens == ["Bearer fresh-token"]


@pytest.mark.asyncio
async def test_request_does_not_refresh_when_expiry_is_far_in_future() -> None:
    """Healthy expiry -> no proactive refresh, original token used."""
    refresh_calls: list[int] = []
    request_tokens: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        request_tokens.append(request.headers["Authorization"])
        return httpx.Response(200, json={"result": {"ok": True}})

    async def _refresh() -> tuple[str, datetime]:
        refresh_calls.append(1)
        return "should-not-be-used", datetime.now(UTC) + timedelta(hours=1)

    healthy_expiry = datetime.now(UTC) + timedelta(minutes=20)
    async with ServiceNowClient(
        "test.service-now.com",
        token="healthy-token",
        refresh_token_callback=_refresh,
        token_expires_at=healthy_expiry,
    ) as c:
        _install_transport(c, httpx.MockTransport(handler))
        await c.fetch_progress("tracker-x")

    assert refresh_calls == []
    assert request_tokens == ["Bearer healthy-token"]


@pytest.mark.asyncio
async def test_request_retries_transient_network_error_then_succeeds() -> None:
    """A transient transport error (ReadError) is retried; a later success returns."""
    calls: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadError("transient connection drop")
        return httpx.Response(200, json={"result": {"ok": True}})

    async with ServiceNowClient("test.service-now.com", token="t") as c:
        _install_transport(c, httpx.MockTransport(handler))
        raw = await c.fetch_progress("tracker-x")

    assert raw == {"ok": True}
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_request_raises_snclienterror_after_exhausting_transient_retries() -> None:
    """When every attempt hits a transport error, surface SNClientError."""
    calls: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise httpx.ConnectError("connection refused")

    async with ServiceNowClient("test.service-now.com", token="t") as c:
        _install_transport(c, httpx.MockTransport(handler))
        with pytest.raises(SNClientError):
            await c.fetch_progress("tracker-x")

    assert len(calls) == 3
