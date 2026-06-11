# src/nexus/schema/sync.py
# GitHub sync client and orchestrator for the schema product catalog.
# Author: Pierre Grothe
# Date: 2026-06-11
"""SchemaSyncSource, GitHubProductCatalogClient, SchemaSync, SchemaSyncReport."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from nexus.schema.products import SchemaProductCatalog

if TYPE_CHECKING:
    from nexus.schema.product_registry import CachedSchemaProductCatalog, ProductRegistry

log = logging.getLogger(__name__)

__all__ = [
    "GitHubProductCatalogClient",
    "SchemaSync",
    "SchemaSyncReport",
    "SchemaSyncSource",
]

_CONFIG = ConfigDict(frozen=True, strict=True, extra="forbid")
_DEFAULT_TIMEOUT = 10.0
_OutcomeT = Literal["ok", "fetch-failed"]


class SchemaSyncSource(BaseModel):
    """Record of where a catalog was fetched from.

    Args:
        repo: Canonical owner/name GitHub slug.
        branch: Branch name.
        path: Path to the catalog file within the repo.
    """

    model_config = _CONFIG

    repo: str
    branch: str
    path: str


@dataclass(frozen=True, slots=True)
class SchemaSyncReport:
    """Typed result of a SchemaSync.run() call.

    Attributes:
        outcome: "ok" or "fetch-failed".
        cached: The cached entry on success, else None.
        reason: One-line failure description when outcome != "ok".
    """

    outcome: _OutcomeT
    cached: CachedSchemaProductCatalog | None
    reason: str | None


class GitHubProductCatalogClient:
    """Anonymous fetcher for the raw GitHub schema product catalog.

    Args:
        httpx_client: Optional pre-built httpx.Client. Tests inject one
            backed by a transport stub. Production callers omit it.
        timeout_seconds: HTTP timeout when building the default client.
    """

    def __init__(
        self,
        *,
        httpx_client: httpx.Client | None = None,
        timeout_seconds: float = _DEFAULT_TIMEOUT,
    ) -> None:
        """See class docstring."""
        self._injected = httpx_client
        self._timeout = timeout_seconds

    def fetch_catalog(
        self, repo: str, branch: str, path: str
    ) -> SchemaProductCatalog | None:
        """GET the raw catalog JSON. Returns None on any failure.

        Args:
            repo: Canonical owner/name slug.
            branch: GitHub branch name.
            path: Path within the repo (e.g. "schema/products.json").

        Returns:
            Parsed SchemaProductCatalog, or None on any failure.
        """
        url = f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
        try:
            if self._injected is not None:
                response = self._injected.get(url)
            else:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.get(url)
        except httpx.HTTPError as exc:
            log.info("catalog fetch failed (%s): %s", type(exc).__name__, exc)
            return None
        if response.status_code != 200:
            log.warning("catalog fetch status=%d url=%s", response.status_code, url)
            return None
        try:
            return SchemaProductCatalog.model_validate_json(response.text)
        except (json.JSONDecodeError, ValidationError) as exc:
            log.info("catalog parse error (%s): %s", type(exc).__name__, exc)
            return None


class SchemaSync:
    """Orchestrates a single schema catalog sync run.

    Args:
        client: GitHubProductCatalogClient (or test subclass).
        registry: ProductRegistry to receive the cached catalog.
    """

    def __init__(
        self, *, client: GitHubProductCatalogClient, registry: ProductRegistry
    ) -> None:
        """See class docstring."""
        self._client = client
        self._registry = registry

    def run(self, *, repo: str, branch: str, path: str) -> SchemaSyncReport:
        """Fetch the catalog, cache it, and return a typed report.

        Args:
            repo: GitHub owner/name slug (already validated by caller).
            branch: GitHub branch name.
            path: Path to the catalog within the repo.

        Returns:
            SchemaSyncReport with outcome "ok" or "fetch-failed".
        """
        wire = self._client.fetch_catalog(repo, branch, path)
        if wire is None:
            return SchemaSyncReport(
                outcome="fetch-failed",
                cached=None,
                reason="Fetch failed (see log for details).",
            )
        source = SchemaSyncSource(repo=repo, branch=branch, path=path)
        try:
            cached = self._registry.save_catalog(wire, source)
        except OSError as exc:
            return SchemaSyncReport(
                outcome="fetch-failed",
                cached=None,
                reason=f"Cache write failed: {type(exc).__name__}",
            )
        return SchemaSyncReport(outcome="ok", cached=cached, reason=None)
