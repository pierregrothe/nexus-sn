# tests/templates/test_now_assist_skill_schema.py
# Schema-level tests for NowAssistSkill.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Story 01 AC1, AC6, AC7, AC9: NowAssistSkill Pydantic surface."""

from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from nexus.templates.schemas.now_assist_skill import NowAssistSkill
from tests.fakes.templates import make_now_assist_skill


def test_now_assist_skill_constructs_with_minimum_fields() -> None:
    skill = make_now_assist_skill()
    assert skill.kind == "now_assist_skill"
    assert skill.id == "sample-skill"
    assert skill.version == "1.0.0"
    assert skill.target_scope == "global"
    assert skill.active is True


def test_now_assist_skill_kind_is_literal() -> None:
    skill = make_now_assist_skill()
    assert skill.kind == "now_assist_skill"


def test_now_assist_skill_rejects_empty_id() -> None:
    with pytest.raises(ValidationError):
        NowAssistSkill(id="", version="1.0", name="x", instructions="x")


def test_now_assist_skill_rejects_empty_instructions() -> None:
    with pytest.raises(ValidationError):
        NowAssistSkill(id="x", version="1.0", name="x", instructions="")


def test_now_assist_skill_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        NowAssistSkill(id="x", version="1.0", name="", instructions="x")


def test_now_assist_skill_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        NowAssistSkill.model_validate(
            {
                "id": "x",
                "version": "1.0",
                "name": "x",
                "instructions": "x",
                "garbage_field": True,
            }
        )


def test_now_assist_skill_is_frozen() -> None:
    skill = make_now_assist_skill()
    with pytest.raises(ValidationError):
        skill.name = "different"


def test_now_assist_skill_rejects_wrong_kind() -> None:
    with pytest.raises(ValidationError):
        NowAssistSkill.model_validate(
            {
                "kind": "workflow",
                "id": "x",
                "version": "1.0",
                "name": "x",
                "instructions": "x",
            }
        )


def test_now_assist_skill_active_defaults_true() -> None:
    skill = make_now_assist_skill()
    assert skill.active is True


def test_now_assist_skill_active_can_be_false() -> None:
    skill = make_now_assist_skill(active=False)
    assert skill.active is False


def test_now_assist_skill_target_scope_defaults_global() -> None:
    skill = NowAssistSkill(id="x", version="1.0", name="x", instructions="x")
    assert skill.target_scope == "global"


def test_now_assist_skill_target_scope_can_be_overridden() -> None:
    skill = make_now_assist_skill(target_scope="x_my_app")
    assert skill.target_scope == "x_my_app"


def test_now_assist_skill_round_trips_via_yaml() -> None:
    original = make_now_assist_skill(name="Original", instructions="Do thing.")
    dumped = yaml.safe_dump(original.model_dump(mode="json"))
    re_loaded = NowAssistSkill.model_validate(yaml.safe_load(dumped), strict=False)
    assert re_loaded == original
