# Story 02: Constraint DSL operators (record_exists, field_equals, field_in, count_gte, count_lte)

Status: done
Spec-Clarity: high
Depends-On: 01

## Story

As the RuleEngine,
I want each `RuleConstraint` variant to expose a uniform
`evaluate(records: tuple[ConfigRecord, ...]) -> ConstraintResult`
method,
so that the engine can run any constraint against any slice of
CaptureResult without dispatching on operator type.

## Acceptance Criteria

AC1 (ConstraintResult model):
**Given** the file `src/nexus/assessment/dsl.py`
**When** loaded
**Then** it exports `ConstraintResult` -- Pydantic frozen+strict
+extra=forbid with fields: `passed: bool`, `affected_sys_ids: tuple[str, ...]`,
`message: str`.

AC2 (record_exists variant):
**Given** a `RecordExistsConstraint(operator="record_exists",
table: str, filter: FieldFilter)` (FieldFilter is a tuple of
`(field_name, expected_value)` pairs, all AND-ed)
**When** `.evaluate(records)` is called against records of the
given table
**Then** it returns `passed=True` if at least one record matches
all filter pairs, `passed=False` otherwise.
`affected_sys_ids` contains the matching records' sys_ids on
pass, empty tuple on fail.

AC3 (field_equals variant):
**Given** a `FieldEqualsConstraint(operator="field_equals",
table: str, field: str, expected: str, filter: FieldFilter | None)`
**When** `.evaluate(records)` is called
**Then** it returns `passed=True` iff every record matching
the optional pre-filter has `record.fields[field] == expected`.
If the pre-filter matches zero records, `passed=False` with
message "no matching records for filter". `affected_sys_ids`
lists records that failed the equality check.

AC4 (field_in variant):
**Given** a `FieldInConstraint(operator="field_in",
table: str, field: str, expected: tuple[str, ...],
filter: FieldFilter | None)`
**When** `.evaluate(records)` is called
**Then** returns `passed=True` iff every filtered record has
`record.fields[field] in expected`. `affected_sys_ids` lists
records that failed.

AC5 (count_gte variant):
**Given** a `CountGteConstraint(operator="count_gte",
table: str, threshold: int, filter: FieldFilter | None)`
**When** `.evaluate(records)` is called
**Then** returns `passed=True` iff the count of filter-matching
records is `>= threshold`. `affected_sys_ids` lists all matching
records.

AC6 (count_lte variant):
**Given** a `CountLteConstraint(operator="count_lte",
table: str, threshold: int, filter: FieldFilter | None)`
**When** `.evaluate(records)` is called
**Then** returns `passed=True` iff the count of filter-matching
records is `<= threshold`. `affected_sys_ids` lists matching
records when failed (the excess).

AC7 (empty records input):
**Given** any constraint variant
**When** `.evaluate(())` is called with empty records
**Then** `record_exists` returns `passed=False`,
`field_equals` returns `passed=False` with "no matching records",
`field_in` returns `passed=False`,
`count_gte` returns `passed=(threshold <= 0)`,
`count_lte` returns `passed=True`.

AC8 (filter semantics):
**Given** a constraint with `filter=(("active", "true"),
("scope_sys_id", "scope_x"))`
**When** records contain a record with both fields matching
**Then** that record is included in the filtered subset.
Filter pairs are AND-ed. Empty filter = all records included.

AC9 (missing field handling):
**Given** a constraint targeting a field that does not exist on
any record (record.fields lookup misses)
**When** `.evaluate(records)` runs
**Then** for `field_equals` / `field_in`: that record fails its
check; `affected_sys_ids` includes it. No exceptions raised.

AC10 (no I/O):
**Given** any constraint
**When** `.evaluate(records)` runs
**Then** zero I/O: no file access, no network, no logging that
makes Tier-1 hook complain. Pure function.

## Must NOT

* Must NOT use `dict[str, Any]` in constraint field types.
* Must NOT raise on missing fields -- return `passed=False`
  instead.
* Must NOT import `nexus.cli`, `nexus.ui`, or any layer above
  `assessment`. Layer order strict.
* Must NOT mutate the input records tuple.
* Must NOT add a 6th operator. Five only. New operators require a
  new story and ADR.

## Tasks / Subtasks

* [ ] Define `ConstraintResult` in `src/nexus/assessment/dsl.py` (AC1)
* [ ] Define `FieldFilter` type alias: `tuple[tuple[str, str], ...]`
* [ ] Implement `RecordExistsConstraint.evaluate()` (AC2)
* [ ] Implement `FieldEqualsConstraint.evaluate()` (AC3)
* [ ] Implement `FieldInConstraint.evaluate()` (AC4)
* [ ] Implement `CountGteConstraint.evaluate()` (AC5)
* [ ] Implement `CountLteConstraint.evaluate()` (AC6)
* [ ] Wire each variant into the discriminated union from Story 01
* [ ] Create `tests/test_constraint_record_exists.py` (AC2, AC7, AC8, AC10)
* [ ] Create `tests/test_constraint_field_equals.py` (AC3, AC9)
* [ ] Create `tests/test_constraint_field_in.py` (AC4)
* [ ] Create `tests/test_constraint_count_gte.py` (AC5, AC7)
* [ ] Create `tests/test_constraint_count_lte.py` (AC6, AC7)
* [ ] Update ratchet baselines

## Existing Code

* `src/nexus/assessment/schemas/constraints.py` -- discriminated
  union skeleton from Story 01; this story adds `.evaluate()`
  methods and concrete variant fields.
* `src/nexus/capture/models.py:ConfigRecord` -- input record
  shape. `record.fields: SnRecord = dict[str, SnFieldValue]`.
* `tests/fakes/rulesets.py` -- canned Ruleset fixtures from
  Story 01 (extend for constraint-specific cases).

## Dev Notes

### Modules Affected

* `src/nexus/assessment/dsl.py` (new, holds ConstraintResult + FieldFilter)
* `src/nexus/assessment/schemas/constraints.py` (extend each variant)
* `tests/test_constraint_*.py` (5 files, one per operator)
* `tests/fakes/rulesets.py` (extend)

### Testing Approach

* Build small `tuple[ConfigRecord, ...]` fixtures inline per test
  (no shared mega-fixture).
* One AC -> one test function. Test naming:
  `test_<operator>_<scenario>` per global rule.
* Cover the cross-product: empty records, missing fields,
  filter-match-zero, multi-record matches.
* No mocks. ConfigRecord is a Pydantic model -- construct directly.

### Conventions

* Frozen+strict+extra=forbid per ADR-021
* No defensive None checks; missing field returns failure path
* Python 3.14 PEP 695 type aliases if useful for FieldFilter

## References

* Story 01: schema skeleton this story implements
* PRD: `.primer/prd/PRD-002-nexus-assessment.md#In Scope`
* Brainstorming: `.primer/brainstorming/2026-05-19-nexus-assessment-rule-engine.md#Recommendation 2`
* `src/nexus/capture/models.py:78-88` (ConfigRecord shape)
