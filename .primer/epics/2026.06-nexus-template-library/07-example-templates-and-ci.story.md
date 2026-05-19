# Story 07: 3 example templates + per-template readiness rulesets + CI validator

Status: backlog
Spec-Clarity: medium
Depends-On: 03

## Story

As a template author contributing community templates,
I want 3 working example templates in `templates/` covering the
NowAssistSkill and Workflow variants, with per-template readiness
rulesets and CI validation,
so that I can copy-modify a proven pattern and trust that malformed
templates never reach main.

## Acceptance Criteria

AC1 (example template files):
**Given** the repository root
**When** Story 07 ships
**Then** `templates/` contains at least 3 template directories,
each with `template.yaml` + `manifest.yaml`:
* `templates/nowassist-incident-triage/`
* `templates/nowassist-tier1-rephrase/`
* `templates/simple-approval-flow/`

AC2 (per-template manifest.yaml):
**Given** each `templates/<id>/manifest.yaml`
**When** parsed via the sync v1 TemplateEntry schema
**Then** it carries `id`, `version`, `type` (now_assist_skill or
workflow), and `path` (the relative path to template.yaml). Mirrors
the structure used by `templates/manifest.json`.

AC3 (incident-triage template):
**Given** `templates/nowassist-incident-triage/template.yaml`
**When** parsed via `load_template_document`
**Then** the result is a NowAssistSkill with `id ==
"nowassist-incident-triage"`, `target_scope == "global"`, and a
non-trivial `instructions` field describing incident triage.

AC4 (tier1-rephrase template):
**Given** `templates/nowassist-tier1-rephrase/template.yaml`
**When** parsed
**Then** the result is a NowAssistSkill (different content; smaller
template demonstrating minimum-viable fields).

AC5 (simple-approval-flow template):
**Given** `templates/simple-approval-flow/template.yaml`
**When** parsed
**Then** the result is a Workflow with at least 1 input and 1
logic entry.

AC6 (per-template readiness rulesets):
**Given** each template
**When** Story 07 ships
**Then** there is a corresponding ruleset under
`templates/assessments/<id>-readiness.yaml` with
`applies_to: [<id>]` and at least one PRE_APPLY rule. Each ruleset
parses via the existing Assessment loader.

AC7 (validate_template_documents script):
**Given** `scripts/validate_template_documents.py`
**When** invoked with no args
**Then** it walks `templates/<id>/template.yaml` and validates each
via `load_template_document`. Exits 0 on success, 1 on any
ValidationError or TemplateLoadError. Prints `OK` / `FAIL` lines
per file plus a summary.

