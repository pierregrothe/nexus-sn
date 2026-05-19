# tests/templates/test_apply_engine.py
# Tests for ApplyEngine end-to-end + scope resolution + provenance + jsonl.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Story 05 AC1-AC12: ApplyEngine orchestration."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from nexus.assessment.context import ApplyResult
from nexus.config.paths import NexusPaths
from nexus.templates.apply import ApplyEngine
from nexus.templates.errors import ScopeNotFoundError
from nexus.templates.results import AppliedAction
from tests.fakes.fake_sn_client import FakeServiceNowClient

_NOW = datetime(2026, 5, 19, 12, 0, tzinfo=UTC)


def _clock() -> datetime:
    return _NOW


def _skill_yaml(template_id: str = "sample-skill", target_scope: str = "global") -> str:
    return f"""
kind: now_assist_skill
id: {template_id}
version: "1.0.0"
target_scope: {target_scope}
name: Sample Skill
description: ""
instructions: Do the thing.
active: true
"""


def _workflow_yaml() -> str:
    return """
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


def _engine(tmp_path: Path, sn_client: FakeServiceNowClient) -> ApplyEngine:
    return ApplyEngine(
        sn_client=sn_client,
        paths=NexusPaths(root=tmp_path),
        clock=_clock,
        instance_id="dev",
        nexus_version="0.0.test",
        git_sha="abc123",
    )


def _write_template(tmp_path: Path, name: str, yaml_text: str) -> Path:
    path = tmp_path / name
    path.write_text(yaml_text, encoding="utf-8")
    return path


def test_apply_engine_skill_returns_apply_result(tmp_path: Path) -> None:
    template_path = _write_template(tmp_path, "skill.yaml", _skill_yaml())
    client = FakeServiceNowClient()
    engine = _engine(tmp_path, client)

    result = asyncio.run(engine.apply(template_path))

    assert isinstance(result, ApplyResult)
    assert result.template_id == "sample-skill"
    assert result.template_version == "1.0.0"
    assert result.target_scope_sys_id == "global"
    assert result.instance_id == "dev"
    assert result.started_at == _NOW
    assert result.completed_at == _NOW


def test_apply_engine_creates_sys_update_set_with_provenance(tmp_path: Path) -> None:
    template_path = _write_template(tmp_path, "skill.yaml", _skill_yaml())
    client = FakeServiceNowClient()
    engine = _engine(tmp_path, client)

    asyncio.run(engine.apply(template_path))

    update_sets = client._tables.get("sys_update_set", [])
    assert len(update_sets) == 1
    update_set = update_sets[0]
    assert update_set["name"].startswith("NEXUS-apply-sample-skill-")
    description = json.loads(str(update_set["description"]))
    assert description == {
        "nexus": {
            "template_id": "sample-skill",
            "template_version": "1.0.0",
            "nexus_version": "0.0.test",
            "git_sha": "abc123",
            "applied_at": _NOW.isoformat(),
        }
    }


def test_apply_engine_emits_one_applied_record_for_skill(tmp_path: Path) -> None:
    template_path = _write_template(tmp_path, "skill.yaml", _skill_yaml())
    client = FakeServiceNowClient()
    engine = _engine(tmp_path, client)

    result = asyncio.run(engine.apply(template_path))

    assert len(result.applied_records) == 1
    applied = result.applied_records[0]
    assert applied.table == "ai_skill"
    assert applied.name == "Sample Skill"
    assert applied.action == AppliedAction.REQUESTED
    assert applied.error_message is None


def test_apply_engine_resolves_global_scope_without_query(tmp_path: Path) -> None:
    template_path = _write_template(tmp_path, "skill.yaml", _skill_yaml())
    client = FakeServiceNowClient()
    engine = _engine(tmp_path, client)
    result = asyncio.run(engine.apply(template_path))
    assert result.target_scope_sys_id == "global"
    # sys_scope table was never queried successfully -- no records created there
    assert client._tables.get("sys_scope", []) == []


def test_apply_engine_resolves_non_global_scope_via_query(tmp_path: Path) -> None:
    template_path = _write_template(tmp_path, "skill.yaml", _skill_yaml(target_scope="x_my_app"))
    client = FakeServiceNowClient(
        initial_records={"sys_scope": [{"sys_id": "scope-abc", "scope": "x_my_app"}]}
    )
    engine = _engine(tmp_path, client)

    result = asyncio.run(engine.apply(template_path))
    assert result.target_scope_sys_id == "scope-abc"


def test_apply_engine_unknown_scope_raises_scope_not_found(tmp_path: Path) -> None:
    template_path = _write_template(
        tmp_path, "skill.yaml", _skill_yaml(target_scope="x_does_not_exist")
    )
    client = FakeServiceNowClient()
    engine = _engine(tmp_path, client)

    with pytest.raises(ScopeNotFoundError):
        asyncio.run(engine.apply(template_path))


def test_apply_engine_pushes_workflow_parent_plus_children(tmp_path: Path) -> None:
    template_path = _write_template(tmp_path, "workflow.yaml", _workflow_yaml())
    client = FakeServiceNowClient()
    engine = _engine(tmp_path, client)
    result = asyncio.run(engine.apply(template_path))

    assert len(result.applied_records) == 3  # parent + 1 input + 1 logic
    tables = [rec.table for rec in result.applied_records]
    assert "sys_hub_flow" in tables
    assert "sys_hub_flow_input" in tables
    assert "sys_hub_flow_logic" in tables


def test_apply_engine_writes_apply_jsonl(tmp_path: Path) -> None:
    template_path = _write_template(tmp_path, "skill.yaml", _skill_yaml())
    client = FakeServiceNowClient()
    engine = _engine(tmp_path, client)
    result = asyncio.run(engine.apply(template_path))

    jsonl_path = NexusPaths(root=tmp_path).jobs_dir / result.update_set_sys_id / "apply.jsonl"
    assert jsonl_path.exists()
    line = jsonl_path.read_text(encoding="utf-8").strip()
    parsed = json.loads(line)
    assert parsed["template_id"] == "sample-skill"
    assert parsed["template_version"] == "1.0.0"


def test_apply_engine_invokes_update_set_with_marker_name(tmp_path: Path) -> None:
    template_path = _write_template(tmp_path, "skill.yaml", _skill_yaml())
    client = FakeServiceNowClient()
    engine = _engine(tmp_path, client)
    result = asyncio.run(engine.apply(template_path))

    assert result.update_set_name.startswith("NEXUS-apply-sample-skill-")
    assert "T120000Z" in result.update_set_name


def test_apply_engine_writes_records_to_sys_update_xml(tmp_path: Path) -> None:
    template_path = _write_template(tmp_path, "skill.yaml", _skill_yaml())
    client = FakeServiceNowClient()
    engine = _engine(tmp_path, client)
    asyncio.run(engine.apply(template_path))

    # UpdateSetWriter creates one sys_update_xml row per rendered record
    update_xml = client._tables.get("sys_update_xml", [])
    assert len(update_xml) == 1
    assert update_xml[0]["type"] == "ai_skill"
    assert update_xml[0]["action"] == "INSERT_OR_UPDATE"


def test_apply_engine_apply_result_is_frozen(tmp_path: Path) -> None:
    template_path = _write_template(tmp_path, "skill.yaml", _skill_yaml())
    client = FakeServiceNowClient()
    engine = _engine(tmp_path, client)
    result = asyncio.run(engine.apply(template_path))

    with pytest.raises(ValidationError):
        result.template_id = "other"


def test_apply_engine_scope_resolution_failure_when_query_returns_empty_sys_id(
    tmp_path: Path,
) -> None:
    template_path = _write_template(tmp_path, "skill.yaml", _skill_yaml(target_scope="x_my_app"))
    client = FakeServiceNowClient(
        initial_records={"sys_scope": [{"sys_id": "", "scope": "x_my_app"}]}
    )
    engine = _engine(tmp_path, client)
    with pytest.raises(ScopeNotFoundError):
        asyncio.run(engine.apply(template_path))
