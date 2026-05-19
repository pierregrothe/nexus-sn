# tests/templates/test_render_skill.py
# Tests for render_to_records on NowAssistSkill inputs.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Story 04 AC2, AC4, AC8: NowAssistSkill -> 1 ConfigRecord renderer."""

from __future__ import annotations

from datetime import UTC, datetime

from nexus.templates.renderer import render_to_records
from tests.fakes.templates import make_now_assist_skill

NOW = datetime(2026, 5, 19, 12, 0, tzinfo=UTC)


def test_render_skill_returns_one_record() -> None:
    skill = make_now_assist_skill()
    records = render_to_records(skill, scope_sys_id="scope_x", captured_at=NOW)
    assert len(records) == 1


def test_render_skill_targets_ai_skill_table() -> None:
    skill = make_now_assist_skill()
    records = render_to_records(skill, "scope_x", NOW)
    assert records[0].table == "ai_skill"


def test_render_skill_propagates_scope_sys_id() -> None:
    skill = make_now_assist_skill()
    records = render_to_records(skill, "scope_x", NOW)
    assert records[0].scope_sys_id == "scope_x"


def test_render_skill_uses_target_scope_as_scope_name() -> None:
    skill = make_now_assist_skill(target_scope="x_my_app")
    records = render_to_records(skill, "scope_x", NOW)
    assert records[0].scope_name == "x_my_app"


def test_render_skill_writes_fields_to_record() -> None:
    skill = make_now_assist_skill(name="Triage", description="desc", instructions="prompt")
    record = render_to_records(skill, "scope_x", NOW)[0]
    assert record.fields["name"] == "Triage"
    assert record.fields["short_description"] == "desc"
    assert record.fields["instructions"] == "prompt"


def test_render_skill_active_true_serializes_to_string() -> None:
    skill = make_now_assist_skill(active=True)
    record = render_to_records(skill, "scope_x", NOW)[0]
    assert record.fields["active"] == "true"


def test_render_skill_active_false_serializes_to_string() -> None:
    skill = make_now_assist_skill(active=False)
    record = render_to_records(skill, "scope_x", NOW)[0]
    assert record.fields["active"] == "false"


def test_render_skill_sys_id_is_deterministic() -> None:
    skill = make_now_assist_skill()
    rec_a = render_to_records(skill, "scope_x", NOW)[0]
    rec_b = render_to_records(skill, "scope_x", NOW)[0]
    assert rec_a.sys_id == rec_b.sys_id


def test_render_skill_sys_id_differs_across_template_id() -> None:
    skill_a = make_now_assist_skill(template_id="alpha")
    skill_b = make_now_assist_skill(template_id="beta")
    sys_a = render_to_records(skill_a, "scope_x", NOW)[0].sys_id
    sys_b = render_to_records(skill_b, "scope_x", NOW)[0].sys_id
    assert sys_a != sys_b


def test_render_skill_sys_id_is_32_hex_chars() -> None:
    skill = make_now_assist_skill()
    record = render_to_records(skill, "scope_x", NOW)[0]
    assert len(record.sys_id) == 32
    int(record.sys_id, 16)  # all hex chars


def test_render_skill_has_no_parent_sys_id() -> None:
    skill = make_now_assist_skill()
    record = render_to_records(skill, "scope_x", NOW)[0]
    assert record.parent_sys_id is None


def test_render_skill_captured_at_propagates() -> None:
    skill = make_now_assist_skill()
    record = render_to_records(skill, "scope_x", NOW)[0]
    assert record.captured_at == NOW
