# src/nexus/templates/models.py
# Pydantic models for the template catalog wire payload and on-disk cache.
# Author: Pierre Grothe
# Date: 2026-05-18
"""TemplateEntry, TemplateManifest, SyncSource, CachedManifest.

Two-model split avoids the round-trip break that would occur if a
single ``extra="forbid"`` model tried to carry both the wire payload
fields and the cache-only ``cached_at`` stamp:

* ``TemplateManifest`` -- the wire shape served from GitHub.
* ``CachedManifest`` -- wraps a ``TemplateManifest`` with the source
  it was fetched from and the UTC timestamp the cache was written.

``TemplateEntry`` describes one row in the manifest's ``templates``
array. Fields mirror the design spec
(``docs/superpowers/specs/2026-05-07-nexus-design.md``) except that
the Python attribute is ``template_type`` to avoid shadowing the
``type`` builtin; the wire alias remains ``template_type``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from nexus.config.types import UtcDatetime

__all__ = [
    "CachedManifest",
    "SyncSource",
    "TemplateEntry",
    "TemplateManifest",
]

_FROZEN = ConfigDict(frozen=True, strict=True, extra="forbid")


class TemplateEntry(BaseModel):
    """One row in a ``TemplateManifest.templates`` array.

    Attributes:
        name: Unique template name (e.g. ``"incident-ai-agent"``).
        template_type: Template category (e.g. ``"ai_agent"``,
            ``"workflow"``). Named to avoid the ``type`` keyword.
        version: Template version string (SemVer or CalVer at the
            template author's discretion).
        path: Relative path to the template YAML within the source
            repository (e.g. ``"ai_agents/incident.yaml"``).
        checksum: Optional content hash for tamper detection. ``None``
            when the manifest author has not computed one.
    """

    model_config = _FROZEN

    name: str
    template_type: str
    version: str
    path: str
    checksum: str | None = None


class TemplateManifest(BaseModel):
    """Wire shape of the catalog manifest served from GitHub.

    Attributes:
        version: Manifest schema version (e.g. ``"1.0"``).
        generated: ISO8601 timestamp string from the manifest author;
            preserved verbatim (not parsed to ``datetime`` because the
            author may use any timezone).
        templates: Tuple of ``TemplateEntry`` rows. Empty tuple is
            valid (a fresh registry with no templates yet).
    """

    model_config = _FROZEN

    version: str
    generated: str
    templates: tuple[TemplateEntry, ...] = ()


class SyncSource(BaseModel):
    """Record of where a cached manifest was fetched from.

    Attributes:
        repo: Canonical ``<owner>/<name>`` slug (post-validation).
        branch: GitHub branch the manifest was fetched from.
        path: Path to the manifest file within the repo.
    """

    model_config = _FROZEN

    repo: str
    branch: str
    path: str


class CachedManifest(BaseModel):
    """On-disk wrapper around a fetched ``TemplateManifest``.

    Persisted at ``~/.nexus/templates/manifest.json`` by
    ``TemplateRegistry.save_manifest``. Carries the wire payload, the
    source it was fetched from, and the UTC timestamp the cache was
    written.

    Attributes:
        wire: The ``TemplateManifest`` as received from GitHub.
        source: ``SyncSource`` describing repo/branch/path used.
        cached_at: UTC timestamp at which ``save_manifest`` ran.
    """

    model_config = _FROZEN

    wire: TemplateManifest
    source: SyncSource
    cached_at: UtcDatetime
