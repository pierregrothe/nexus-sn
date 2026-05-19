# Story 04: render_to_records pure function -- TemplateDocument -> ConfigRecord tuple

Status: done
Spec-Clarity: high
Depends-On: 03

## Story

As ApplyEngine,
I want a pure function that turns one TemplateDocument plus a
resolved scope_sys_id into a tuple of ConfigRecords ready for
UpdateSetWriter,
so that template rendering is testable in isolation and the
engine does not own the per-variant translation logic.

## Acceptance Criteria

AC1 (render signature):
**Given** `src/nexus/templates/renderer.py`
**When** loaded
**Then** it exports
`render_to_records(document: TemplateDocument, scope_sys_id: str,
captured_at: UtcDatetime) -> tuple[ConfigRecord, ...]`.
Module-level function; pure (no I/O).

AC2 (NowAssistSkill -> 1 record):
**Given** a `NowAssistSkill(name="Triage", instructions="...", ...)`
and `scope_sys_id="s1"`
**When** `render_to_records(skill, "s1", NOW)` runs
**Then** the result is a 1-tuple containing one ConfigRecord with:
* `sys_id` -- deterministically generated from `(skill.id, version)`
  via a stable hash (e.g. `sha256(f"{id}:{version}").hexdigest()[:32]`)
* `table = "ai_skill"`
* `scope_sys_id = "s1"`
* `scope_name = "global"` (or resolved scope name)
* `captured_at = NOW`
* `fields` -- a SnRecord mapping each NowAssistSkill field to its
  ai_skill column name (table-specific mapping documented inline)
* `parent_sys_id = None`

AC3 (Workflow -> parent + children):
**Given** a `Workflow(name="approval", inputs=(i1, i2),
logic=(l1,), ...)` and `scope_sys_id="s1"`
**When** `render_to_records(workflow, "s1", NOW)` runs
**Then** the result is a 4-tuple in order:
1. Parent record (table=`sys_hub_flow`)
2. WorkflowInput i1 record (table=`sys_hub_flow_input`,
   parent_sys_id=parent's sys_id)
3. WorkflowInput i2 record (table=`sys_hub_flow_input`,
   parent_sys_id=parent's sys_id)
4. WorkflowLogic l1 record (table=`sys_hub_flow_logic`,
   parent_sys_id=parent's sys_id)

AC4 (deterministic sys_ids):
**Given** the same TemplateDocument rendered twice
**When** both renders complete
**Then** every ConfigRecord has the same sys_id in both renders.
(Stable hashes; not random UUIDs.)

AC5 (purity):
**Given** any render call
**When** it runs
**Then** zero I/O. No `os.environ` lookups (env-var resolution
already happened at TemplateDocument parse time). No file access.
No network. No mutation of inputs.

AC6 (empty children for Workflow):
**Given** a `Workflow(inputs=(), logic=(), ...)`
**When** rendered
**Then** the result is a 1-tuple (parent only).

AC7 (scope_sys_id propagates everywhere):
**Given** a Workflow with N children
**When** rendered
**Then** every record (parent + children) has the same
`scope_sys_id`.

AC8 (active field maps to "active":"true"/"false"):
**Given** a NowAssistSkill or Workflow with `active=True`
**When** rendered
**Then** the resulting ConfigRecord.fields["active"] == "true"
(ServiceNow boolean field convention).

AC9 (unknown discriminator handled):
**Given** the match block over `document.kind`
**When** the discriminator does not match `now_assist_skill` or
`workflow`
**Then** `render_to_records` raises `AssertionError("unreachable
kind: ...")` (covered by `case _:` default; v1 discriminator is
exhaustive).

AC10 (type strictness):
**Given** the new file
**When** pyright strict + mypy strict run
**Then** 0 errors. No `# type: ignore`.

## Must NOT

* Must NOT call `os.environ`. env-var resolution already happened.
* Must NOT generate non-deterministic sys_ids (no `uuid.uuid4()`,
  no `time.time_ns()` for sys_id generation).
* Must NOT import `nexus.cli`, `nexus.assessment`, or `nexus.agents`.
* Must NOT mutate the input document or any field.
* Must NOT inline the per-table field mapping into `apply.py` --
  keep the mapping in `renderer.py` so engine stays thin.

## Tasks / Subtasks

* [ ] Create `src/nexus/templates/renderer.py` with
      `render_to_records(...)` (AC1, AC5, AC10)
* [ ] Implement NowAssistSkill renderer (AC2, AC4, AC8)
* [ ] Implement Workflow renderer + child fan-out (AC3, AC6, AC7, AC8)
* [ ] Implement deterministic sys_id generator (AC4)
* [ ] Add `case _:` default with AssertionError + pragma: no cover (AC9)
* [ ] Create `tests/templates/test_render_skill.py` (AC2, AC4, AC8)
* [ ] Create `tests/templates/test_render_workflow.py` (AC3, AC6, AC7)
* [ ] Create `tests/templates/test_render_purity.py` (AC5)
* [ ] Update `src/nexus/templates/__init__.py` re-exports
* [ ] Update `.ratchet.json` baselines

## Existing Code

* Story 03: `TemplateDocument` discriminated union
* `src/nexus/capture/models.py:ConfigRecord` -- output shape
* `src/nexus/capture/tables.py:AI_AUTOMATION` -- table identifiers

## Dev Notes

### Modules Affected

* `src/nexus/templates/renderer.py` (new)
* `src/nexus/templates/__init__.py`
* `tests/templates/test_render_*.py` (3 files)

### Deterministic sys_id

```python
import hashlib

def _stable_sys_id(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]

# Skill: seed = f"{template.id}:{template.version}:skill"
# Workflow parent: seed = f"{template.id}:{template.version}:flow"
# Workflow input: seed = f"{template.id}:{template.version}:input:{input.name}"
# Workflow logic: seed = f"{template.id}:{template.version}:logic:{logic.name}"
```

Hash is 64 hex chars; truncating to 32 matches ServiceNow's
32-char sys_id format.

### Testing Approach

* Pure-function tests: construct documents inline, call render,
  assert on resulting ConfigRecord tuple.
* No fakes needed; this layer has no I/O.
* Test naming: `test_render_skill_<scenario>` and
  `test_render_workflow_<scenario>`.

### Conventions

* `match`/`case` over `document.kind` discriminator
* `case _:` default required (CLAUDE.md convention)
* No I/O; no env lookups
* Module-level function (not a class)

## References

* Story 03 (TemplateDocument input shape)
* PRD: `.primer/prd/PRD-003-nexus-template-library.md#In Scope`
* Brainstorming: `.primer/brainstorming/2026-05-19-nexus-template-library.md#Recommendation 4`
* `src/nexus/capture/models.py:ConfigRecord`
