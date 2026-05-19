# tests/templates/test_shipped_templates.py
# Guard tests for templates/<id>/template.yaml + manifest.yaml.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Story 07 AC1-AC5, AC11, AC12: shipped-template parse + round-trip."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from nexus.templates.document import load_template_document

_REPO_TEMPLATES = Path(__file__).resolve().parents[2] / "templates"


def test_shipped_templates_parse_via_load_template_document() -> None:
    paths = sorted(_REPO_TEMPLATES.glob("*/template.yaml"))
    assert paths, "expected at least one template under templates/"
    for path in paths:
        doc = load_template_document(path)
        assert doc.id
        assert doc.version


def test_shipped_templates_round_trip_through_pydantic() -> None:
    for path in sorted(_REPO_TEMPLATES.glob("*/template.yaml")):
        doc = load_template_document(path)
        dumped = yaml.safe_dump(doc.model_dump(mode="json"))
        re_loaded_path = path.parent / "__round_trip__.yaml"
        re_loaded_path.write_text(dumped, encoding="utf-8")
        try:
            re_loaded = load_template_document(re_loaded_path)
        finally:
            re_loaded_path.unlink()
        assert re_loaded == doc


def test_each_shipped_template_has_manifest_yaml() -> None:
    for template_dir in sorted(_REPO_TEMPLATES.glob("*/template.yaml")):
        manifest = template_dir.parent / "manifest.yaml"
        assert manifest.exists(), f"missing manifest: {manifest}"


def test_manifest_json_lists_every_shipped_template() -> None:
    manifest_path = _REPO_TEMPLATES / "manifest.json"
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    listed_ids = {entry["id"] for entry in raw["templates"]}
    on_disk_ids = {p.parent.name for p in _REPO_TEMPLATES.glob("*/template.yaml")}
    assert listed_ids == on_disk_ids


def test_incident_triage_template_is_skill() -> None:
    path = _REPO_TEMPLATES / "nowassist-incident-triage" / "template.yaml"
    doc = load_template_document(path)
    assert doc.kind == "now_assist_skill"
    assert doc.id == "nowassist-incident-triage"


def test_approval_flow_template_is_workflow_with_children() -> None:
    path = _REPO_TEMPLATES / "simple-approval-flow" / "template.yaml"
    doc = load_template_document(path)
    assert doc.kind == "workflow"
    # Discriminated union narrows via assertion
    from nexus.templates.schemas.workflow import Workflow  # noqa: PLC0415

    assert isinstance(doc, Workflow)
    assert len(doc.inputs) >= 1
    assert len(doc.logic) >= 1
