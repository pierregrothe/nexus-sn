# Story 05: `nexus migrate plan` + runbook

Status: backlog
Spec-Clarity: high
Depends-On: 04

## Story

As a Solution Consultant executing a dependency-safe migration by hand,
I want `nexus migrate plan` to build a MigrationPlan from a curated
Selection and emit a lane-shaped runbook,
so that I have a single auditable, hand-executable document with a
validity window and every waiver/acknowledgment on its front page.

## Acceptance Criteria

AC1 (plan CLI, GWT):
**Given** `nexus migrate plan --selection selection.yaml --out runbook.md`
**When** it runs against valid full captures of both instances
**Then** it builds a `MigrationPlan` (closure + waves via Story 04), writes
the plan YAML alongside `--out`, renders a console summary, and writes the
runbook markdown to `--out`; exit 0.

AC2 (runbook lane-shaped units):
**Given** a rendered runbook
**When** inspected
**Then** each unit of work is one lane-shaped item (an app to install, an
update set to move, a data batch, a manual rebuild step) -- never one line
per individual artifact; items sharing a wave and lane are grouped into a
single runbook entry.

AC3 (runbook header):
**Given** a rendered runbook
**When** inspected
**Then** its header carries `generated-at` (UTC), the source + target
snapshot identities (profile + captured_at for both instances), and a
validity-window statement instructing the operator to run `plan --recheck`
before executing any wave by hand.

AC4 (waiver/acknowledgment front page):
**Given** a plan with waivers and acknowledgments
**When** the runbook is rendered
**Then** every `Waiver` (author, approver, reason, date) and every
`Acknowledgment` (author, reason, date) appears verbatim on the runbook's
first page, before any wave content.

AC5 (documented-gap register verbatim):
**Given** any rendered runbook
**When** inspected
**Then** it includes, verbatim, the documented-gap register from
PRD-005/ADR-026 (script-body references, sys_domain separation, legacy
Workflow internals, notifications/email templates, REST/SOAP + MID/
credential refs, business-rule execution order) as a fixed section, never
conditionally omitted.

AC6 (byte-stable LF output):
**Given** two successive runs of `plan` over the same inputs
**When** their runbook markdown output is compared
**Then** it is byte-identical, using `\n` line endings only.

AC7 (unapproved plan still renders, GWT):
**Given** a plan with unresolved blocking findings (per Story 04's
`validate_approval`)
**When** `plan` runs
**Then** it still writes the runbook, but the runbook's front page
prominently flags the plan as NOT APPROVED with the list of blocking
reasons; exit code is 0 (plan generation succeeded; approval is a separate,
later git-reviewed step).

## Must NOT

- Must NOT write to either ServiceNow instance -- `plan` is read-only over
  already-captured inputs (advisory only).
- Must NOT invent an in-tool approval/merge mechanism -- approval is a
  human editing the plan YAML's `approved_by`/`approved_at` fields and
  committing via git PR review (ADR-026#Decision 2); the CLI never sets
  those fields itself.
- Must NOT collapse the runbook's unit of work to one line per artifact --
  lane-shaped grouping (AC2) is mandatory.

## Tasks / Subtasks

- [ ] Create `src/nexus/migrate/runbook.py` -- `render_runbook(plan) ->
      str` markdown emitter (AC2-AC6)
- [ ] Implement lane-shaped grouping (group PlanItems by `(wave_index,
      lane)`) (AC2)
- [ ] Implement header block (generated-at, snapshot identities, validity
      window) (AC3)
- [ ] Implement waiver/acknowledgment front-page section (AC4)
- [ ] Add the fixed documented-gap register constant (shared with Story
      04's finding taxonomy) (AC5)
- [ ] Wire `@migrate_app.command("plan")` in
      `src/nexus/cli/commands_migrate.py` calling closure + planner (Story
      04) + `render_runbook` (AC1, AC7)
- [ ] Create `tests/test_migrate_runbook.py`, `tests/cli/test_migrate_plan_cmd.py`
      (AC1-AC7)

## Existing Code

- `src/nexus/replatform/reporter.py` -- `render_checklist`/`write_markdown`
  pattern this story's runbook emitter mirrors (console render + markdown
  emit split).
- `src/nexus/cli/commands_migrate.py` (Story 03) -- existing `migrate_app`
  group to extend with `plan`.
- `src/nexus/migrate/closure.py`, `src/nexus/migrate/planner.py` (Story 04)
  -- supply the `MigrationPlan` this story renders.

## Dev Notes

### Modules Affected

- `src/nexus/migrate/runbook.py` (new)
- `src/nexus/cli/commands_migrate.py` (add `plan` command)
- `tests/test_migrate_runbook.py`, `tests/cli/test_migrate_plan_cmd.py`
  (new)

### Testing Approach

- Function-based `test_<func>_<scenario>` tests, e.g.
  `test_render_runbook_groups_by_wave_and_lane`,
  `test_render_runbook_flags_unapproved_plan`.
- No mocks; runbook tests render a `tests/fakes/migrate.py`
  `MigrationPlan` fixture and assert on the markdown text.
- Byte-stability asserted by rendering twice and comparing raw strings.
- CLI test via Typer `CliRunner` against fixture Selection + capture inputs
  in `tmp_path`.

## References

- PRD: `.primer/prd/PRD-005-nexus-migration-planner.md#In Scope`
  (Runbook bullet), `#Acceptance Criteria` (runbook + validity-window
  bullet)
- ADR: `.primer/adr/ADR-026-selective-migration-planner.md#Decision 2`
  (plan file as artifact of record), `#Decision 4` (freshness enforcement),
  `#Consequences` (documented-gap register)
- Brainstorming:
  `.primer/brainstorming/2026-07-02-selective-migration-planner.md#Key Insight 2`
  (lane-shaped unit of work), `#Recommendation 3` (documented-gap register
  content)
