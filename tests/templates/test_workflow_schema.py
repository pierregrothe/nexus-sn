# tests/templates/test_workflow_schema.py
# Schema-level tests for Workflow, WorkflowInput, WorkflowLogic.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Story 02 AC1-AC3, AC6, AC7, AC9: Workflow + child Pydantic surface."""

from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from nexus.templates.schemas.workflow import Workflow, WorkflowInput, WorkflowLogic
from tests.fakes.templates import (
    make_workflow,
    make_workflow_input,
    make_workflow_logic,
)


def test_workflow_constructs_with_minimum_fields() -> None:
    wf = make_workflow()
    assert wf.kind == "workflow"
    assert wf.id == "sample-workflow"
    assert wf.target_scope == "global"
    assert wf.active is True
    assert wf.inputs == ()
    assert wf.logic == ()


def test_workflow_rejects_empty_id() -> None:
    with pytest.raises(ValidationError):
        Workflow(id="", version="1.0", name="x")


def test_workflow_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        Workflow(id="x", version="1.0", name="")


def test_workflow_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        Workflow.model_validate(
            {
                "id": "x",
                "version": "1.0",
                "name": "x",
                "garbage_field": True,
            }
        )


def test_workflow_is_frozen() -> None:
    wf = make_workflow()
    with pytest.raises(ValidationError):
        wf.name = "different"


def test_workflow_kind_is_literal_workflow() -> None:
    wf = make_workflow()
    assert wf.kind == "workflow"


def test_workflow_with_inputs_and_logic() -> None:
    wf = make_workflow(
        inputs=(make_workflow_input(name="i1"), make_workflow_input(name="i2")),
        logic=(make_workflow_logic(name="step_a"),),
    )
    assert len(wf.inputs) == 2
    assert len(wf.logic) == 1
    assert wf.inputs[0].name == "i1"


def test_workflow_input_required_defaults_false() -> None:
    inp = WorkflowInput(name="x", type="string")
    assert inp.required is False
    assert inp.default is None


def test_workflow_input_with_default_value() -> None:
    inp = make_workflow_input(default="42")
    assert inp.default == "42"


def test_workflow_input_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        WorkflowInput(name="", type="string")


def test_workflow_input_rejects_empty_type() -> None:
    with pytest.raises(ValidationError):
        WorkflowInput(name="x", type="")


def test_workflow_input_is_frozen() -> None:
    inp = make_workflow_input()
    with pytest.raises(ValidationError):
        inp.name = "different"


def test_workflow_logic_defaults_empty_inputs() -> None:
    step = WorkflowLogic(name="s1", action="rest_step")
    assert step.inputs == {}


def test_workflow_logic_with_inputs() -> None:
    step = make_workflow_logic(inputs={"to": "user@example.com"})
    assert step.inputs == {"to": "user@example.com"}


def test_workflow_logic_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        WorkflowLogic(name="", action="rest_step")


def test_workflow_logic_rejects_empty_action() -> None:
    with pytest.raises(ValidationError):
        WorkflowLogic(name="x", action="")


def test_workflow_logic_is_frozen() -> None:
    step = make_workflow_logic()
    with pytest.raises(ValidationError):
        step.name = "different"


def test_workflow_round_trips_via_yaml() -> None:
    original = make_workflow(
        inputs=(make_workflow_input(name="i1", required=True),),
        logic=(make_workflow_logic(inputs={"to": "x@y"}),),
    )
    dumped = yaml.safe_dump(original.model_dump(mode="json"))
    re_loaded = Workflow.model_validate(yaml.safe_load(dumped), strict=False)
    assert re_loaded == original


def test_workflow_target_scope_defaults_global() -> None:
    wf = Workflow(id="x", version="1.0", name="x")
    assert wf.target_scope == "global"


def test_workflow_target_scope_override() -> None:
    wf = make_workflow(target_scope="x_my_app")
    assert wf.target_scope == "x_my_app"


def test_workflow_rejects_wrong_kind() -> None:
    with pytest.raises(ValidationError):
        Workflow.model_validate(
            {"kind": "now_assist_skill", "id": "x", "version": "1.0", "name": "x"}
        )
