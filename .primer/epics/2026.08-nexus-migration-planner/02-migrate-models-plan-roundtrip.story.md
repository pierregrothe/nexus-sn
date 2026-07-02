# Story 02: migrate models + plan round-trip

Status: backlog
Spec-Clarity: high
Depends-On: none

## Story

As a NEXUS developer building the migration planner,
I want frozen Pydantic models for Selection, MigrationPlan, Wave, PlanItem,
IntegrityFinding, Waiver, and Acknowledgment with a byte-stable YAML round
trip,
so that the plan file can be the auditable artifact of record that git PR
review governs.

## Acceptance Criteria

AC1 (PlanLane enum):
**Given** `PlanLane` in `src/nexus/migrate/models.py`
**When** loaded
**Then** it is a `StrEnum` with exactly `APP_REPO`, `UPDATE_SET`, `DATA`,
`MANUAL`.

AC2 (FindingKind enum):
**Given** `FindingKind`
**When** loaded
**Then** it is a `StrEnum` including at minimum `STRANDED_DEPENDENCY`,
`DATA_PREREQUISITE`, `CYCLE` (open to extension by later stories, e.g.
Story 04's access-posture-drift rule).

AC3 (Selection + SelectionItem):
**Given** `Selection`
**When** loaded
**Then** frozen+strict+extra=forbid with `source_profile: str`,
`target_profile: str`, `source_captured_at: UtcDatetime`, `items:
tuple[SelectionItem, ...]`, where each `SelectionItem` is frozen+strict+
extra=forbid with `key: str` (natural key), `disposition:
Literal["include", "exclude", "undecided"]`, `annotation: str = ""`,
`annotated_by: str = ""`.

AC4 (PlanItem):
**Given** `PlanItem`
**When** loaded
**Then** frozen+strict+extra=forbid with `key: str`, `lane: PlanLane`,
`added_by_closure: bool = False`, `wave_index: Annotated[int,
Field(ge=0)]`.

AC5 (IntegrityFinding):
**Given** `IntegrityFinding`
**When** loaded
**Then** frozen+strict+extra=forbid with `kind: FindingKind`, `subject_key:
str`, `detail: str`, `waiver: Waiver | None = None`, `acknowledgment:
Acknowledgment | None = None`.

AC6 (Waiver + segregation-of-duties validator, table AC):
| Case | author | approver | Expected |
|---|---|---|---|
| valid waiver | "alice" | "bob" | constructs cleanly |
| self-approved waiver | "alice" | "alice" | `ValidationError` from `@model_validator(mode="after")` |

`Waiver` fields: `author: str`, `approver: str`, `reason: str`, `date:
UtcDatetime`.

AC7 (Acknowledgment):
**Given** `Acknowledgment`
**When** loaded
**Then** frozen+strict+extra=forbid with `author: str`, `reason: str`,
`date: UtcDatetime`.

AC8 (Wave):
**Given** `Wave`
**When** loaded
**Then** frozen+strict+extra=forbid with `index: Annotated[int,
Field(ge=0)]`, `items: tuple[PlanItem, ...]`.

AC9 (MigrationPlan -- approval block + snapshots):
**Given** `MigrationPlan`
**When** loaded
**Then** frozen+strict+extra=forbid with `schema_version: str`,
`source_profile: str`, `target_profile: str`, `source_captured_at:
UtcDatetime`, `target_captured_at: UtcDatetime`, `waves: tuple[Wave, ...]`,
`findings: tuple[IntegrityFinding, ...]`, `approved_by: str = ""`,
`approved_at: UtcDatetime | None = None`, `target_chain: tuple[str, ...] =
()` (reserved promotion-chain field per PRD-005 Open Questions; v1 never
populates more than one entry).

AC10 (YAML round trip, byte-stable):
**Given** a `MigrationPlan` with at least one waiver and one acknowledgment
**When** emitted via `emit_plan_yaml(plan) -> str` and reloaded via
`load_plan_yaml(text) -> MigrationPlan`
**Then** `emit_plan_yaml(load_plan_yaml(emit_plan_yaml(plan))) ==
emit_plan_yaml(plan)` byte-for-byte, using `\n` (LF) line endings only.

AC11 (exports + purity):
**Given** the module
**When** imported
**Then** `__all__` lists every public model/enum, no field uses
`dict[str, Any]`, and the module imports nothing from `cli/` or `agents/`
(ADR-026#Decision 1).

## Must NOT

- Must NOT add closure, waiver-approval, or CLI logic to this module --
  models + YAML emit/load only (closure is Story 04, CLI is Stories 03/05).
- Must NOT use `dict[str, Any]` in any field.
- Must NOT import from `src/nexus/cli/` or `src/nexus/agents/`.
- Must NOT allow `Waiver` construction with `author == approver` to succeed
  silently -- must raise `ValidationError`.

## Tasks / Subtasks

- [ ] Create `src/nexus/migrate/models.py` -- PlanLane, FindingKind,
      SelectionItem, Selection, PlanItem, Wave, Waiver, Acknowledgment,
      IntegrityFinding, MigrationPlan (AC1-AC9)
- [ ] Add `@model_validator(mode="after")` author!=approver check on Waiver
      (AC6)
- [ ] Implement `emit_plan_yaml` / `load_plan_yaml` with
      `yaml.safe_dump(..., sort_keys=False, default_flow_style=False)` +
      explicit LF normalization for byte-stability (AC10)
- [ ] Create `tests/fakes/migrate.py` -- canned Selection/MigrationPlan/
      Waiver/Acknowledgment fixtures
- [ ] Create `tests/test_migrate_models.py` (AC1-AC11)

## Existing Code

- `src/nexus/replatform/models.py` -- reference for the
  frozen+strict+extra=forbid + `@model_validator(mode="after")` + `Self`
  return pattern this story mirrors.
- `src/nexus/replatform/domain_map.py` -- reference for `yaml.safe_load`
  usage already in this codebase (load side); this story is the first
  `yaml.safe_dump` emit path.
- `src/nexus/config/types.py` -- `UtcDatetime`.

## Dev Notes

### Modules Affected

- `src/nexus/migrate/models.py` (new)
- `tests/fakes/migrate.py`, `tests/test_migrate_models.py` (new)

### Testing Approach

- Construct each model from the Pydantic constructor; assert frozen by
  attempting mutation and expecting `ValidationError`, mirroring Story 01
  of the 2026.07 epic.
- Function-based `test_<func>_<scenario>` tests, e.g.
  `test_waiver_rejects_self_approval`,
  `test_emit_plan_yaml_round_trip_byte_stable`.
- No mocks; fakes in `tests/fakes/migrate.py` supply reusable
  Selection/MigrationPlan instances for Stories 03-07.
- The round-trip test writes to `tmp_path`, reads back, and compares raw
  text (not just parsed equality) to catch key-ordering/whitespace drift.

## References

- PRD: `.primer/prd/PRD-005-nexus-migration-planner.md#In Scope` (models
  bullet), `#Acceptance Criteria` (models + round-trip bullet)
- ADR: `.primer/adr/ADR-026-selective-migration-planner.md#Decision 1`
  (package boundary), `#Decision 2` (plan file is the artifact of record),
  `#Decision 3` (waiver/acknowledgment semantics), `#Decision 5` (PlanLane
  is a provisional hint)
- Brainstorming:
  `.primer/brainstorming/2026-07-02-selective-migration-planner.md#Session Decisions`
  (1-2), `#Adversarial Review` Round 2 (waiver segregation,
  DATA-PREREQUISITE acknowledgment, promotion-tier field)
- Patterns: `.primer/patterns.md` ("Pydantic everywhere" section)
