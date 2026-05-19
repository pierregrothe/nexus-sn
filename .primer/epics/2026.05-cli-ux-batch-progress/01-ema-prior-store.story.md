# Story 01: EmaPriorStore + EmaSample JSONL persistence

Status: done
Spec-Clarity: high
Depends-On: none

## Story

As a NEXUS user kicking off a batch plugin upgrade,
I want NEXUS to remember how long previous upgrades in the same
family took,
so that the next batch's ETA is informed by history rather than
guessing forever.

## Acceptance Criteria

AC1 (EmaSample model):
**Given** the need to persist per-family duration history
**When** Story 01 ships
**Then** `src/nexus/ui/components/eta_store.py` exports an
`EmaSample(BaseModel)` with `frozen=True, strict=True,
extra="forbid"`, fields: `family: str`, `duration_s: float`,
`ts: UtcDatetime`.

AC2 (path helper):
**Given** the cache path is project-defined
**When** Story 01 ships
**Then** `src/nexus/config/paths.py` exposes
`NexusPaths.eta_prior_cache_path() -> Path` returning
`<cache_dir>/eta_prior.jsonl`. `cache_dir` lives under the
existing `~/.nexus/` root.

AC3 (record appends JSONL):
**Given** an `EmaPriorStore(cache_path=tmp_path/eta_prior.jsonl)`
**When** the user calls `store.record("plugin_family",
duration_s=42.0)`
**Then** the file gains a line
`{"family": "plugin_family", "duration_s": 42.0, "ts":
"2026-05-18T...Z"}` (UTC ISO).

AC4 (mkdir-or-exist):
**Given** `~/.nexus/cache/` does not exist on disk
**When** `store.record(...)` is called for the first time
**Then** the parent directory is created (`parents=True,
exist_ok=True`); no `FileNotFoundError` leaks.

AC5 (load filters by family):
**Given** the JSONL file contains 5 entries: 3 family=A, 2
family=B
**When** `store.load("A")` runs
**Then** the return value is a `tuple[float, ...]` of length 3
containing only the A durations, in file order.

AC6 (load caps at 1000):
**Given** the file contains 1500 entries all family=A
**When** `store.load("A")` runs
**Then** the return value has length 1000 (the most-recent 1000
in file order). The file is unchanged.

AC7 (load skips malformed lines):
**Given** the file contains 3 valid JSON lines plus 1 truncated
line at the end (partial JSON from a killed process)
**When** `store.load("X")` runs
**Then** the return value contains the valid X-family entries
ONLY; the malformed line is silently skipped; no exception leaks.

AC8 (load returns empty on missing file):
**Given** the JSONL file does not exist
**When** `store.load("X")` runs
**Then** the return value is `()` (empty tuple); no exception.

AC9 (in-process multi-thread safety):
**Given** two threads, each calling `store.record("X", float(i))`
50 times concurrently
**When** both threads complete
**Then** the file contains exactly 100 lines; loading family X
returns 100 durations.

AC10 (Windows cross-process is documented as out of scope):
**Given** the EmaPriorStore docstring
**When** a reader inspects the class
**Then** the docstring includes a "Limitations" section noting
that cross-process atomicity is NOT guaranteed on Windows (POSIX
O_APPEND semantics do not apply to `open('a')`); v1 covers
in-process multi-threaded only.

AC11 (no type ignore, frozen Pydantic, ASCII only):
**Given** the new files
**When** pyright strict + mypy strict + ruff + black run
**Then** all report 0 errors. No `# type: ignore`. All Pydantic
models use `frozen=True, strict=True, extra="forbid"`.

## Must NOT

* Must NOT add asyncio / threading.Lock around the write path.
  In-process safety is provided by the GIL serializing `os.write`
  on append-mode file descriptors.
* Must NOT claim cross-process atomicity. The docstring states the
  limitation; AC10 enforces.
* Must NOT use `dict[str, Any]` in public signatures.
* Must NOT add a TTL or rotation mechanism. The 1000-entry cap is
  enforced at load time, not write time.
* Must NOT cache the loaded prior list in memory across calls.
  Each `load(family)` re-reads the file.

## Tasks / Subtasks

