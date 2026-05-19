# src/nexus/templates/renderer.py
# Pure renderer: TemplateDocument -> tuple[ConfigRecord, ...].
# Author: Pierre Grothe
# Date: 2026-05-19

"""Render a parsed TemplateDocument into the records UpdateSetWriter consumes.

`render_to_records` is a pure function -- no I/O, no env lookups (env-var
resolution already happened at TemplateDocument parse time). It is the
boundary between the schema layer (Pydantic Skill/Workflow) and the
update-set layer (ConfigRecord tuples on AI_AUTOMATION tables).

Sys_id generation is deterministic: a SHA-256 hash of
`(template_id, version, role[, child_name])` truncated to 32 hex chars
(ServiceNow's sys_id format). Same template rendered twice produces the
same sys_ids -- INSERT_OR_UPDATE then noops in target state.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from nexus.capture.models import ConfigRecord, SnFieldValue
from nexus.templates.document import TemplateDocument
from nexus.templates.schemas.now_assist_skill import NowAssistSkill
from nexus.templates.schemas.workflow import Workflow

__all__ = ["render_to_records"]


def render_to_records(
    document: TemplateDocument, scope_sys_id: str, captured_at: datetime
) -> tuple[ConfigRecord, ...]:
    """Render a TemplateDocument into ServiceNow ConfigRecord(s).

    Args:
        document: Parsed `NowAssistSkill` or `Workflow` instance.
        scope_sys_id: Resolved sys_id of the target scope. Caller resolves
            the slug to a sys_id before invoking the renderer.
        captured_at: Timestamp stamped on every produced ConfigRecord.

    Returns:
        Tuple of ConfigRecords. NowAssistSkill -> 1 record (ai_skill).
        Workflow -> parent + N inputs + M logic records, all sharing the
        same scope_sys_id and the parent's sys_id as parent_sys_id on
        the children.
    """
    match document:
        case NowAssistSkill():
            return (_render_skill(document, scope_sys_id, captured_at),)
        case Workflow():
            return _render_workflow(document, scope_sys_id, captured_at)
        case _:  # pragma: no cover -- exhaustive over TemplateDocument
            raise AssertionError(f"unreachable kind: {document!r}")


def _render_skill(skill: NowAssistSkill, scope_sys_id: str, captured_at: datetime) -> ConfigRecord:
    """Render a NowAssistSkill to one ai_skill ConfigRecord."""
    fields: dict[str, SnFieldValue] = {
        "name": skill.name,
        "short_description": skill.description,
        "instructions": skill.instructions,
        "active": _bool_field(skill.active),
    }
    return ConfigRecord(
        sys_id=_stable_sys_id(skill.id, skill.version, "skill"),
        table="ai_skill",
        scope_sys_id=scope_sys_id,
        scope_name=skill.target_scope,
        captured_at=captured_at,
        fields=fields,
        parent_sys_id=None,
    )


def _render_workflow(
    workflow: Workflow, scope_sys_id: str, captured_at: datetime
) -> tuple[ConfigRecord, ...]:
    """Render a Workflow to parent + child ConfigRecords."""
    parent_sys_id = _stable_sys_id(workflow.id, workflow.version, "flow")
    parent_fields: dict[str, SnFieldValue] = {
        "name": workflow.name,
        "description": workflow.description,
        "active": _bool_field(workflow.active),
    }
    parent = ConfigRecord(
        sys_id=parent_sys_id,
        table="sys_hub_flow",
        scope_sys_id=scope_sys_id,
        scope_name=workflow.target_scope,
        captured_at=captured_at,
        fields=parent_fields,
        parent_sys_id=None,
    )
    children: list[ConfigRecord] = []
    for inp in workflow.inputs:
        children.append(
            ConfigRecord(
                sys_id=_stable_sys_id(workflow.id, workflow.version, "input", inp.name),
                table="sys_hub_flow_input",
                scope_sys_id=scope_sys_id,
                scope_name=workflow.target_scope,
                captured_at=captured_at,
                fields=_render_input_fields(inp.name, inp.type, inp.required, inp.default),
                parent_sys_id=parent_sys_id,
            )
        )
    for step in workflow.logic:
        children.append(
            ConfigRecord(
                sys_id=_stable_sys_id(workflow.id, workflow.version, "logic", step.name),
                table="sys_hub_flow_logic",
                scope_sys_id=scope_sys_id,
                scope_name=workflow.target_scope,
                captured_at=captured_at,
                fields=_render_logic_fields(step.name, step.action, step.inputs),
                parent_sys_id=parent_sys_id,
            )
        )
    return (parent, *children)


def _render_input_fields(
    name: str, input_type: str, required: bool, default: str | None
) -> dict[str, SnFieldValue]:
    """Build the SnRecord for a sys_hub_flow_input child."""
    fields: dict[str, SnFieldValue] = {
        "name": name,
        "type": input_type,
        "mandatory": _bool_field(required),
    }
    if default is not None:
        fields["default_value"] = default
    return fields


def _render_logic_fields(name: str, action: str, inputs: dict[str, str]) -> dict[str, SnFieldValue]:
    """Build the SnRecord for a sys_hub_flow_logic child.

    The action's input map is serialized to a JSON-style string and
    stored on a single column; the exact column name varies by SN
    version. v1 picks `inputs_json` as a stable target; future epics
    refine against live-instance shape.
    """
    fields: dict[str, SnFieldValue] = {
        "name": name,
        "action": action,
    }
    if inputs:
        serialized = ", ".join(f"{key}={value}" for key, value in sorted(inputs.items()))
        fields["inputs_serialized"] = serialized
    return fields


def _stable_sys_id(template_id: str, version: str, role: str, *parts: str) -> str:
    """Deterministic sys_id from `(template_id, version, role[, parts...])`."""
    seed = ":".join([template_id, version, role, *parts])
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]


def _bool_field(value: bool) -> str:
    """Serialize a bool to ServiceNow's `"true"` / `"false"` string convention."""
    return "true" if value else "false"
