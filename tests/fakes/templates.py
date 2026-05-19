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

from nexus.templates.schemas.now_assist_skill import NowAssistSkill

__all__ = ["make_now_assist_skill"]


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
