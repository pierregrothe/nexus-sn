# tests/templates/test_render_workflow.py
# Tests for render_to_records on Workflow inputs.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Story 04 AC3, AC6, AC7: Workflow -> parent + children renderer."""

from __future__ import annotations

from datetime import UTC, datetime

from nexus.templates.renderer import render_to_records
from tests.fakes.templates import (
    make_workflow,
    make_workflow_input,
    make_workflow_logic,
)

NOW = datetime(2026, 5, 19, 12, 0, tzinfo=UTC)


def test_render_workflow_with_no_children_returns_one_record() -> None:
    workflow = make_workflow()
    records = render_to_records(workflow, "scope_x", NOW)
    assert len(records) == 1
    assert records[0].table == "sys_hub_flow"
    assert records[0].parent_sys_id is None


def test_render_workflow_with_inputs_produces_child_records() -> None:
    workflow = make_workflow(
        inputs=(
            make_workflow_input(name="request_id", type_="string"),
            make_workflow_input(name="approver", type_="reference"),
        )
    )
    records = render_to_records(workflow, "scope_x", NOW)
    assert len(records) == 3
    assert records[0].table == "sys_hub_flow"
    assert records[1].table == "sys_hub_flow_input"
    assert records[2].table == "sys_hub_flow_input"


def test_render_workflow_inputs_carry_parent_sys_id() -> None:
    workflow = make_workflow(inputs=(make_workflow_input(name="i1"),))
    records = render_to_records(workflow, "scope_x", NOW)
    parent, child = records
    assert child.parent_sys_id == parent.sys_id


def test_render_workflow_logic_steps_produce_records() -> None:
    workflow = make_workflow(
        logic=(
            make_workflow_logic(name="step_a", action="rest_step"),
            make_workflow_logic(name="step_b", action="notification", inputs={"to": "user@x"}),
        )
    )
    records = render_to_records(workflow, "scope_x", NOW)
    assert len(records) == 3
    assert records[0].table == "sys_hub_flow"
    assert records[1].table == "sys_hub_flow_logic"
    assert records[2].table == "sys_hub_flow_logic"
    assert records[2].fields["action"] == "notification"
    assert records[2].fields["inputs_serialized"] == "to=user@x"


def test_render_workflow_logic_no_inputs_omits_serialized_field() -> None:
    workflow = make_workflow(logic=(make_workflow_logic(name="step_a", action="rest_step"),))
    records = render_to_records(workflow, "scope_x", NOW)
    assert "inputs_serialized" not in records[1].fields


def test_render_workflow_input_with_default_includes_default_value() -> None:
    workflow = make_workflow(inputs=(make_workflow_input(name="i1", default="42"),))
    records = render_to_records(workflow, "scope_x", NOW)
    assert records[1].fields["default_value"] == "42"


def test_render_workflow_input_without_default_omits_field() -> None:
    workflow = make_workflow(inputs=(make_workflow_input(name="i1"),))
    records = render_to_records(workflow, "scope_x", NOW)
    assert "default_value" not in records[1].fields


def test_render_workflow_scope_propagates_to_all_records() -> None:
    workflow = make_workflow(
        target_scope="x_app",
        inputs=(make_workflow_input(name="i1"),),
        logic=(make_workflow_logic(name="step_a"),),
    )
    records = render_to_records(workflow, "scope_x", NOW)
    for record in records:
        assert record.scope_sys_id == "scope_x"
        assert record.scope_name == "x_app"


def test_render_workflow_sys_ids_are_deterministic() -> None:
    workflow = make_workflow(
        inputs=(make_workflow_input(name="i1"),),
        logic=(make_workflow_logic(name="step_a"),),
    )
    first = render_to_records(workflow, "scope_x", NOW)
    second = render_to_records(workflow, "scope_x", NOW)
    for rec_a, rec_b in zip(first, second, strict=True):
        assert rec_a.sys_id == rec_b.sys_id


def test_render_workflow_child_sys_ids_differ_from_parent() -> None:
    workflow = make_workflow(
        inputs=(make_workflow_input(name="i1"),),
        logic=(make_workflow_logic(name="step_a"),),
    )
    records = render_to_records(workflow, "scope_x", NOW)
    sys_ids = {record.sys_id for record in records}
    assert len(sys_ids) == 3  # all different