* [ ] Create `src/nexus/ui/components/eta_store.py`:
  * [ ] File header per `~/.claude/rules/file-headers.md`
  * [ ] `EmaSample(BaseModel)` with fields family / duration_s / ts
  * [ ] `EmaPriorStore(BaseModel)` with `cache_path: Path` field
  * [ ] `record(family: str, duration_s: float) -> None`
        method that:
    * mkdirs `cache_path.parent` with `parents=True, exist_ok=True`
    * opens with `cache_path.open("a", encoding="utf-8")`
    * writes one JSON line + `\n`, flushes
  * [ ] `load(family: str) -> tuple[float, ...]` method that:
    * returns `()` if file missing
    * iterates lines, JSON-parses each, skips malformed via
      `try/except json.JSONDecodeError, ValidationError`
    * filters by family
    * returns last 1000 durations as tuple
  * [ ] `__all__ = ["EmaPriorStore", "EmaSample"]`
* [ ] Extend `src/nexus/config/paths.py`:
  * [ ] Add `eta_prior_cache_path(self) -> Path` method on
        `NexusPaths` returning `cache_dir / "eta_prior.jsonl"`
  * [ ] Verify `cache_dir` is already defined; if not, add it
        (returns `root / "cache"`)
* [ ] Create `tests/test_ema_prior_store.py`:
  * [ ] `test_record_appends_jsonl_line_with_utc_timestamp`
  * [ ] `test_record_creates_cache_dir_when_missing`
  * [ ] `test_load_filters_by_family`
  * [ ] `test_load_returns_empty_tuple_when_file_missing`
  * [ ] `test_load_caps_at_1000_entries`
  * [ ] `test_load_skips_malformed_jsonl_lines`
  * [ ] `test_record_concurrent_threads_preserve_all_records`
        (2 threads x 50 writes each)
  * [ ] `test_emasample_rejects_extra_fields` (extra="forbid"
        sanity)
* [ ] Update `.ratchet.json` with baseline for new module
* [ ] Update `src/nexus/ui/components/__init__.py` exports

## Existing Code

* `src/nexus/config/paths.py` -- extend with one helper.
* `src/nexus/config/types.py:UtcDatetime` -- reuse as `ts` type.
* `tests/conftest.py` -- existing `tmp_path` fixture is sufficient;
  no new conftest changes needed.

## Dev Notes

### Concurrent-write test pattern

```python
import threading

def test_record_concurrent_threads_preserve_all_records(tmp_path):
    store = EmaPriorStore(cache_path=tmp_path / "eta.jsonl")
    barrier = threading.Barrier(2)
    def worker():
        barrier.wait()
        for i in range(50):
            store.record("X", float(i))
    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads: t.start()
    for t in threads: t.join()
    samples = store.load("X")
    assert len(samples) == 100
```

### Malformed-line test pattern

```python
def test_load_skips_malformed_jsonl_lines(tmp_path):
    path = tmp_path / "eta.jsonl"
    path.write_text(
        '{"family":"A","duration_s":1.0,"ts":"2026-01-01T00:00:00Z"}\n'
        '{"family":"A","duration_s":2.0,"ts":"2026-01-01T00:00:01Z"}\n'
        '{partial\n',  # malformed
        encoding="utf-8",
    )
    store = EmaPriorStore(cache_path=path)
    assert store.load("A") == (1.0, 2.0)
```

### Conventions

* Absolute imports (`from nexus.ui.components.eta_store import ...`)
* UTC timestamps via `datetime.now(UTC).isoformat()` (or model
  `UtcDatetime` field)
* 100% line coverage; pyright strict + mypy strict 0; no
  `# type: ignore`
* ASCII only

## References

* PRD: `.primer/prd/PRD-001-cli-ux-wow-factor.md` (EmaPriorStore
  section + Constraints)
* Brainstorming: `.primer/brainstorming/2026-05-18-cli-ux-implementation-plan.md`
* Original story: `.primer/stories/2026.05.02-cli-batch-progress-eta.md`
  (AC7-AC9; v2 spec retains AC7-AC9, replaces AC8 wording from
  "concurrent invocations" to "concurrent threads in-process")
* Sync epic decisions:
  `.primer/decisions.md` (wire-vs-cached split precedent +
  "real I/O over mock I/O" doctrine)