AC8 (validator handles missing templates dir):
**Given** an environment without a `templates/` directory
**When** the script runs
**Then** exits 0 with `no templates to validate` (mirrors the
Assessment validator's behavior).

AC9 (CI workflow integration):
**Given** `.github/workflows/validate-templates.yml`
**When** Story 07 ships
**Then** the workflow has a new step running
`poetry run python scripts/validate_template_documents.py` after
the existing assessment-rulesets step.

AC10 (manifest.json refresh):
**Given** `templates/manifest.json`
**When** Story 07 ships
**Then** the `templates` array lists the 3 new templates with
`{id, version, type, path}` entries matching the per-template
`manifest.yaml` files. `version` field on the root bumped if
contract changed.

AC11 (round-trip via Pydantic):
**Given** every shipped template
**When** loaded then re-dumped and re-loaded
**Then** the two parsed objects compare equal.

AC12 (test guard):
**Given** `tests/templates/test_shipped_templates.py`
**When** run
**Then** it iterates every YAML in `templates/<id>/template.yaml`
and asserts `load_template_document(path)` succeeds. This test
guards against silent regressions in the schema layer.

## Must NOT

* Must NOT use `dict[str, Any]` in any template YAML.
* Must NOT ship a template with `extra` fields that don't match
  the schema.
* Must NOT skip the CI integration.
* Must NOT add Python rule fixtures or executable code in
  templates/.
* Must NOT use `{{ env.X }}` references in the shipped templates
  unless documented as required (keep v1 examples self-contained
  to avoid CI breakage when env vars aren't set).

## Tasks / Subtasks

* [ ] Author `templates/nowassist-incident-triage/template.yaml`
      + `manifest.yaml` (AC1, AC3)
* [ ] Author `templates/nowassist-tier1-rephrase/template.yaml`
      + `manifest.yaml` (AC1, AC4)
* [ ] Author `templates/simple-approval-flow/template.yaml`
      + `manifest.yaml` (AC1, AC5)
* [ ] Author the 3 per-template readiness rulesets under
      `templates/assessments/` (AC6)
* [ ] Implement `scripts/validate_template_documents.py` (AC7, AC8)
* [ ] Extend `.github/workflows/validate-templates.yml` (AC9)
* [ ] Update `templates/manifest.json` (AC10)
* [ ] Add `docs/CONTRIBUTING.md` paragraph about contributing a
      template (one paragraph; cite the YAML examples)
* [ ] Create `tests/templates/test_shipped_templates.py` (AC11, AC12)
* [ ] Create `tests/templates/test_validate_template_documents_script.py`
      (mirror the Assessment script test, AC7, AC8)

## Existing Code

* Stories 01-03: NowAssistSkill, Workflow, TemplateDocument,
  load_template_document
* `templates/assessments/*.yaml` -- 3 Assessment rulesets
  shipped with `applies_to: ["*"]`
* `scripts/validate_assessment_rulesets.py` -- mirror its shape
* `.github/workflows/validate-templates.yml` -- already has the
  assess-validator step; extend it

## Dev Notes

### Modules Affected

* `templates/<id>/template.yaml` + `manifest.yaml` (6 new files)
* `templates/assessments/<id>-readiness.yaml` (3 new files)
* `scripts/validate_template_documents.py` (new)
* `.github/workflows/validate-templates.yml` (extend)
* `templates/manifest.json` (refresh)
* `docs/CONTRIBUTING.md` (extend)
* `tests/templates/test_shipped_templates.py` (new)
* `tests/templates/test_validate_template_documents_script.py` (new)

### Incident-triage example skeleton

```yaml
kind: now_assist_skill
id: nowassist-incident-triage
version: "1.0.0"
target_scope: "global"
name: "Incident Triage"
description: "Classify incoming incident urgency and route to the
right queue."
instructions: |
  Read the incident short_description and description.
  Assign urgency 1-4 (1=critical, 4=low).
  Route to assignment_group based on the inferred category.
active: true
```

### Simple-approval-flow example skeleton

```yaml
kind: workflow
id: simple-approval-flow
version: "1.0.0"
target_scope: "global"
name: "Simple Approval Flow"
description: "Two-step approval flow for change requests."
active: true
inputs:
  - name: request_sys_id
    type: string
    required: true
  - name: approver
    type: reference
    required: true
logic:
  - name: notify_approver
    action: notification
    inputs:
      to: "{{ env.NOTIFY_TO }}"
      template: "approval_request"
```

(`{{ env.NOTIFY_TO }}` example is illustrative; final templates
either set sensible defaults or drop the env reference. CI must
parse cleanly without env mutation -- choose accordingly.)

### Per-template readiness ruleset skeleton

```yaml
id: nowassist-incident-triage-readiness
version: "1.0.0"
description: Pre-deploy readiness for nowassist-incident-triage
applies_to: [nowassist-incident-triage]
rules:
  - id: target-scope-exists
    description: target scope (global or override) is captured
    severity: ERROR
    phase: PRE_APPLY
    scope: { kind: table, table: sys_scope }
    required_tables: [sys_scope]
    logic: AND_ALL
    constraints:
      - operator: count_gte
        table: sys_scope
        threshold: 1
        filter: []
```

### Testing Approach

* Iterate directory glob; assert each template + ruleset parses.
* Subprocess-invoke the validator script via `subprocess.run`
  against a controlled tmp_path templates directory.
* Mirror `tests/assessment/test_validate_assessment_rulesets_script.py`.

### Conventions

* ASCII only in template YAML.
* `applies_to: [<id>]` for per-template rulesets; `applies_to: ["*"]`
  for cross-template rulesets (the existing 3 Assessment rulesets).
* No env-var references in shipped templates unless documented.

## References

* Stories 01, 02, 03
* PRD: `.primer/prd/PRD-003-nexus-template-library.md#In Scope`
* Brainstorming: `.primer/brainstorming/2026-05-19-nexus-template-library.md#Recommendations 8-10`
* Reference: `scripts/validate_assessment_rulesets.py`
* Reference: `templates/assessments/*.yaml` (3 Assessment examples)
