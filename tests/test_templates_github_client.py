# tests/test_templates_github_client.py
# Tests for GitHubTemplateClient (raw.githubusercontent.com manifest fetch).
# Author: Pierre Grothe
# Date: 2026-05-18
"""Tests for nexus.templates.sync.GitHubTemplateClient."""

from __future__ import annotations

import logging
from collections.abc import Callable

import httpx
import pytest

from nexus.templates.sync import GitHubTemplateClient


def _client_for(handler: Callable[[httpx.Request], httpx.Response]) -> GitHubTemplateClient:
    transport = httpx.MockTransport(handler)
    return GitHubTemplateClient(httpx_client=httpx.Client(transport=transport))


def test_fetch_manifest_returns_parsed_manifest_on_200() -> None:
    body = '{"version": "1.0", "generated": "2026-05-07", "templates": []}'

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body)

    client = _client_for(handler)
    manifest = client.fetch_manifest("owner/name", "main", "templates/manifest.json")
    assert manifest is not None
    assert manifest.version == "1.0"
    assert manifest.templates == ()


def test_fetch_manifest_url_includes_repo_branch_and_path() -> None:
    captured: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        return httpx.Response(200, text='{"version":"1.0","generated":"x","templates":[]}')

    client = _client_for(handler)
    client.fetch_manifest("owner/name", "develop", "custom/path.json")
    assert captured["url"] == (
        "https://raw.githubusercontent.com/owner/name/develop/custom/path.json"
    )


def test_fetch_manifest_returns_none_on_404(caplog: pytest.LogCaptureFixture) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="Not Found")

    client = _client_for(handler)
    with caplog.at_level(logging.WARNING, logger="nexus.templates.sync"):
        result = client.fetch_manifest("owner/name", "main", "templates/manifest.json")
    assert result is None
    assert any("status=404" in r.message for r in caplog.records)


def test_fetch_manifest_returns_none_on_403() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="forbidden")

    client = _client_for(handler)
    assert client.fetch_manifest("owner/name", "main", "templates/manifest.json") is None


def test_fetch_manifest_returns_none_on_429_logs_rate_limit(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="rate limited")

    client = _client_for(handler)
    with caplog.at_level(logging.WARNING, logger="nexus.templates.sync"):
        result = client.fetch_manifest("owner/name", "main", "templates/manifest.json")
    assert result is None
    assert any("rate limit" in r.message for r in caplog.records)


def test_fetch_manifest_returns_none_on_connect_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    client = _client_for(handler)
    with caplog.at_level(logging.INFO, logger="nexus.templates.sync"):
        result = client.fetch_manifest("owner/name", "main", "templates/manifest.json")
    assert result is None
    assert any("ConnectError" in r.message for r in caplog.records)


def test_fetch_manifest_returns_none_on_malformed_json(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="{ not json")

    client = _client_for(handler)
    with caplog.at_level(logging.INFO, logger="nexus.templates.sync"):
        result = client.fetch_manifest("owner/name", "main", "templates/manifest.json")
    assert result is None
    assert any(
        "invalid JSON" in r.message or "schema mismatch" in r.message for r in caplog.records
    )


def test_fetch_manifest_returns_none_on_schema_mismatch(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text='{"unrelated": "shape"}')

    client = _client_for(handler)
    with caplog.at_level(logging.INFO, logger="nexus.templates.sync"):
        result = client.fetch_manifest("owner/name", "main", "templates/manifest.json")
    assert result is None
    assert any("schema mismatch" in r.message for r in caplog.records)


def test_fetch_manifest_accepts_empty_templates_array() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text='{"version": "1.0", "generated": "x", "templates": []}')

    client = _client_for(handler)
    manifest = client.fetch_manifest("owner/name", "main", "templates/manifest.json")
    assert manifest is not None
    assert manifest.templates == ()


def test_fetch_manifest_default_timeout_is_10_seconds() -> None:
    client = GitHubTemplateClient()
    assert client._timeout == 10.0
