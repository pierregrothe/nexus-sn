# Story 01: Pydantic rule schemas + YAML loader

Status: backlog
Spec-Clarity: high
Depends-On: none

## Story

As a rule author contributing a community ruleset,
I want a declarative YAML schema (`Ruleset` + `AssessmentRule` +
`RuleConstraint`) that Pydantic validates at load time,
so that I can author rules without Python and get clear errors
when my YAML is malformed.

## Acceptance Criteria

AC1 (Ruleset schema):
**Given** a `Ruleset` Pydantic model in `src/nexus/assessment/schemas/ruleset.py`
**When** the schema is loaded
**Then** it has `model_config = ConfigDict(frozen=True, strict=True, extra="forbid")`
and fields: `id: str`, `version: str`, `description: str`,
`applies_to: tuple[str, ...]`, `rules: tuple[AssessmentRule, ...]`.

AC2 (AssessmentRule schema):
**Given** an `AssessmentRule` Pydantic model
**When** the schema is loaded
**Then** it has frozen+strict+extra=forbid and fields:
`id: str`, `description: str`, `severity: Severity`,
`phase: Phase`, `scope: RuleScope`,
`required_tables: tuple[str, ...]`, `logic: Logic = Logic.AND_ALL`,
`constraints: tuple[RuleConstraint, ...]`.

AC3 (Severity, Phase, Logic enums):
**Given** `severity`, `phase`, `logic` field types
**When** the enums are defined
**Then** `Severity = ERROR | WARNING | INFO`,
`Phase = PRE_APPLY | POST_APPLY | STANDALONE`,
`Logic = AND_ALL | OR_ANY`. All `StrEnum` subclasses
(Python 3.11+ stdlib).

AC4 (RuleScope discriminated union):
**Given** `RuleScope` field type
**When** parsed
**Then** it is a discriminated union with two variants:
`TableScope(kind="table", table: str)` and
`CrossTableScope(kind="cross-table")`. Pydantic discriminator
field is `kind`. Each variant is frozen+strict+extra=forbid.

AC5 (RuleConstraint discriminated union, schema only):
**Given** `RuleConstraint` field type
**When** parsed
**Then** it is a discriminated-union schema with 5 variant
placeholders identified by `operator` field:
`record_exists`, `field_equals`, `field_in`, `count_gte`,
`count_lte`. Each variant has its own fields validated at parse
time. Implementation of `.check()` for each operator is Story 02.

AC6 (cross-validator: constraint.table in required_tables):
**Given** a Ruleset with a constraint referencing a table NOT in
its rule's `required_tables`
**When** the Ruleset is parsed
**Then** Pydantic raises `ValidationError` with a clear message.

AC7 (cross-validator: scope-operator compatibility):
**Given** a Ruleset where a constraint operator is incompatible
with the rule's scope (e.g., `count_lte` over a `TableScope` is
allowed; an op marked `cross_table_only` over a `TableScope`
fails)
**When** the Ruleset is parsed
**Then** Pydantic raises `ValidationError`. (Initial 5-operator
set has no cross-table-only ops; the validator hook exists for
future ops.)

AC8 (YAML loader):
**Given** a YAML file at `templates/assessments/foo.yaml`
**When** `load_ruleset(path) -> Ruleset` is called
**Then** it parses YAML via `yaml.safe_load` (no
`yaml.unsafe_load`) and constructs `Ruleset.model_validate(...)`.
Returns frozen Ruleset.

AC9 (loader error handling):
**Given** a YAML file with invalid syntax or schema violation
**When** `load_ruleset(path)` is called
**Then** it raises `RulesetLoadError(path: Path, cause: Exception)`
with a clear message including the path and the underlying
validation message.

AC10 (round-trip):
**Given** a sample Ruleset constructed in Python
**When** dumped to YAML via `yaml.safe_dump(ruleset.model_dump())`
and re-loaded via `load_ruleset`
**Then** the round-tripped Ruleset equals the original.

## Must NOT

* Must NOT use `yaml.load` or `yaml.unsafe_load`. Only `yaml.safe_load`.
* Must NOT permit `extra` fields anywhere. All schemas
  `extra="forbid"`.
* Must NOT couple schemas to `tests/`. Schemas live in
  `src/nexus/assessment/schemas/` and are imported by the engine
  + reporter + CLI without test imports.
* Must NOT use `dict[str, Any]` anywhere in a model field. Every
  field is typed.
* Must NOT define `.check()` or evaluation logic on constraint
  variants -- that is Story 02.

## Tasks / Subtasks

* [ ] Create `src/nexus/assessment/schemas/ruleset.py` -- Ruleset model (AC1)
* [ ] Create `src/nexus/assessment/schemas/rule.py` -- AssessmentRule model (AC2)
* [ ] Create `src/nexus/assessment/schemas/enums.py` -- Severity, Phase, Logic (AC3)
* [ ] Create `src/nexus/assessment/schemas/scope.py` -- RuleScope union (AC4)
* [ ] Create `src/nexus/assessment/schemas/constraints.py` -- RuleConstraint union skeleton (AC5)
* [ ] Add `@model_validator(mode="after")` on `AssessmentRule` (AC6, AC7)
* [ ] Create `src/nexus/assessment/loader.py` -- `load_ruleset(path)` (AC8)
* [ ] Add `RulesetLoadError` to `src/nexus/assessment/errors.py` (AC9)
* [ ] Create `tests/fakes/rulesets.py` -- canned ruleset fixtures
* [ ] Create `tests/test_assessment_ruleset_schema.py` (AC1-AC7)
* [ ] Create `tests/test_assessment_loader.py` (AC8-AC10)
* [ ] Update `src/nexus/assessment/__init__.py` exports

## Existing Code

* `src/nexus/assessment/` -- stub package; replace empty
  `schemas/health.py`, `schemas/readiness.py`,
  `schemas/validation.py` if redundant once Ruleset/Rule unify
  the schema surface, OR keep them as report-output schemas
  (decide during Story 04). For Story 01, focus on the rule-input
  schemas above; do not modify existing stubs.

## Dev Notes

### Modules Affected

* `src/nexus/assessment/schemas/{ruleset.py, rule.py, enums.py, scope.py, constraints.py}`
* `src/nexus/assessment/loader.py`
* `src/nexus/assessment/errors.py`
* `src/nexus/assessment/__init__.py`
* `tests/fakes/rulesets.py`
* `tests/test_assessment_ruleset_schema.py`
* `tests/test_assessment_loader.py`

### Testing Approach

* Hand-build Ruleset instances from Pydantic constructor for
  schema tests (no YAML needed).
* For loader tests, write small YAML strings to `tmp_path` via
  pytest fixture; load and assert.
* No mocks. Fakes in `tests/fakes/rulesets.py` provide pre-built
  Ruleset / AssessmentRule instances for downstream stories.
* Each enum value tested with at least one round-trip case.

### Conventions

* Frozen+strict+extra=forbid (ADR-021, patterns.md)
* Python 3.14 syntax -- PEP 695 type aliases if useful
* `@field_validator` for simple checks, `@model_validator(mode="after")`
  returning `Self` for cross-field
* File header per global rules
* Google-style docstrings on all public classes
* `__all__` exports per module

## References

* PRD: `.primer/prd/PRD-002-nexus-assessment.md#In Scope`
* Brainstorming: `.primer/brainstorming/2026-05-19-nexus-assessment-rule-engine.md#Recommendation 1`
* ADR: `.primer/adr/ADR-021-frozen-model-validators.md`
* ADR: `.primer/adr/ADR-023-file-size-limits.md`
* Patterns: `.primer/patterns.md#pydantic-conventions`
