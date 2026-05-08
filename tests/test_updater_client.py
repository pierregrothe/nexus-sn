# tests/test_updater_client.py
# Tests for GitHubReleasesClient.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for nexus.updater.client."""

import httpx
import pytest

from nexus.updater.client import GitHubReleasesClient


def _transport_returning(response: httpx.Response) -> httpx.MockTransport:
    return httpx.MockTransport(lambda req: response)


def _transport_raising(exc: Exception) -> httpx.MockTransport:
    def handler(req: httpx.Request) -> httpx.Response:
        raise exc

    return httpx.MockTransport(handler)


def test_fetch_latest_returns_release_info_on_200() -> None:
    response = httpx.Response(
        200,
        json={
            "tag_name": "2026.06.0",
            "assets": [
                {
                    "name": "nexus_sn-2026.06.0-py3-none-any.whl",
                    "browser_download_url": "https://example.com/nexus_sn-2026.06.0-py3-none-any.whl",
                }
            ],
        },
    )
    with httpx.Client(transport=_transport_returning(response)) as http_client:
        info = GitHubReleasesClient(httpx_client=http_client).fetch_latest()
    assert info is not None
    assert info.tag_name == "2026.06.0"
    assert info.wheel_url == "https://example.com/nexus_sn-2026.06.0-py3-none-any.whl"


def test_fetch_latest_returns_release_info_with_no_wheel_when_no_assets() -> None:
    response = httpx.Response(200, json={"tag_name": "2026.06.0", "assets": []})
    with httpx.Client(transport=_transport_returning(response)) as http_client:
        info = GitHubReleasesClient(httpx_client=http_client).fetch_latest()
    assert info is not None
    assert info.tag_name == "2026.06.0"
    assert info.wheel_url is None


def test_fetch_latest_skips_non_wheel_assets() -> None:
    response = httpx.Response(
        200,
        json={
            "tag_name": "2026.06.0",
            "assets": [
                {
                    "name": "checksums.txt",
                    "browser_download_url": "https://example.com/checksums.txt",
                },
                {
                    "name": "nexus_sn-2026.06.0-py3-none-any.whl",
                    "browser_download_url": "https://example.com/nexus_sn-2026.06.0-py3-none-any.whl",
                },
            ],
        },
    )
    with httpx.Client(transport=_transport_returning(response)) as http_client:
        info = GitHubReleasesClient(httpx_client=http_client).fetch_latest()
    assert info is not None
    assert info.wheel_url is not None
    assert info.wheel_url.endswith(".whl")


def test_fetch_latest_returns_none_on_404() -> None:
    response = httpx.Response(404, json={"message": "Not Found"})
    with httpx.Client(transport=_transport_returning(response)) as http_client:
        assert GitHubReleasesClient(httpx_client=http_client).fetch_latest() is None


def test_fetch_latest_returns_none_on_403_rate_limit() -> None:
    response = httpx.Response(403, json={"message": "API rate limit exceeded"})
    with httpx.Client(transport=_transport_returning(response)) as http_client:
        assert GitHubReleasesClient(httpx_client=http_client).fetch_latest() is None


def test_fetch_latest_returns_none_on_timeout() -> None:
    transport = _transport_raising(httpx.TimeoutException("timed out"))
    with httpx.Client(transport=transport) as http_client:
        assert GitHubReleasesClient(httpx_client=http_client).fetch_latest() is None


def test_fetch_latest_returns_none_when_tag_name_missing() -> None:
    response = httpx.Response(200, json={"assets": []})
    with httpx.Client(transport=_transport_returning(response)) as http_client:
        assert GitHubReleasesClient(httpx_client=http_client).fetch_latest() is None


def test_fetch_latest_returns_none_on_non_json_body() -> None:
    response = httpx.Response(200, content=b"this is not json")
    with httpx.Client(transport=_transport_returning(response)) as http_client:
        assert GitHubReleasesClient(httpx_client=http_client).fetch_latest() is None


def test_fetch_latest_returns_none_when_response_is_json_array() -> None:
    response = httpx.Response(200, json=["not", "an", "object"])
    with httpx.Client(transport=_transport_returning(response)) as http_client:
        assert GitHubReleasesClient(httpx_client=http_client).fetch_latest() is None


def test_fetch_latest_returns_release_info_when_assets_field_is_not_a_list() -> None:
    response = httpx.Response(200, json={"tag_name": "2026.06.0", "assets": "broken"})
    with httpx.Client(transport=_transport_returning(response)) as http_client:
        info = GitHubReleasesClient(httpx_client=http_client).fetch_latest()
    assert info is not None
    assert info.wheel_url is None


def test_fetch_latest_returns_release_info_when_asset_entry_is_not_a_dict() -> None:
    response = httpx.Response(
        200,
        json={
            "tag_name": "2026.06.0",
            "assets": [
                "garbage",
                {
                    "name": "nexus_sn-2026.06.0-py3-none-any.whl",
                    "browser_download_url": "https://example.com/nexus_sn-2026.06.0-py3-none-any.whl",
                },
            ],
        },
    )
    with httpx.Client(transport=_transport_returning(response)) as http_client:
        info = GitHubReleasesClient(httpx_client=http_client).fetch_latest()
    assert info is not None
    assert info.wheel_url == "https://example.com/nexus_sn-2026.06.0-py3-none-any.whl"


def test_fetch_latest_constructs_default_client_when_none_injected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cover the branch that builds an httpx.Client when no client is injected."""
    response = httpx.Response(
        200,
        json={
            "tag_name": "2026.07.0",
            "assets": [
                {
                    "name": "nexus_sn-2026.07.0-py3-none-any.whl",
                    "browser_download_url": "https://example.com/nexus_sn-2026.07.0-py3-none-any.whl",
                }
            ],
        },
    )

    real_client = httpx.Client

    def fake_client_factory(timeout: float) -> httpx.Client:
        return real_client(transport=_transport_returning(response), timeout=timeout)

    monkeypatch.setattr(httpx, "Client", fake_client_factory)
    info = GitHubReleasesClient().fetch_latest()
    assert info is not None
    assert info.tag_name == "2026.07.0"
