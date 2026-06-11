# tests/schema/test_schema_sync.py
# Tests for GitHubProductCatalogClient and SchemaSync.
# Author: Pierre Grothe
# Date: 2026-06-11
"""Sync client fetches SchemaProductCatalog; SchemaSync caches it."""

from pathlib import Path

import httpx

from nexus.schema.models import ScopeEntry
from nexus.schema.product_registry import ProductRegistry
from nexus.schema.products import SchemaProduct, SchemaProductCatalog
from nexus.schema.sync import GitHubProductCatalogClient, SchemaSync, SchemaSyncSource


def _catalog_json() -> str:
    catalog = SchemaProductCatalog(
        version="1.0",
        products=(
            SchemaProduct(
                key="ham",
                acronym="HAM",
                name="Hardware Asset Management",
                scopes=(ScopeEntry(key="sn_hamp", label="HAM Pro"),),
                bridge_targets=("cmdb_ci",),
            ),
        ),
    )
    return catalog.model_dump_json()


class _OkTransport(httpx.BaseTransport):
    def __init__(self, body: str) -> None:
        self._body = body

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=self._body)


class _ErrorTransport(httpx.BaseTransport):
    def __init__(self, status: int) -> None:
        self._status = status

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(self._status)


def test_github_product_catalog_client_returns_catalog_on_200() -> None:
    client = GitHubProductCatalogClient(
        httpx_client=httpx.Client(transport=_OkTransport(_catalog_json()))
    )
    result = client.fetch_catalog("owner/repo", "main", "schema/products.json")
    assert result is not None
    assert result.resolve("ham") is not None


def test_github_product_catalog_client_returns_none_on_404() -> None:
    client = GitHubProductCatalogClient(
        httpx_client=httpx.Client(transport=_ErrorTransport(404))
    )
    assert client.fetch_catalog("owner/repo", "main", "schema/products.json") is None


def test_github_product_catalog_client_returns_none_on_invalid_json() -> None:
    client = GitHubProductCatalogClient(
        httpx_client=httpx.Client(transport=_OkTransport("not-json"))
    )
    assert client.fetch_catalog("owner/repo", "main", "schema/products.json") is None


def test_schema_sync_run_ok_caches_catalog(tmp_path: Path) -> None:
    http_client = httpx.Client(transport=_OkTransport(_catalog_json()))
    catalog_client = GitHubProductCatalogClient(httpx_client=http_client)
    registry = ProductRegistry(tmp_path)
    report = SchemaSync(client=catalog_client, registry=registry).run(
        repo="owner/repo", branch="main", path="schema/products.json"
    )
    assert report.outcome == "ok"
    assert report.cached is not None
    assert registry.resolve("ham") is not None


def test_schema_sync_run_fetch_failed_preserves_existing_cache(tmp_path: Path) -> None:
    registry = ProductRegistry(tmp_path)
    registry.save_catalog(
        SchemaProductCatalog(
            version="1.0",
            products=(
                SchemaProduct(
                    key="old",
                    acronym="OLD",
                    name="Old Product",
                    scopes=(),
                    bridge_targets=(),
                ),
            ),
        ),
        SchemaSyncSource(repo="owner/repo", branch="main", path="schema/products.json"),
    )

    http_client = httpx.Client(transport=_ErrorTransport(500))
    catalog_client = GitHubProductCatalogClient(httpx_client=http_client)
    report = SchemaSync(client=catalog_client, registry=registry).run(
        repo="owner/repo", branch="main", path="schema/products.json"
    )
    assert report.outcome == "fetch-failed"
    assert registry.resolve("old") is not None
