# Story 05: ApplyEngine + ApplyResult + AppliedRecord + scope resolution

Status: done
Spec-Clarity: high
Depends-On: 04

## Story

As a CLI orchestrator (Story 06),
I want an `ApplyEngine.apply(template_path, ...)` method that
takes a template file plus a connected ServiceNow client and
returns an `ApplyResult` describing what was sent,
so that the apply step is testable in isolation against a
FakeServiceNowClient and the CLI just glues capture + gates + engine
together.

## Acceptance Criteria

AC1 (ApplyResult model):
**Given** `src/nexus/assessment/context.py:ApplyResult` (currently
empty placeholder)
**When** Story 05 ships
**Then** ApplyResult is populated with fields:
* `update_set_sys_id: str`
* `update_set_name: str`
* `template_id: str`
* `template_version: str`
* `target_scope_sys_id: str`
* `applied_records: tuple[AppliedRecord, ...]`
* `instance_id: str`
* `started_at: UtcDatetime`
* `completed_at: UtcDatetime`
Frozen+strict+extra=forbid.

AC2 (AppliedAction enum + AppliedRecord):
**Given** `src/nexus/templates/results.py`
**When** loaded
**Then** it exports `AppliedAction = REQUESTED | FAILED` (StrEnum)
and `AppliedRecord` Pydantic frozen with:
* `table: str`
* `name: str`
* `requested_sys_id: str | None`
* `action: AppliedAction`
* `error_message: str | None`

AC3 (ApplyEngine signature):
**Given** `src/nexus/templates/apply.py` (currently 1-line stub)
**When** Story 05 ships
**Then** it exports `ApplyEngine(@dataclass(slots=True, frozen=True))`
with a single public method
`apply(self, template_path: Path) -> ApplyResult`. The dataclass
holds injected collaborators (sn_client, paths, ... -- see Dev Notes).

AC4 (ApplyEngine end-to-end happy path):
**Given** an ApplyEngine wired to `FakeServiceNowClient` and a
sample NowAssistSkill template
**When** `engine.apply(path)` runs
**Then** in order:
1. `load_template_document(path)` produces the Pydantic instance.
2. `target_scope` slug is resolved to a sys_id via the SN client
   (one `sys_scope?name=<slug>` query); `"global"` resolves to
   the well-known global sys_id without a query.
3. `render_to_records(doc, scope_sys_id, NOW)` produces a record
   tuple.
4. A `sys_update_set` record is created via
   `sn_client.create_record("sys_update_set", {...})` with
   `name=NEXUS-apply-<template.id>-<ts>` and structured description
   metadata.
5. `UpdateSetWriter.push(records, update_set_sys_id)` runs.
6. ApplyResult is constructed with all 9 fields populated;
   `applied_records[i].action == AppliedAction.REQUESTED` for
   every record.

AC5 (target_scope = "global" sentinel):
**Given** a template with `target_scope: "global"`
**When** apply runs
**Then** no `sys_scope` query is issued; the global scope sys_id
is the constant `"global"` (ServiceNow convention) or whatever
the project's well-known constant resolves to. ApplyResult.
target_scope_sys_id reflects this.

AC6 (target_scope unknown -> apply aborts):
**Given** a template with `target_scope: "x_does_not_exist"` and
the SN client returns no matching sys_scope record
**When** apply runs
**Then** ApplyEngine raises `ScopeNotFoundError(slug=...)` BEFORE
creating any sys_update_set. No record is written.

AC7 (AppliedRecord.action = FAILED predicate):
**Given** an UpdateSetWriter.push that returns a per-record
response containing `{"error": "duplicate"}` for one record
**When** apply consumes the response
**Then** that record's `AppliedAction == FAILED` and
`error_message` contains the SN error text. Other records remain
REQUESTED.

AC8 (sys_update_set provenance metadata):
**Given** a happy-path apply
**When** the engine creates the sys_update_set
**Then** the `description` JSON contains:
* `nexus.template_id`
* `nexus.template_version`
* `nexus.nexus_version`
* `nexus.git_sha` (best-effort; may be `"unknown"`)
* `nexus.applied_at` (UTC ISO timestamp)

AC9 (local apply.jsonl):
**Given** an apply completes (success OR partial failure)
**When** the engine returns
**Then** it has appended one JSON line to
`paths.jobs_dir / <job_id> / apply.jsonl` containing the full
ApplyResult serialized via `model_dump(mode="json")`. Idempotent
on retries (one line per apply call, never duplicated).

AC10 (purity at the ApplyEngine boundary):
**Given** ApplyEngine
**When** instantiated
**Then** all I/O collaborators are injected via the dataclass:
`sn_client: ServiceNowClientProtocol`, `paths: NexusPaths`,
`clock: Callable[[], UtcDatetime]`, `nexus_version: str`,
`git_sha: str`. Tests substitute fakes for each.

AC11 (FakeApplyEngine + FakeServiceNowClient sufficient for tests):
**Given** test fakes only
**When** ApplyEngine is tested
**Then** all paths covered without mocks. (Note: `tests/fakes/
fake_sn_client.py:FakeServiceNowClient` exists and is the
canonical fake.)

