# src/nexus/templates/schemas/now_assist_skill.py
# NowAssistSkill Pydantic schema mapping to the SN ai_skill table.
# Author: Pierre Grothe
# Date: 2026-05-19

"""NowAssistSkill template document.

One YAML file authored as a NowAssistSkill renders to one ConfigRecord
on the `ai_skill` ServiceNow table.

Field shape is based on the canonical ai_skill columns documented in the
ServiceNow Now Assist Skill Kit product reference; verification against
a live instance is captured under tests/fixtures/ where applicable.
The v1 field set is intentionally minimal -- additional columns can be
added in later epics without breaking existing templates because every
new field defaults at the schema level.

String fields go through `resolve_env_in_value` so authors can
parameterize values with `{{ env.X }}` references resolved at parse
time from `os.environ`. Missing env vars raise ValueError with the
literal variable name.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from nexus.templates.schemas._env import resolve_env_in_value

__all__ = ["NowAssistSkill"]


class NowAssistSkill(BaseModel):
    """One NowAssist skill template authored as YAML.

    Attributes:
        kind: Discriminator literal `"now_assist_skill"`.
        id: Template identifier (kebab-case slug; matches the directory name).
        version: Semantic version of this template revision.
        target_scope: ServiceNow scope slug the skill belongs to. Use
            `"global"` for the global scope sentinel; the renderer maps
            this to the well-known global scope sys_id without an SN query.
        name: Skill display name written to ai_skill.name.
        description: Optional one-liner written to ai_skill.short_description.
        instructions: The skill prompt / policy text written to
            ai_skill.instructions. Required; carries the actual behavior.
        active: ai_skill.active toggle; defaults to True.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    kind: Literal["now_assist_skill"] = "now_assist_skill"
    id: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    target_scope: str = Field(default="global", min_length=1)
    name: str = Field(..., min_length=1)
    description: str = ""
    instructions: str = Field(..., min_length=1)
    active: bool = True

    @field_validator(
        "id",
        "version",
        "target_scope",
        "name",
        "description",
        "instructions",
        mode="before",
    )
    @classmethod
    def _resolve_env_refs(cls, value: object) -> object:
        """Resolve `{{ env.X }}` references in every string field at parse time."""
        return resolve_env_in_value(value)
