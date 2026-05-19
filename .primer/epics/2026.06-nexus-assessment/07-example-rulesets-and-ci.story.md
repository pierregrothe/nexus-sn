# Story 07: Example rulesets in templates/assessments/ + CI validator integration

Status: backlog
Spec-Clarity: medium
Depends-On: 01

## Story

As a rule author contributing a community ruleset,
I want to read 3+ working example YAML files that exercise the
5-operator DSL across both `table` and `cross-table` scopes, and
I want CI to validate every ruleset on every PR,
so that I can copy-modify a proven pattern and trust that
malformed YAML never reaches main.

## Acceptance Criteria

AC1 (directory layout):
**Given** the repository root
**When** Story 07 ships
**Then** `templates/assessments/` exists with at least 3 ruleset
files. Filenames follow `<slug>.yaml` convention. Each file
parses cleanly via `load_ruleset(path)`.

AC2 (example 1 -- scope readiness, PRE_APPLY):
**Given** `templates/assessments/scope-readiness.yaml`
**When** parsed
**Then** it contains at least 1 rule with
`phase=PRE_APPLY`, `scope.kind=table`,
`required_tables=("sys_scope",)`, using `record_exists` to
assert the target scope is pre-existing AND active
(`logic=AND_ALL` over `record_exists` + `field_equals`).

AC3 (example 2 -- post-deploy verification, POST_APPLY):
**Given** `templates/assessments/post-deploy-checks.yaml`
**When** parsed
**Then** it contains at least 1 rule with
`phase=POST_APPLY`, using `count_gte` to assert a minimum
number of expected records exist after deploy.

AC4 (example 3 -- standalone health, STANDALONE):
**Given** `templates/assessments/instance-health.yaml`
**When** parsed
**Then** it contains at least 2 rules with
`phase=STANDALONE`. One rule uses `count_lte` on a
`cross-table` scope to flag instances with too many orphaned
records. One rule uses `field_in` to verify a critical config
field is in a known-good set.

AC5 (every YAML parses):
**Given** every file in `templates/assessments/*.yaml`
**When** `load_ruleset(path)` is called
**Then** zero `ValidationError`. Zero `RulesetLoadError`. Zero
`yaml.YAMLError`.

AC6 (applies_to resolution):
**Given** every ruleset's `applies_to` field
**When** the CI validator runs
**Then** every entry is either:
- a valid template id (resolves to
  `templates/<id>/manifest.yaml` existence), OR
- the literal string `"*"` for rulesets that apply to all
  templates (the standalone health and post-deploy examples
  may use this)

AC7 (CI workflow):
**Given** `.github/workflows/validate-templates.yml`
**When** a PR modifies any `templates/assessments/*.yaml`
**Then** the CI job runs a new validator step that:
1. Iterates `templates/assessments/*.yaml`
2. Calls `load_ruleset(path)` on each
3. For each ruleset, resolves every `applies_to` entry
4. Exits non-zero on any failure with a clear error pointing
   at the offending file:line

AC8 (validator script):
**Given** `scripts/validate_assessment_rulesets.py`
**When** invoked with no args
**Then** it walks `templates/assessments/`, validates all,
prints a summary like `N rulesets validated; M rules; 0 errors`
or `Error in <path>: <message>` per failure. Exits 0 on
success, 1 on any failure.

AC9 (validator handles missing directory):
**Given** `templates/assessments/` does not exist
**When** the script runs
**Then** exits 0 with message "no rulesets to validate" --
not an error.

AC10 (round-trip via examples):
**Given** every example ruleset
**When** loaded then re-dumped and re-loaded
**Then** the two parsed objects compare equal.

AC11 (test parses each example):
**Given** `tests/test_assessment_examples_parse.py`
**When** the test runs
**Then** it iterates every YAML in `templates/assessments/` and
asserts `load_ruleset(path)` succeeds. This test guards against
silent regressions in the schema layer.

## Must NOT

