# tests/templates/test_workflow_env_resolution.py
# env-var substitution tests for Workflow + children.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Story 02 AC4, AC5: env-var resolution at parse time for Workflow + nested."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from nexus.templates.schemas.workflow import Workflow, WorkflowInput, WorkflowLogic


def test_workflow_resolves_env_in_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WF_DESC", "Approval workflow")
    wf = Workflow(id="x", version="1.0", name="x", description="{{ env.WF_DESC }}")
    assert wf.description == "Approval workflow"


def test_workflow_resolves_env_in_target_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WF_SCOPE", "x_app")
    wf = Workflow(id="x", version="1.0", target_scope="{{ env.WF_SCOPE }}", name="x")
    assert wf.target_scope == "x_app"


def test_workflow_raises_validation_error_on_unset_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MISSING_WF_VAR", raising=False)
    with pytest.raises(ValidationError) as exc:
        Workflow(id="{{ env.MISSING_WF_VAR }}", version="1.0", name="x")
    assert "'MISSING_WF_VAR'" in str(exc.value)


def test_workflow_input_resolves_env_in_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INPUT_DEFAULT", "42")
    inp = WorkflowInput(name="x", type="string", default="{{ env.INPUT_DEFAULT }}")
    assert inp.default == "42"


def test_workflow_input_resolves_env_in_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INPUT_NAME", "request_sys_id")
    inp = WorkflowInput(name="{{ env.INPUT_NAME }}", type="string")
    assert inp.name == "request_sys_id"


def test_workflow_logic_resolves_env_in_inputs_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NOTIFY_TO", "ops@example.com")
    step = WorkflowLogic(
        name="notify",
        action="notification",
        inputs={"to": "{{ env.NOTIFY_TO }}"},
    )
    assert step.inputs == {"to": "ops@example.com"}


def test_workflow_logic_resolves_env_in_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ACTION_TYPE", "rest_step")
    step = WorkflowLogic(name="s", action="{{ env.ACTION_TYPE }}")
    assert step.action == "rest_step"


def test_workflow_logic_inputs_pass_through_non_dict() -> None:
    # malformed (non-dict) inputs caught by Pydantic later; helper passes through
    with pytest.raises(ValidationError):
        WorkflowLogic.model_validate({"name": "s", "action": "rest_step", "inputs": "not a dict"})


def test_workflow_logic_inputs_raises_on_unset_env_in_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MISSING_LOGIC_VAR", raising=False)
    with pytest.raises(ValidationError) as exc:
        WorkflowLogic(name="s", action="rest_step", inputs={"k": "{{ env.MISSING_LOGIC_VAR }}"})
    assert "'MISSING_LOGIC_VAR'" in str(exc.value)
