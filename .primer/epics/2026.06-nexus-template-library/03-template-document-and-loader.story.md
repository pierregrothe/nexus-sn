# Story 03: TemplateDocument discriminated union + YAML load helper

Status: backlog
Spec-Clarity: high
Depends-On: 01, 02

## Story

As ApplyEngine,
I want a single `TemplateDocument` type that I can load from a
YAML file and dispatch via the `kind` discriminator,
so that I do not need to dispatch on filename or maintain
separate loaders per template type.

## Acceptance Criteria

AC1 (TemplateDocument union):
**Given** `src/nexus/templates/document.py`
**When** loaded
**Then** it exports `TemplateDocument` as a discriminated union:
`Annotated[NowAssistSkill | Workflow, Field(discriminator="kind")]`.

AC2 (load_template_document):
**Given** `load_template_document(path: Path) -> TemplateDocument`
in the same module
**When** called against a valid YAML file
**Then** the function parses YAML via `yaml.safe_load`, then
validates via `TemplateDocument` adapter, and returns the
constructed Pydantic instance.

AC3 (loader error handling):
**Given** a file that does not exist OR malformed YAML OR a
schema-violating document
**When** `load_template_document(path)` runs
**Then** it raises `TemplateLoadError(path, cause)` carrying the
offending path and original exception (OSError, yaml.YAMLError,
or pydantic.ValidationError).

AC4 (NowAssistSkill discriminator dispatch):
**Given** a YAML file starting with `kind: now_assist_skill`
**When** loaded
**Then** the returned instance is an instance of `NowAssistSkill`.

AC5 (Workflow discriminator dispatch):
**Given** a YAML file starting with `kind: workflow`
**When** loaded
**Then** the returned instance is an instance of `Workflow`.

AC6 (unknown kind rejection):
**Given** a YAML file with `kind: ai_agent` (or any other value
not in the v1 union)
**When** loaded
**Then** `TemplateLoadError` is raised; the message identifies the
offending `kind`.

AC7 (round-trip):
**Given** a TemplateDocument loaded from a fixture YAML
**When** re-dumped with `yaml.safe_dump(instance.model_dump(mode="json"))`
and re-loaded
**Then** the two instances compare equal.

AC8 (env-var substitution still works through the union):
**Given** a NowAssistSkill YAML with `{{ env.X }}` in a field and
the env var set
**When** loaded via `load_template_document`
**Then** the resolved value is present on the returned instance
(env validator runs through the union dispatch, not bypassed).

AC9 (TemplateLoadError):
**Given** `src/nexus/templates/errors.py`
**When** loaded
**Then** it exports `TemplateError` (base) and
`TemplateLoadError(path, cause)` mirror the Assessment
`RulesetLoadError` pattern.

AC10 (type strictness):
**Given** the new files
**When** pyright strict + mypy strict run
**Then** 0 errors. No `# type: ignore`.

## Must NOT

* Must NOT use `yaml.load` or `yaml.unsafe_load`. Only `yaml.safe_load`.
* Must NOT permit unknown `kind` values (Pydantic discriminator
  enforces; document explicitly).
* Must NOT bypass the env-var field validators from Stories 01/02.
* Must NOT import from `nexus.cli` or `nexus.assessment`.

## Tasks / Subtasks

* [ ] Create `src/nexus/templates/errors.py` -- TemplateError +
      TemplateLoadError (AC9)
* [ ] Create `src/nexus/templates/document.py` -- TemplateDocument
      union + load_template_document helper (AC1-AC8, AC10)
* [ ] Extend `tests/fakes/templates.py` with `sample_skill_yaml()`,
      `sample_workflow_yaml()` factory helpers
* [ ] Create `tests/templates/test_template_document.py` (AC1-AC8)
* [ ] Create `tests/templates/test_template_loader_errors.py` (AC3, AC6)
* [ ] Update `src/nexus/templates/__init__.py` re-exports
* [ ] Update `.ratchet.json` baselines

## Existing Code

* Story 01: `NowAssistSkill`
* Story 02: `Workflow`
* Pattern reference: `src/nexus/assessment/loader.py` --
  `load_ruleset` + `RulesetLoadError` (mirror the structure)

## Dev Notes

### Modules Affected

* `src/nexus/templates/document.py` (new)
* `src/nexus/templates/errors.py` (new)
* `src/nexus/templates/__init__.py` (extend)
* `tests/fakes/templates.py` (extend)
* `tests/templates/test_template_document.py` (new)
* `tests/templates/test_template_loader_errors.py` (new)

### Discriminated union pattern

```python
from typing import Annotated
from pydantic import Field, TypeAdapter

from nexus.templates.schemas.now_assist_skill import NowAssistSkill
from nexus.templates.schemas.workflow import Workflow

type TemplateDocument = Annotated[
    NowAssistSkill | Workflow, Field(discriminator="kind")
]

_TEMPLATE_ADAPTER = TypeAdapter(TemplateDocument)


def load_template_document(path: Path) -> TemplateDocument:
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TemplateLoadError(path, exc) from exc
    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise TemplateLoadError(path, exc) from exc
    try:
        return _TEMPLATE_ADAPTER.validate_python(data, strict=False)
    except ValidationError as exc:
        raise TemplateLoadError(path, exc) from exc
```

(strict=False mirrors `nexus.assessment.loader.load_ruleset` for
YAML list-to-tuple coercion.)

### Testing Approach

* Hand-build YAML strings in tests; write to tmp_path.
* Use real NowAssistSkill / Workflow instances via tests/fakes/templates.
* Mirror Assessment's `test_loader.py` structure.

### Conventions

* Frozen+strict+extra=forbid on every model
* `yaml.safe_load` exclusively
* Errors carry both path and cause

## References

* Stories 01, 02
* PRD: `.primer/prd/PRD-003-nexus-template-library.md#In Scope`
* Brainstorming: `.primer/brainstorming/2026-05-19-nexus-template-library.md#Recommendation 3`
* Reference: `src/nexus/assessment/loader.py` (mirror pattern)
