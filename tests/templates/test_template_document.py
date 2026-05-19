# tests/templates/test_template_document.py
# Tests for TemplateDocument discriminated union + load_template_document.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Story 03 AC1-AC8: discriminator dispatch + YAML load."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from nexus.templates.document import load_template_document
from nexus.templates.errors import TemplateLoadError
from nexus.templates.schemas.now_assist_skill import NowAssistSkill
from nexus.templates.schemas.workflow import Workflow

_SKILL_YAML = """
kind: now_assist_skill
id: sample-skill
version: "1.0.0"
target_scope: global
name: Sample
description: ""
instructions: Do the thing.
active: true
"""

_WORKFLOW_YAML = """
kind: workflow
id: sample-flow
version: "1.0.0"
target_scope: global
name: Sample Flow
description: ""
active: true
inputs:
  - name: i1
    type: string
    required: false
logic:
  - name: step_a
    action: rest_step
    inputs:
      url: https://example.invalid
"""


def test_load_template_document_dispatches_skill(tmp_path: Path) -> None:
    path = tmp_path / "skill.yaml"
    path.write_text(_SKILL_YAML, encoding="utf-8")
    doc = load_template_document(path)
    assert isinstance(doc, NowAssistSkill)
    assert doc.id == "sample-skill"


def test_load_template_document_dispatches_workflow(tmp_path: Path) -> None:
    path = tmp_path / "workflow.yaml"
    path.write_text(_WORKFLOW_YAML, encoding="utf-8")
    doc = load_template_document(path)
    assert isinstance(doc, Workflow)
    assert doc.id == "sample-flow"
    assert len(doc.inputs) == 1
    assert len(doc.logic) == 1


def test_load_template_document_raises_on_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.yaml"
    with pytest.raises(TemplateLoadError) as exc_info:
        load_template_document(path)
    assert exc_info.value.path == path
    assert isinstance(exc_info.value.cause, OSError)


def test_load_template_document_raises_on_malformed_yaml(tmp_path: Path) -> None:
    path = tmp_path / "broken.yaml"
    path.write_text("kind: foo\n: missing-key\n[bad", encoding="utf-8")
    with pytest.raises(TemplateLoadError) as exc_info:
        load_template_document(path)
    assert isinstance(exc_info.value.cause, yaml.YAMLError)


def test_load_template_document_raises_on_unknown_kind(tmp_path: Path) -> None:
    path = tmp_path / "unknown.yaml"
    path.write_text(
        yaml.safe_dump({"kind": "ai_agent", "id": "x", "version": "1.0", "name": "x"}),
        encoding="utf-8",
    )
    with pytest.raises(TemplateLoadError) as exc_info:
        load_template_document(path)
    assert "ai_agent" in str(exc_info.value.cause)


def test_load_template_document_raises_on_schema_violation(tmp_path: Path) -> None:
    path = tmp_path / "invalid.yaml"
    # missing required `instructions` field
    path.write_text(
        yaml.safe_dump(
            {
                "kind": "now_assist_skill",
                "id": "x",
                "version": "1.0",
                "name": "x",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(TemplateLoadError):
        load_template_document(path)


def test_load_template_document_resolves_env_in_skill_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOC_NAME", "Resolved")
    path = tmp_path / "skill.yaml"
    path.write_text(
        """
kind: now_assist_skill
id: x
version: "1.0"
target_scope: global
name: "{{ env.DOC_NAME }}"
description: ""
instructions: Do the thing.
active: true
""",
        encoding="utf-8",
    )
    doc = load_template_document(path)
    assert isinstance(doc, NowAssistSkill)
    assert doc.name == "Resolved"


def test_load_template_document_round_trips_via_yaml(tmp_path: Path) -> None:
    path = tmp_path / "skill.yaml"
    path.write_text(_SKILL_YAML, encoding="utf-8")
    original = load_template_document(path)

    re_dumped_path = tmp_path / "round_trip.yaml"
    re_dumped_path.write_text(yaml.safe_dump(original.model_dump(mode="json")), encoding="utf-8")
    re_loaded = load_template_document(re_dumped_path)
    assert re_loaded == original


def test_template_load_error_str_contains_path_and_cause(tmp_path: Path) -> None:
    cause = ValueError("inner")
    err = TemplateLoadError(tmp_path / "x.yaml", cause)
    text = str(err)
    assert str(tmp_path / "x.yaml") in text
    assert "inner" in text
