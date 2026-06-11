# src/nexus/schema/sync.py
# GitHub sync client and orchestrator for the schema product catalog.
# Author: Pierre Grothe
# Date: 2026-06-11
"""SchemaSyncSource, GitHubProductCatalogClient, SchemaSync."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

__all__ = [
    "SchemaSyncSource",
]

_CONFIG = ConfigDict(frozen=True, strict=True, extra="forbid")


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
