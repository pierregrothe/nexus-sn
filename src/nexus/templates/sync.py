# src/nexus/templates/sync.py
# GitHub raw template-manifest fetcher + sync orchestrator.
# Author: Pierre Grothe
# Date: 2026-05-18
"""GitHubTemplateClient + GitHubSync.

The client is a never-raises wrapper around a single anonymous GET to
``https://raw.githubusercontent.com/<repo>/<branch>/<path>``. It
mirrors the ``GitHubReleasesClient`` shape (optional ``httpx.Client``
injection for tests, ``info``/``warning`` logging, ``None`` on every
failure path).

The orchestrator wires the client + ``TemplateRegistry`` + the
``validate_github_repo`` guard and returns a typed ``SyncReport`` so
the command layer can render outcomes without try/except chains.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import httpx
from pydantic import ValidationError

from nexus.templates.errors import InvalidGitHubRepoError
from nexus.templates.models import SyncSource, TemplateManifest
from nexus.templates.repo_name import validate_github_repo

if TYPE_CHECKING:
    from nexus.templates.models import CachedManifest
    from nexus.templates.registry import TemplateRegistry

log = logging.getLogger(__name__)

__all__ = ["GitHubSync", "GitHubTemplateClient", "SyncReport"]

_DEFAULT_TIMEOUT_SECONDS = 10.0
_OutcomeT = Literal["ok", "no-config", "invalid-repo", "fetch-failed"]


class GitHubTemplateClient:
    """Anonymous fetcher for a raw GitHub manifest file.

    Args:
        httpx_client: Optional pre-built httpx.Client. Tests pass one
            backed by ``httpx.MockTransport``. Production callers omit
            it; a default client is built per ``fetch_manifest`` call.
        timeout_seconds: HTTP timeout for the default client. Ignored
            when ``httpx_client`` is supplied.
    """

    def __init__(
        self,
        *,
        httpx_client: httpx.Client | None = None,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """See class docstring."""
        self._injected_client = httpx_client
        self._timeout = timeout_seconds

    def fetch_manifest(self, repo: str, branch: str, path: str) -> TemplateManifest | None:
        """GET the raw manifest. Returns None on any failure.

        Args:
            repo: Canonical ``<owner>/<name>`` slug (caller validates).
            branch: GitHub branch name (e.g. ``"main"``).
            path: Path to the manifest within the repo (e.g.
                ``"templates/manifest.json"``).

        Returns:
            Parsed ``TemplateManifest`` on HTTP 200 with valid JSON and
            schema; ``None`` on network error, non-200 (incl. 429
            rate-limit), malformed JSON, or Pydantic schema mismatch.
            Every failure path logs a reason.
        """
        url = f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
        try:
            if self._injected_client is not None:
                response = self._injected_client.get(url)
            else:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.get(url)
        except httpx.HTTPError as exc:
            log.info("template manifest fetch failed (%s): %s", type(exc).__name__, exc)
            return None
        if response.status_code == 429:
            log.warning("template manifest fetch hit rate limit (status=429): %s", url)
            return None
        if response.status_code != 200:
            log.warning(
                "template manifest fetch returned status=%d url=%s",
                response.status_code,
                url,
            )
            return None
        try:
            payload = response.text
            return TemplateManifest.model_validate_json(payload)
        except json.JSONDecodeError as exc:
            log.info("template manifest invalid JSON: %s", exc)
            return None
        except ValidationError as exc:
            first = exc.errors()[0] if exc.errors() else {"loc": (), "type": "unknown"}
            loc_parts = first.get("loc", ()) or ()
            loc = ".".join(str(p) for p in loc_parts) or "(root)"
            log.info("template manifest schema mismatch at %s: %s", loc, first.get("type"))
            return None


@dataclass(frozen=True, slots=True)
class SyncReport:
    """Typed result of a single ``GitHubSync.run`` call.

    Attributes:
        outcome: One of ``"ok"``, ``"no-config"``, ``"invalid-repo"``,
            ``"fetch-failed"``.
        manifest: The persisted ``CachedManifest`` when ``outcome ==
            "ok"``, else ``None``.
        reason: One-line user-facing description of the failure when
            ``outcome != "ok"``, else ``None``.
    """

    outcome: _OutcomeT
    manifest: CachedManifest | None
    reason: str | None


class GitHubSync:
    """Orchestrates a single sync run.

    Args:
        client: ``GitHubTemplateClient`` (or test subclass).
        registry: ``TemplateRegistry`` to receive the cached manifest.
    """

    def __init__(self, *, client: GitHubTemplateClient, registry: TemplateRegistry) -> None:
        """See class docstring."""
        self._client = client
        self._registry = registry

    def run(self, *, repo: str, branch: str, path: str) -> SyncReport:
        """Validate config, fetch the manifest, persist the cache.

        Args:
            repo: ``github_repo`` from config (may be empty or
                malformed; validated here).
            branch: ``github_branch`` from config.
            path: Path to the manifest within the repo. Caller may set
                this from a future ``github_manifest_path`` config
                field; defaults are managed at the command layer.

        Returns:
            ``SyncReport`` with the outcome. The cache is only written
            on ``"ok"``; any prior cache is preserved on every other
            outcome.
        """
        if not repo.strip():
            return SyncReport(
                outcome="no-config",
                manifest=None,
                reason="Template registry not configured.",
            )
        try:
            canonical = validate_github_repo(repo)
        except InvalidGitHubRepoError as exc:
            return SyncReport(outcome="invalid-repo", manifest=None, reason=str(exc))
        wire = self._client.fetch_manifest(canonical, branch, path)
        if wire is None:
            return SyncReport(
                outcome="fetch-failed",
                manifest=None,
                reason="Fetch failed (see log output for details).",
            )
        source = SyncSource(repo=canonical, branch=branch, path=path)
        try:
            cached = self._registry.save_manifest(wire, source)
        except OSError as exc:
            return SyncReport(
                outcome="fetch-failed",
                manifest=None,
                reason=f"Cache write failed: {type(exc).__name__}",
            )
        return SyncReport(outcome="ok", manifest=cached, reason=None)
