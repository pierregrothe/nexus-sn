# Story 05: AssessmentReporter renders GateReport via existing ui/components/

Status: backlog
Spec-Clarity: high
Depends-On: 04

## Story

As a NEXUS user running `nexus assess --for <template>`,
I want a clean console summary of the gate's findings -- one
table per severity, a verdict badge, and a remediation hint
panel,
so that I can read a long ruleset's output and act on it
without grepping JSON.

## Acceptance Criteria

AC1 (render_report signature):
**Given** `src/nexus/assessment/reporter.py`
**When** loaded
**Then** it exports
`render_report(report: GateReport, ctx: RenderContext) -> None`.
Module-level function. Writes to `ctx.console`.

AC2 (PASS verdict layout):
**Given** a `GateReport(verdict=PASS, findings=())`
**When** rendered on RICH profile
**Then** the output contains:
1. A `Notice.success(...)` line with the gate name + ruleset id
2. A `StatusBadge(PASS)` (green)
3. A `KeyValuePanel` showing `GateSummary` numbers
   (rules_evaluated, rules_passed, etc.)
4. No DataTable (findings is empty)

AC3 (BLOCK verdict layout):
**Given** a `GateReport(verdict=BLOCK, findings=N)` where N >= 1
**When** rendered
**Then** the output contains:
1. A `Notice.error(...)` line with summary count
2. A `StatusBadge(BLOCK)` (red)
3. A `KeyValuePanel` with summary
4. A `DataTable` with one row per Finding: columns =
   (`rule_id`, `severity`, `affected`, `message`)
5. A `Hint` panel suggesting `--force` to bypass (Gate 1) or
   "verify the ruleset" (Gate 2 / standalone)

AC4 (ERROR verdict layout):
**Given** a `GateReport(verdict=ERROR, findings=N)`
**When** rendered
**Then** the output contains:
1. A `Notice.error(...)` with "evaluation incomplete" message
2. A `StatusBadge(ERROR)` (orange/yellow)
3. A `DataTable` of ERROR findings
4. A `Hint` panel suggesting re-running with `--live` or
   inspecting the ruleset for missing required_tables

AC5 (PLAIN profile rendering):
**Given** the same reports on PLAIN profile
**When** rendered
**Then** the output is line-per-event ASCII text:
- `[PASS|BLOCK|ERROR] <gate-name> <ruleset-id>: M findings`
- For each finding:
  `[<severity>] <rule_id>: <message> (affected: <count>)`
- No tables, no styles.

AC6 (DataTable column truncation):
**Given** a Finding with `message` longer than 80 chars
**When** rendered to DataTable
**Then** the message column truncates with ellipsis to fit the
console width. Full message available in JSON export (story
outside this epic; not implemented here).

AC7 (severity ordering):
**Given** mixed-severity findings (1 ERROR, 2 WARNING, 1 INFO)
**When** rendered
**Then** the DataTable rows are sorted: ERROR first, then
WARNING, then INFO. Within severity, original input order
preserved.

AC8 (template_id rendering):
**Given** `GateReport.template_id="acme-incident-mgmt"`
**When** rendered
**Then** the KeyValuePanel includes a `template_id` row.
When `template_id=None` (HealthScan), the row is omitted.

AC9 (RenderContext.console used exclusively):
**Given** any rendered report
**When** the test captures `ctx.console.export_text()`
**Then** all output (including the DataTable and KeyValuePanel)
was written through `ctx.console`. No `print()`, no direct
stdout.

AC10 (no new UI primitives):
**Given** the new reporter module
**When** its imports are inspected
**Then** it imports only from `nexus.ui.components.{data_table,
key_value_panel, status_badge, notice, hint}` and Rich
stdlib. No `nexus.ui.framed_viewer`. No new components defined
in this story.

## Must NOT

* Must NOT add a new UI primitive. Reuse only.
* Must NOT use `FramedViewer` (assessment output isn't paginated
  tables and the rendering is one-shot).
* Must NOT write JSON / machine-readable output here -- that's
  a separate story outside this epic.
* Must NOT call `console.print` outside `ctx.console`.
* Must NOT inline rendering inside the CLI command -- the
  reporter is a separate module so Story 06's CLI just calls
  `render_report(report, ctx)`.

## Tasks / Subtasks

* [ ] Create `src/nexus/assessment/reporter.py` with
      `render_report(report, ctx)` (AC1, AC9)
* [ ] Implement PASS layout (AC2)
* [ ] Implement BLOCK layout (AC3)
* [ ] Implement ERROR layout (AC4)
* [ ] Implement PLAIN profile branch (AC5)
* [ ] DataTable column truncation (AC6)
* [ ] Findings sort by severity (AC7)
* [ ] template_id conditional row (AC8)
* [ ] Verify import set (AC10) -- ruff `--select TID` config
      already catches forbidden imports
* [ ] Create `tests/test_assessment_reporter_pass.py` (AC2, AC5)
* [ ] Create `tests/test_assessment_reporter_block.py` (AC3, AC6, AC7)
* [ ] Create `tests/test_assessment_reporter_error.py` (AC4)
* [ ] Create `tests/test_assessment_reporter_plain.py` (AC5)
* [ ] Create `tests/test_assessment_reporter_template_id.py` (AC8)
* [ ] Update ratchet baseline

## Existing Code

* `src/nexus/ui/components/data_table.py:DataTable`
* `src/nexus/ui/components/key_value_panel.py:KeyValuePanel`
* `src/nexus/ui/components/status_badge.py:StatusBadge`
* `src/nexus/ui/components/notice.py:Notice`
* `src/nexus/ui/components/hint.py:Hint`
* `src/nexus/ui/render_context.py:RenderContext`,
  `RenderProfile`
* `src/nexus/cli/commands_plugins_advisories.py` -- mirror
  pattern reference
* Story 04: `GateReport`, `GateSummary`, `Finding`,
  `GateVerdict`

## Dev Notes

### Modules Affected

* `src/nexus/assessment/reporter.py` (new)
* `tests/test_assessment_reporter_*.py` (5 files)

### Testing Approach

* Construct real `GateReport` instances via fakes (no mocks).
* Capture console output via `Console(file=StringIO(), record=True)`
  in tests; assert on `export_text()`.
* For RICH-profile tests, use the project's `NEXUS_THEME` to
  avoid `MissingStyle` errors (see batch-progress story 02
  precedent).
* Test naming: `test_render_report_<scenario>`.

### Conventions

* Pure presentation; no engine logic
* Module-level function, not a class
* `match`/`case` over `GateVerdict` with `case _:` default

## References

* Story 04: report shape
* PRD: `.primer/prd/PRD-002-nexus-assessment.md#In Scope`
* Brainstorming: `.primer/brainstorming/2026-05-19-nexus-assessment-rule-engine.md#Recommendation 7`
* Precedent: `src/nexus/cli/commands_plugins_advisories.py`
* ADR-024: FramedViewer scope (explicit non-use here)
