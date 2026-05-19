# Story 02: Workflow Pydantic schema with nested input/logic models

Status: done
Spec-Clarity: high
Depends-On: none

## Story

As a template author writing a sys_hub_flow workflow in YAML,
I want a Pydantic schema for `Workflow` that captures the
parent flow record plus nested input and logic child rows,
so that one YAML file declares a complete workflow including its
child records and validation catches missing pieces before write.

## Acceptance Criteria

AC1 (Workflow model):
**Given** the file `src/nexus/templates/schemas/workflow.py`
**When** loaded
**Then** it exports `Workflow` -- frozen+strict+extra=forbid with:
* `kind: Literal["workflow"] = "workflow"`
* `id: str` (min_length=1)
* `version: str` (min_length=1)
* `target_scope: str = "global"`
* `name: str` (min_length=1)
* `description: str = ""`
* `active: bool = True`
* `inputs: tuple[WorkflowInput, ...]` (may be empty)
* `logic: tuple[WorkflowLogic, ...]` (may be empty)
* Optional flow-level fields verified against SN sys_hub_flow
  documentation or live-instance fixture

AC2 (WorkflowInput nested model):
**Given** `WorkflowInput` exported from the same module
**When** loaded
**Then** it is frozen+strict+extra=forbid with:
* `name: str` (min_length=1)
* `type: str` (e.g. "string", "boolean", "reference")
* `required: bool = False`
* `default: str | None = None`

AC3 (WorkflowLogic nested model):
**Given** `WorkflowLogic` exported from the same module
**When** loaded
**Then** it is frozen+strict+extra=forbid with at least:
* `name: str`
* `action: str` (action type identifier)
* `inputs: dict[str, str] = {}` -- per-action input map
  (verified to satisfy frozen-model-with-dict-field constraint;
  may need to be tuple-of-pairs instead)

AC4 (env-var substitution applies to all string fields):
**Given** a workflow YAML with `inputs[0].default: "{{ env.DEFAULT_X }}"`
**When** parsed with `DEFAULT_X=42` set
**Then** the resolved `default` value is `"42"`. Same env-var rules
as Story 01.

AC5 (env-var substitution applies to nested models):
**Given** `description: "{{ env.WF_DESC }}"` at the Workflow root
**When** parsed
**Then** the value is resolved at parse time. The validator must
apply to nested models, not just the root.

AC6 (round-trip through YAML):
**Given** a Workflow with both inputs and logic populated
**When** `yaml.safe_dump(model_dump(mode="json"))` and re-loaded
**Then** the two instances compare equal.

AC7 (frozen + strict + extra=forbid):
**Given** any Workflow / WorkflowInput / WorkflowLogic instance
**When** mutation or unknown-field construction is attempted
**Then** Pydantic raises ValidationError.

AC8 (field-shape verification):
**Given** the schema docstring
**When** a contributor reads it
**Then** the docstring cites a verifiable source for the
sys_hub_flow / sys_hub_flow_input / sys_hub_flow_logic field
shapes. If unavailable, story status `needs-research`.

AC9 (type strictness):
**Given** the new file
**When** pyright strict + mypy strict run
**Then** 0 errors. No `# type: ignore`.

## Must NOT

* Must NOT permit `extra` fields anywhere.
* Must NOT use `dict[str, Any]`. Per-action input maps use
  `dict[str, str]` or `tuple[tuple[str, str], ...]`.
* Must NOT import from `nexus.cli`, `nexus.assessment`, or
  `nexus.agents`.
* Must NOT inline the env-var validator. Share the implementation
  from Story 01 via a helper module
  (`src/nexus/templates/schemas/_env.py` or similar).
* Must NOT add a Jinja2 dependency.

## Tasks / Subtasks

* [ ] If Story 01 created a shared `_env.py` helper, import it.
      Otherwise extract Story 01's env validator into a shared
      helper module before this story starts (refactoring Story 01
      counts as part of Story 02's prep).
* [ ] Create `src/nexus/templates/schemas/workflow.py` (AC1-AC3,
      AC7, AC9)
* [ ] Verify field shape against SN documentation; cite source
      (AC8)
* [ ] Extend `tests/fakes/templates.py` with `make_workflow()`
      builder helper
* [ ] Create `tests/templates/test_workflow_schema.py` (AC1-AC3,
      AC6, AC7)
* [ ] Create `tests/templates/test_workflow_env_resolution.py`
      (AC4, AC5)
* [ ] Update `src/nexus/templates/__init__.py` re-exports
* [ ] Update `.ratchet.json` baselines

## Existing Code

* `src/nexus/templates/schemas/workflow.py` -- 1-line stub
* Story 01 -- env-var validator helper (extract to shared module
  if not already shared)

## Dev Notes

### Modules Affected

* `src/nexus/templates/schemas/workflow.py` (replace stub)
* `src/nexus/templates/schemas/_env.py` (new shared helper, may
  be created in Story 01 prep)
* `src/nexus/templates/__init__.py`
* `tests/fakes/templates.py` (extend)
* `tests/templates/test_workflow_schema.py` (new)
* `tests/templates/test_workflow_env_resolution.py` (new)

### Workflow structural shape

```python
class WorkflowInput(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    name: str
    type: str
    required: bool = False
    default: str | None = None


class WorkflowLogic(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    name: str
    action: str
    inputs: dict[str, str] = Field(default_factory=dict)


class Workflow(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    kind: Literal["workflow"] = "workflow"
    id: str
    version: str
    target_scope: str = "global"
    name: str
    description: str = ""
    active: bool = True
    inputs: tuple[WorkflowInput, ...] = ()
    logic: tuple[WorkflowLogic, ...] = ()
```

(Exact field set finalized after AC8 verification.)

### Testing Approach

* Build fixtures inline. Use `monkeypatch.setenv()` for env tests.
* Test naming: `test_workflow_<scenario>`,
  `test_workflow_input_<scenario>`, `test_workflow_logic_<scenario>`.

### Conventions

* Frozen+strict+extra=forbid (ADR-021)
* Google-style docstrings
* Python 3.14 syntax

## References

* Story 01 (env-var pattern, shared helper)
* PRD: `.primer/prd/PRD-003-nexus-template-library.md#In Scope`
* Brainstorming: `.primer/brainstorming/2026-05-19-nexus-template-library.md#Recommendation 2`
* ADR-021: frozen-model-validators
