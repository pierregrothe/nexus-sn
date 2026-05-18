# tests/test_templates_models.py
# Tests for nexus.templates.models -- wire + cached manifest split.
# Author: Pierre Grothe
# Date: 2026-05-18
"""Tests for TemplateEntry, TemplateManifest, SyncSource, CachedManifest."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from nexus.templates.models import (
    CachedManifest,
    SyncSource,
    TemplateEntry,
    TemplateManifest,
)


def test_template_manifest_parses_seed_payload() -> None:
    payload = '{"version": "1.0", "generated": "2026-05-07", "templates": []}'
    manifest = TemplateManifest.model_validate_json(payload)
    assert manifest.version == "1.0"
    assert manifest.generated == "2026-05-07"
    assert manifest.templates == ()


def test_template_entry_accepts_required_fields_and_optional_checksum() -> None:
    entry = TemplateEntry(
        name="incident-ai-agent",
        template_type="ai_agent",
        version="0.1.0",
        path="ai_agents/incident.yaml",
    )
    assert entry.checksum is None
    with_checksum = TemplateEntry(
        name="x", template_type="workflow", version="1.0", path="x.yaml", checksum="abc"
    )
    assert with_checksum.checksum == "abc"


def test_template_manifest_rejects_extra_fields() -> None:
    payload = (
        '{"version": "1.0", "generated": "2026-05-07", "templates": [], '
        '"cached_at": "2026-05-18T00:00:00+00:00"}'
    )
    with pytest.raises(ValidationError):
        TemplateManifest.model_validate_json(payload)


def test_template_manifest_template_type_field_replaces_type_keyword() -> None:
    entry = TemplateEntry(name="a", template_type="workflow", version="1.0", path="a.yaml")
    assert entry.template_type == "workflow"
    with pytest.raises(ValidationError):
        TemplateEntry.model_validate(
            {"name": "a", "type": "workflow", "version": "1.0", "path": "a.yaml"}
        )


def test_template_manifest_accepts_empty_templates_array() -> None:
    manifest = TemplateManifest(version="1.0", generated="2026-05-07", templates=())
    assert manifest.templates == ()


def test_cached_manifest_round_trips_json() -> None:
    wire = TemplateManifest(
        version="1.0",
        generated="2026-05-07",
        templates=(
            TemplateEntry(
                name="incident",
                template_type="ai_agent",
                version="0.1.0",
                path="ai_agents/incident.yaml",
            ),
        ),
    )
    source = SyncSource(repo="owner/name", branch="main", path="templates/manifest.json")
    cached = CachedManifest(
        wire=wire, source=source, cached_at=datetime(2026, 5, 18, 12, 0, tzinfo=UTC)
    )
    payload = cached.model_dump_json()
    restored = CachedManifest.model_validate_json(payload)
    assert restored == cached


def test_cached_manifest_requires_utc_aware_datetime() -> None:
    wire = TemplateManifest(version="1.0", generated="2026-05-07")
    source = SyncSource(repo="owner/name", branch="main", path="templates/manifest.json")
    with pytest.raises(ValidationError):
        CachedManifest(wire=wire, source=source, cached_at=datetime(2026, 5, 18, 12, 0))


def test_template_manifest_with_one_entry_parses() -> None:
    payload = (
        '{"version": "1.0", "generated": "2026-05-07", "templates": ['
        '{"name": "wf-1", "template_type": "workflow", "version": "0.1.0",'
        ' "path": "workflows/wf1.yaml"}]}'
    )
    manifest = TemplateManifest.model_validate_json(payload)
    assert len(manifest.templates) == 1
    assert manifest.templates[0].name == "wf-1"


def test_sync_source_is_frozen() -> None:
    source = SyncSource(repo="owner/name", branch="main", path="templates/manifest.json")
    with pytest.raises(ValidationError):
        source.__pydantic_validator__.validate_python(  # type-checked frozen
            {"repo": "x"}, self_instance=source
        )