AC12 (type strictness):
**Given** the new files
**When** pyright strict + mypy strict run
**Then** 0 errors. No `# type: ignore`.

## Must NOT

* Must NOT use `unittest.mock` -- inject fakes only.
* Must NOT bypass Gate 1 / Gate 2 -- that wiring is Story 06's
  responsibility. ApplyEngine has no gate awareness.
* Must NOT call `os.environ` directly. The nexus_version + git_sha
  fields are passed in.
* Must NOT use `uuid.uuid4()` for the update_set_sys_id (let SN
  generate it server-side and return it).
* Must NOT swallow exceptions from `sn_client.create_record` --
  let them propagate to the orchestrator.
* Must NOT update the sys_update_set state (in_progress vs complete
  vs ...). That decision is deferred.

## Tasks / Subtasks

* [ ] Populate `src/nexus/assessment/context.py:ApplyResult`
      (replace the empty placeholder) (AC1)
* [ ] Create `src/nexus/templates/results.py` -- AppliedAction +
      AppliedRecord (AC2)
* [ ] Create `src/nexus/templates/errors.py` extension:
      `ScopeNotFoundError(slug)` (AC6)
* [ ] Replace `src/nexus/templates/apply.py` stub with ApplyEngine
      dataclass + `apply(...)` method (AC3-AC10)
* [ ] Verify `FakeServiceNowClient` covers `create_record("sys_scope"...)`
      and `create_record("sys_update_set"...)`; extend if needed (AC11)
* [ ] Create `tests/templates/test_apply_engine_happy_path.py` (AC4, AC8)
* [ ] Create `tests/templates/test_apply_engine_scope_resolution.py`
      (AC5, AC6)
* [ ] Create `tests/templates/test_apply_engine_failed_record.py` (AC7)
* [ ] Create `tests/templates/test_apply_engine_jsonl.py` (AC9)
* [ ] Update `src/nexus/templates/__init__.py` re-exports
* [ ] Update `.ratchet.json` baselines

## Existing Code

* Stories 01-04: schemas + document loader + renderer
* `src/nexus/assessment/context.py:ApplyResult` (placeholder)
* `src/nexus/connectors/servicenow/protocol.py:ServiceNowClientProtocol`
* `src/nexus/capture/update_set.py:UpdateSetWriter`
* `src/nexus/config/paths.py:NexusPaths` (has `jobs_dir`)
* `tests/fakes/fake_sn_client.py:FakeServiceNowClient`

## Dev Notes

### Modules Affected

* `src/nexus/assessment/context.py` (populate ApplyResult)
* `src/nexus/templates/apply.py` (replace stub)
* `src/nexus/templates/results.py` (new)
* `src/nexus/templates/errors.py` (extend with ScopeNotFoundError)
* `src/nexus/templates/__init__.py` (re-exports)
* `tests/templates/test_apply_engine_*.py` (4 files)

### ApplyEngine shape

```python
@dataclass(slots=True, frozen=True)
class ApplyEngine:
    sn_client: ServiceNowClientProtocol
    paths: NexusPaths
    clock: Callable[[], UtcDatetime]
    nexus_version: str
    git_sha: str

    def apply(self, template_path: Path) -> ApplyResult:
        doc = load_template_document(template_path)
        scope_id = self._resolve_scope(doc.target_scope)
        records = render_to_records(doc, scope_id, self.clock())
        update_set_sys_id, update_set_name = self._create_update_set(doc)
        update_set_writer = UpdateSetWriter(self.sn_client)
        push_results = update_set_writer.push(records, update_set_sys_id)
        applied = self._classify_records(records, push_results)
        result = ApplyResult(
            update_set_sys_id=update_set_sys_id,
            update_set_name=update_set_name,
            template_id=doc.id,
            template_version=doc.version,
            target_scope_sys_id=scope_id,
            applied_records=applied,
            instance_id=self.sn_client.instance_id,
            started_at=...,
            completed_at=self.clock(),
        )
        self._write_jsonl(result)
        return result
```

### Failed-record predicate

```python
def _is_failed(response: dict[str, object]) -> bool:
    if response.get("error") is not None:
        return True
    status = response.get("http_status")
    if isinstance(status, int) and status >= 400:
        return True
    return False
```

### Testing Approach

* Inject `FakeServiceNowClient`, `clock=lambda: NOW`, deterministic
  `nexus_version` + `git_sha`. Construct templates via
  `tests/fakes/templates.py`.
* Verify ApplyResult equality with hand-built expected instance.
* Smoke-test the `apply.jsonl` write to `tmp_path`-rooted NexusPaths.

### Conventions

* `@dataclass(slots=True, frozen=True)` for ApplyEngine
* Pydantic frozen for ApplyResult, AppliedRecord
* `StrEnum` for AppliedAction
* No mocks; injected fakes

## References

* Stories 01-04
* PRD: `.primer/prd/PRD-003-nexus-template-library.md#In Scope`
* Brainstorming: `.primer/brainstorming/2026-05-19-nexus-template-library.md#Recommendation 5`
* `src/nexus/capture/update_set.py:UpdateSetWriter`
* `tests/fakes/fake_sn_client.py:FakeServiceNowClient`
