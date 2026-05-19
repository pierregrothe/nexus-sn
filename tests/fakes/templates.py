# tests/fakes/templates.py
# Builder helpers for template fixtures.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Construct NowAssistSkill / Workflow / TemplateDocument instances for tests.

Builders assume any `{{ env.X }}` references in their inputs have been
pre-resolved (or env vars set via monkeypatch.setenv) -- the schemas
run the env validator at construction time.
"""

from __future__ import annotations

from datetime import UTC, datetime

from nexus.assessment.context import ApplyResult
from nexus.templates.schemas.now_assist_skill import NowAssistSkill
from nexus.templates.schemas.workflow import Workflow, WorkflowInput, WorkflowLogic

__all__ = [
    "make_apply_result",
    "make_now_assist_skill",
    "make_workflow",
    "make_workflow_input",
    "make_workflow_logic",
]


def make_apply_result(
    *,
    update_set_sys_id: str = "us-1",
    update_set_name: str = "NEXUS-apply-sample-20260519T120000Z",
    template_id: str = "sample-skill",
    template_version: str = "1.0.0",
    target_scope_sys_id: str = "global",
    instance_id: str = "dev",
) -> ApplyResult:
    """Build a populated ApplyResult for tests."""
    now = datetime(2026, 5, 19, 12, 0, tzinfo=UTC)
    return ApplyResult(
        update_set_sys_id=update_set_sys_id,
        update_set_name=update_set_name,
        template_id=template_id,
        template_version=template_version,
        target_scope_sys_id=target_scope_sys_id,
        applied_records=(),
        instance_id=instance_id,
        started_at=now,
        completed_at=now,
    )


def make_now_assist_skill(
    *,
    template_id: str = "sample-skill",
    version: str = "1.0.0",
    target_scope: str = "global",
    name: str = "Sample Skill",
    description: str = "",
    instructions: str = "Do the thing.",
    active: bool = True,
) -> NowAssistSkill:
    """Build a minimal NowAssistSkill with sensible defaults."""
    return NowAssistSkill(
        id=template_id,
        version=version,
        target_scope=target_scope,
        name=name,
        description=description,
        instructions=instructions,
        active=active,
    )


def make_workflow_input(
    *,
    name: str = "input_1",
    type_: str = "string",
    required: bool = False,
    default: str | None = None,
) -> WorkflowInput:
    """Build a WorkflowInput child row."""
    return WorkflowInput(name=name, type=type_, required=required, default=default)


def make_workflow_logic(
    *,
    name: str = "step_1",
    action: str = "rest_step",
    inputs: dict[str, str] | None = None,
) -> WorkflowLogic:
    """Build a WorkflowLogic child row."""
    return WorkflowLogic(name=name, action=action, inputs=inputs or {})


def make_workflow(
    *,
    template_id: str = "sample-workflow",
    version: str = "1.0.0",
    target_scope: str = "global",
    name: str = "Sample Workflow",
    description: str = "",
    active: bool = True,
    inputs: tuple[WorkflowInput, ...] = (),
    logic: tuple[WorkflowLogic, ...] = (),
) -> Workflow:
    """Build a minimal Workflow with sensible defaults."""
    return Workflow(
        id=template_id,
        version=version,
        target_scope=target_scope,
        name=name,
        description=description,
        active=active,
        inputs=inputs,
        logic=logic,
    )
