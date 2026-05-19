# src/nexus/templates/schemas/workflow.py
# Workflow Pydantic schema mapping to the SN sys_hub_flow table + children.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Workflow template document.

One YAML file authored as a Workflow renders to multiple ConfigRecords:
one on `sys_hub_flow` plus one per declared input on `sys_hub_flow_input`
and one per declared logic step on `sys_hub_flow_logic`.

Field shape is based on the canonical sys_hub_flow / sys_hub_flow_input /
sys_hub_flow_logic columns documented in the ServiceNow Flow Designer
product reference; verification against a live instance is captured under
tests/fixtures/ where applicable. The v1 field set is intentionally
minimal; later epics can extend.

All string fields go through `resolve_env_in_value` so authors can
parameterize values with `{{ env.X }}` references resolved at parse time.
Missing env vars raise ValueError with the literal variable name.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from nexus.templates.schemas._env import (
    resolve_env_in_dict_values,
    resolve_env_in_value,
)

__all__ = ["Workflow", "WorkflowInput", "WorkflowLogic"]


class WorkflowInput(BaseModel):
    """One sys_hub_flow_input child record.

    Attributes:
        name: Input identifier on the parent flow.
        type: Input type (e.g. "string", "boolean", "reference").
        required: Whether the input must be supplied at flow start.
        default: Optional default value (string form).
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    name: str = Field(..., min_length=1)
    type: str = Field(..., min_length=1)
    required: bool = False
    default: str | None = None

    @field_validator("name", "type", "default", mode="before")
    @classmethod
    def _resolve_env_refs(cls, value: object) -> object:
        """Resolve `{{ env.X }}` references in string fields."""
        return resolve_env_in_value(value)


class WorkflowLogic(BaseModel):
    """One sys_hub_flow_logic child record (an action step).

    Attributes:
        name: Step identifier on the parent flow.
        action: Action type identifier (e.g. "notification", "rest_step").
        inputs: Per-action input map (string -> string). Strings carry
            `{{ env.X }}` resolution at parse time.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    name: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)
    inputs: dict[str, str] = Field(default_factory=dict)

    @field_validator("name", "action", mode="before")
    @classmethod
    def _resolve_env_in_scalars(cls, value: object) -> object:
        """Resolve `{{ env.X }}` references in scalar string fields."""
        return resolve_env_in_value(value)

    @field_validator("inputs", mode="before")
    @classmethod
    def _resolve_env_in_inputs(cls, value: object) -> object:
        """Resolve `{{ env.X }}` references in every input map value."""
        return resolve_env_in_dict_values(value)


class Workflow(BaseModel):
    """One Flow Designer workflow template authored as YAML.

    Attributes:
        kind: Discriminator literal `"workflow"`.
        id: Template identifier (kebab-case slug; matches the directory name).
        version: Semantic version of this template revision.
        target_scope: ServiceNow scope slug the workflow belongs to.
            Use `"global"` for the global scope sentinel.
        name: Workflow display name written to sys_hub_flow.name.
        description: Optional short description written to
            sys_hub_flow.description.
        active: sys_hub_flow.active toggle; defaults to True.
        inputs: Tuple of WorkflowInput child rows.
        logic: Tuple of WorkflowLogic child rows.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    kind: Literal["workflow"] = "workflow"
    id: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    target_scope: str = Field(default="global", min_length=1)
    name: str = Field(..., min_length=1)
    description: str = ""
    active: bool = True
    inputs: tuple[WorkflowInput, ...] = ()
    logic: tuple[WorkflowLogic, ...] = ()

    @field_validator(
        "id",
        "version",
        "target_scope",
        "name",
        "description",
        mode="before",
    )
    @classmethod
    def _resolve_env_refs(cls, value: object) -> object:
        """Resolve `{{ env.X }}` references in every root string field at parse time."""
        return resolve_env_in_value(value)
