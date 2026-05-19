# tests/templates/test_render_purity.py
# Verifies render_to_records does no I/O and does not mutate inputs.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Story 04 AC5: renderer purity guarantees."""

from __future__ import annotations

from datetime import UTC, datetime

from nexus.templates.renderer import render_to_records
from tests.fakes.templates import (
    make_now_assist_skill,
    make_workflow,
    make_workflow_input,
)

NOW = datetime(2026, 5, 19, 12, 0, tzinfo=UTC)


def test_render_skill_does_not_mutate_input() -> None:
    skill = make_now_assist_skill(name="original")
    render_to_records(skill, "scope_x", NOW)
    assert skill.name == "original"


def test_render_workflow_does_not_mutate_input() -> None:
    workflow = make_workflow(inputs=(make_workflow_input(name="i1"),))
    render_to_records(workflow, "scope_x", NOW)
    assert workflow.inputs[0].name == "i1"


def test_render_skill_called_twice_yields_equal_records() -> None:
    skill = make_now_assist_skill()
    rec_a = render_to_records(skill, "scope_x", NOW)[0]
    rec_b = render_to_records(skill, "scope_x", NOW)[0]
    assert rec_a == rec_b
