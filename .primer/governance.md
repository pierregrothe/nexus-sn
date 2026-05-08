# Governance

## Enforcement Gates

### Tier 1 -- Blocking (pre-edit hook, prevents file write)

File-aware checks the regex hook still owns:
- no-sys-argv -- blocks sys.argv indexing outside test files
- no-bare-any-in-sig -- blocks : Any or -> Any in function signatures (ADR-008)
- no-dict-any-in-sig -- blocks dict[str, Any] in function signatures (ADR-008)

### Tier 1 -- Blocking (ruff lint, fails post-edit and pre-commit)

- no-mocks -- ruff banned-api on unittest.mock and pytest_mock
- no-relative-imports -- ruff ban-relative-imports = "all"
- no-bare-except -- ruff E722
- no-deferred-import -- ruff PLC0415 (ADR-016)
- no-type-ignore -- ruff PGH003 (ADR-007)

### Tier 1 -- Blocking (semgrep, semantic governance, ADR-016 + ADR-017)

- no-lru-cache-none -- @lru_cache(maxsize=None) is forbidden, use @cache
- no-unittest-testcase -- class X(TestCase) is forbidden in tests/, use pytest functions
- caching-must-use-cached-decorator -- @cache, @lru_cache, @cached_property forbidden in src/nexus/ (ADR-017)
- cached-requires-explicit-ttl -- @cached without ttl= is forbidden (ADR-017)
- cached-persist-requires-namespace -- @cached(persist=True) without namespace= is forbidden (ADR-017)

### Tier 2 -- Ratchet (post-edit hook, blocks if metrics worsen)

- coverage-ratchet -- per-module covered lines can only increase (ADR-009)
  Baseline: .ratchet.json (updated when coverage improves)

### Tier 3 -- Soft (post-edit warning, never blocks)

- missing-test-file -- warns if src/nexus/X/Y.py edited without tests/
- resource-open -- warns if file handle / logging handler opened in test without close

### Post-edit checks (runs after every Python file write, blocking)

- ruff-check -- lint (ruff check on edited file)
- mypy -- type check (mypy on edited file) -- ADR-012
- pyright -- type check (pyright on edited file) -- ADR-012

### CI (every push, lint only)

- black-check -- formatting (black --check src/nexus/ tests/)
- ruff-check -- lint (ruff check src/nexus/ tests/)
- mypy -- type check (mypy src/nexus/) -- ADR-012
- pyright -- type check (pyright src/nexus/) -- ADR-012

### CI release tags only (full test suite)

- pytest -- cross-platform (ubuntu, macos, windows), Python 3.14 -- ADR-013

### Pre-commit (blocks local commit)

- pytest -- full test suite (poetry run pytest -q --override-ini="addopts=")

## Agent-Enforced Rules

- calver -- CalVer YYYY.0M.PATCH; version set manually in pyproject.toml
- file-headers -- new Python files: # path, # description, # Author, # Date
- docstrings -- Google-style docstrings on all public functions, classes, methods
- module-exports -- every module declares explicit __all__
- pydantic-frozen -- ConfigDict(frozen=True, strict=True, extra="forbid")
- utc-only -- datetime.now(UTC); no naive datetimes
- slots-dataclass -- @dataclass(slots=True) for structured data
- enum-dispatch -- match/case with case _: default
- no-print -- logging.getLogger(__name__) in library code
- secrets-keychain -- secrets in OS keychain only
- layer-order -- config < auth < capabilities < api/connectors < agents/... < cli
- test-naming -- test_<function>_<scenario> convention
- 100-coverage -- 100% line coverage target for implemented modules
- behavioral-tests -- tests must assert on behavior, not just side effects (ADR-009)

## ADR Catalog

| ADR | Title | Enforcement | Status |
|-----|-------|-------------|--------|
| 001 | API-direct architecture | none | accepted (partial supersede ADR-015) |
| 002 | Template distribution via GitHub sync | agent | accepted |
| 003 | Assessment 3-gate model | agent | accepted |
| 004 | CalVer versioning (YYYY.0M.PATCH) | agent | accepted |
| 005 | Connector plugin system | agent | accepted |
| 006 | Python 3.14 minimum | hook | accepted |
| 007 | Zero type: ignore tolerance | blocking hook | accepted |
| 008 | Type annotation completeness | blocking hook + pyright | accepted |
| 009 | Behavioral test completeness | ratchet | accepted |
| 010 | Resource lifecycle in tests | soft hook | accepted |
| 011 | 3-tier enforcement model | governance doc | accepted |
| 012 | Dual type checking (mypy + pyright) | blocking hook + CI | accepted |
| 013 | Lean CI for solo developer | ci.yml | accepted |
| 015 | Migrate from anthropic SDK to claude-agent-sdk | none | accepted |
| 016 | Semgrep for semantic governance rules | semgrep + pre-commit | accepted |
| 017 | Single canonical caching decorator (@cached) | semgrep + python | accepted |
| 018 | Tier detection from Claude Code OAuth + org MCP config | none | accepted |

Full ADR files: .primer/adr/