* Must NOT use `referenced_by_count_gte` or `parent_exists`
  operators in any example -- those are out of scope per
  PRD-002. Five-operator initial DSL only.
* Must NOT skip CI integration. The validator must run on every
  PR.
* Must NOT delete or modify existing
  `.github/workflows/validate-templates.yml` -- add a step or
  extend it.
* Must NOT add Python rule fixtures here -- examples are YAML
  only (matches PRD-002 anti-creep on runtime Python plugins).
* Must NOT inline rule details for production ServiceNow logic
  that the project doesn't yet have. The examples must be
  plausible but minimal -- enough to demonstrate the DSL, not
  enough to ship as production rulesets.

## Tasks / Subtasks

* [ ] Create `templates/assessments/scope-readiness.yaml` (AC2)
* [ ] Create `templates/assessments/post-deploy-checks.yaml` (AC3)
* [ ] Create `templates/assessments/instance-health.yaml` (AC4)
* [ ] Implement `scripts/validate_assessment_rulesets.py` (AC8, AC9)
* [ ] Extend `.github/workflows/validate-templates.yml` to call
      the new script (AC7)
* [ ] Add documentation note in `docs/CONTRIBUTING.md` about
      assessment rule contribution (one paragraph; pointer to
      the YAML examples)
* [ ] Create `tests/test_assessment_examples_parse.py` (AC11)
* [ ] Verify AC1, AC5, AC6, AC10 via the parse test plus a
      separate `test_validate_assessment_rulesets_script.py`

## Existing Code

* `templates/<existing-templates>/manifest.yaml` -- template id
  resolution targets
* `.github/workflows/validate-templates.yml` -- CI pattern to
  extend
* Story 01: `load_ruleset`, `Ruleset` schema
* Existing validation script (if any) for templates/

## Dev Notes

### Modules Affected

* `templates/assessments/*.yaml` (3 new files)
* `scripts/validate_assessment_rulesets.py` (new)
* `.github/workflows/validate-templates.yml` (extend)
* `docs/CONTRIBUTING.md` (extend with one section)
* `tests/test_assessment_examples_parse.py` (new)
* `tests/test_validate_assessment_rulesets_script.py` (new)

### Example skeleton

```yaml
# templates/assessments/scope-readiness.yaml
id: scope-readiness
version: "1.0.0"
description: |
  Verify the target scope exists and is active before applying
  any template.
applies_to: ["*"]
rules:
  - id: scope-must-exist
    description: Target scope must exist as a sys_scope record
    severity: ERROR
    phase: PRE_APPLY
    scope: { kind: table, table: sys_scope }
    required_tables: [sys_scope]
    logic: AND_ALL
    constraints:
      - operator: record_exists
        table: sys_scope
        filter:
          - [scope, "<target_scope_name>"]
      - operator: field_equals
        table: sys_scope
        field: active
        expected: "true"
        filter:
          - [scope, "<target_scope_name>"]
```

The `<target_scope_name>` placeholder is illustrative -- in
production the rule would either be parameterized via the
template-apply context (future work) or hard-coded per ruleset.
For Story 07 examples, hard-code a recognizable placeholder.

### Testing Approach

* `test_assessment_examples_parse.py` iterates the directory
  glob; one test for the directory, one assertion per file.
* `test_validate_assessment_rulesets_script.py` invokes the
  script via `subprocess.run([sys.executable, "scripts/..."]) `
  with controlled `cwd` containing a temp `templates/assessments/`
  directory.

### Conventions

* YAML files: ASCII only, 2-space indent, no trailing whitespace
* No emojis in examples (global rule)
* `applies_to: ["*"]` is the convention for ruleset that applies
  to all templates -- document in schema docstring

## References

* Story 01: `Ruleset` schema, `load_ruleset`
* PRD: `.primer/prd/PRD-002-nexus-assessment.md#In Scope`
* Brainstorming: `.primer/brainstorming/2026-05-19-nexus-assessment-rule-engine.md#Recommendation 8`
* Existing CI pattern: `.github/workflows/validate-templates.yml`
