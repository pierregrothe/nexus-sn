# Story 01: NowAssistSkill Pydantic schema + env-var field validator

Status: backlog
Spec-Clarity: high
Depends-On: none

## Story

As a template author writing a NowAssist skill in YAML,
I want a Pydantic schema for `NowAssistSkill` that validates my
file at parse time and lets me parameterize fields with
`{{ env.X }}` env-var references,
so that bad templates fail loudly before any ServiceNow write
attempt.

## Acceptance Criteria

AC1 (NowAssistSkill model):
**Given** the file `src/nexus/templates/schemas/now_assist_skill.py`
**When** loaded
**Then** it exports `NowAssistSkill` -- Pydantic frozen+strict+
extra=forbid with fields:
* `kind: Literal["now_assist_skill"] = "now_assist_skill"`
* `id: str` (min_length=1)
* `version: str` (min_length=1)
* `target_scope: str = "global"`
* `name: str` (min_length=1)
* `description: str = ""`
* `instructions: str` (min_length=1)
* `active: bool = True`
* Optional fields for associated agent reference, trigger conditions
  (exact field set verified against SN ai_skill documentation or
  live-instance discovery)

AC2 (env-var substitution):
**Given** a YAML field `instructions: "Use {{ env.SKILL_PROMPT }}"`
where `SKILL_PROMPT=Read the incident.` is set
**When** the model is parsed
**Then** the final `instructions` value is `"Use Read the incident."`

AC3 (env-var unset error):
**Given** a YAML field `instructions: "{{ env.MISSING }}"` with
`MISSING` not set in the environment
**When** the model is parsed
**Then** Pydantic raises `ValidationError` whose cause contains
the literal `"env var 'MISSING' is not set"`.

AC4 (multiple substitutions per field):
**Given** a string field `description: "{{ env.A }}-{{ env.B }}"`
where `A=x`, `B=y`
**When** parsed
**Then** the resolved value is `"x-y"`.

AC5 (no Jinja2 / no other interpolation):
**Given** a string field `description: "{% if foo %}bar{% endif %}"`
**When** parsed
**Then** the value passes through verbatim. No template engine
evaluates Jinja-like syntax. Only `{{ env.X }}` is recognized.

AC6 (frozen + strict + extra=forbid):
**Given** any NowAssistSkill instance
**When** mutation is attempted (e.g. `skill.name = "x"`)
**Then** Pydantic raises ValidationError. Constructing with an
unknown field key raises ValidationError.

AC7 (round-trip via YAML):
**Given** a NowAssistSkill loaded from YAML
**When** dumped with `model_dump(mode="json")` and re-loaded
**Then** the two instances compare equal.

AC8 (field-shape verification):
**Given** the schema docstring
**When** a contributor reads it
**Then** the docstring cites a verifiable source for the ai_skill
field shape: a ServiceNow documentation URL, OR a reference to a
live-instance fixture file under `tests/fixtures/`. If neither is
available, the story is `needs-research` (not BLOCKED on the epic).

AC9 (type strictness):
**Given** the new file
**When** pyright strict + mypy strict run
**Then** 0 errors. No `# type: ignore`.

## Must NOT

* Must NOT add Jinja2 or any other template engine.
* Must NOT permit `extra` fields (extra="forbid").
* Must NOT use `dict[str, Any]` anywhere in a model field.
* Must NOT import from `nexus.cli`, `nexus.assessment`, or
  `nexus.agents`. Layer order strict.
* Must NOT call os.environ at module-import time (only inside
  the field validator, lazily).

## Tasks / Subtasks

* [ ] Create `src/nexus/templates/schemas/now_assist_skill.py` --
      `NowAssistSkill` model (AC1, AC6, AC9)
* [ ] Implement `@field_validator(mode="before")` resolving
      `{{ env.X }}` -> os.environ lookup (AC2, AC3, AC4, AC5)
* [ ] Verify field shape against SN documentation; cite source
      in the schema docstring (AC8)
* [ ] Create `tests/fakes/templates.py` -- builder helpers for
      NowAssistSkill instances (sets env vars via monkeypatch in
      conftest-style fixtures, OR exposes a `from_resolved()`
      classmethod for tests that need to skip the env step)
* [ ] Create `tests/templates/test_now_assist_skill_schema.py` (AC1, AC6, AC7)
* [ ] Create `tests/templates/test_env_var_resolution.py` (AC2-AC5)
* [ ] Update `src/nexus/templates/__init__.py` to re-export
      NowAssistSkill
* [ ] Update `.ratchet.json` baselines

## Existing Code

* `src/nexus/templates/schemas/now_assist_skill.py` -- 1-line stub
  awaiting this story
* `src/nexus/templates/models.py` -- TemplateEntry, TemplateManifest
  (sync v1; reference for the frozen+strict+extra=forbid pattern)
* `src/nexus/capture/models.py:ConfigRecord` -- target shape for
  Story 04's renderer

## Dev Notes

### Modules Affected

* `src/nexus/templates/schemas/now_assist_skill.py` (replace stub)
* `src/nexus/templates/__init__.py` (re-export)
* `tests/fakes/templates.py` (new)
* `tests/templates/__init__.py` (new)
* `tests/templates/test_now_assist_skill_schema.py` (new)
* `tests/templates/test_env_var_resolution.py` (new)

### env-var validator pattern

```python
import os
import re
from typing import Any
from pydantic import field_validator

_ENV_PATTERN = re.compile(r"\{\{\s*env\.([A-Z_][A-Z0-9_]*)\s*\}\}")


@field_validator("instructions", "description", ...)
@classmethod
def _resolve_env(cls, value: Any) -> Any:
    if not isinstance(value, str):
        return value
    def _sub(match: re.Match[str]) -> str:
        name = match.group(1)
        env = os.environ.get(name)
        if env is None:
            raise ValueError(f"env var {name!r} is not set")
        return env
    return _ENV_PATTERN.sub(_sub, value)
```

(Apply the validator to every string field that may be
parameterized; or write a shared validator that applies to all
string fields automatically via model_validator(mode="before")
unpacking dict values.)

### Testing Approach

* Use `monkeypatch.setenv("SKILL_PROMPT", "...")` (pytest's
  standard fixture; not a mock).
* Build NowAssistSkill instances inline per test.
* Test naming: `test_now_assist_skill_<scenario>` and
  `test_env_resolution_<scenario>`.

### Conventions

* Frozen+strict+extra=forbid (ADR-021)
* Python 3.14 PEP 695 type aliases if useful
* Google-style docstrings on all public classes
* File header per global rules
* `__all__` exports per module

## References

* PRD: `.primer/prd/PRD-003-nexus-template-library.md#In Scope`
* Brainstorming: `.primer/brainstorming/2026-05-19-nexus-template-library.md#Recommendation 1`
* Sibling epic Story 01 (Assessment): `.primer/epics/2026.06-nexus-assessment/01-rule-schemas-and-yaml-loader.story.md`
  (reference for frozen+strict+extra=forbid schema pattern)
* ADR-021: frozen-model-validators
* ADR-023: file-size-limits
* Patterns: `.primer/patterns.md#pydantic-conventions`
