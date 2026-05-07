# Governance

## Enforcement Gates

### Pre-edit -- Claude Code hooks (blocks Claude writes)
- no-mocks -- blocks unittest.mock, MagicMock, @patch, pytest_mock (pre-edit-validate.py)
- no-relative-imports -- blocks from .module style (pre-edit-validate.py)
- no-bare-except -- blocks bare except: clauses (pre-edit-validate.py)
- no-lru-cache-none -- blocks @lru_cache(maxsize=None), use @cache (pre-edit-validate.py)
- no-unittest-testcase -- blocks class Foo(TestCase) in test files (pre-edit-validate.py)
- no-sys-argv -- blocks sys.argv indexing outside test files (pre-edit-validate.py)
- post-edit-ruff -- runs ruff check after every Python file write (post-edit-lint.py)
- post-edit-mypy -- runs mypy after every Python file write (post-edit-lint.py)

### CI (blocks merge to main)
- black-check -- formatting check (black --check src/nexus/ tests/)
- ruff-check -- lint check (ruff check src/nexus/ tests/)
- mypy -- type check (mypy src/nexus/)
- pytest -- test suite, cross-platform (ubuntu, macos, windows, Python 3.12)

## Agent-Enforced Rules

Rules with no automated gate -- agent convention only.

- calver -- CalVer YYYY.0M.PATCH; version set manually in pyproject.toml
- file-headers -- new Python files: # path, # description, # Author, # Date
- docstrings -- Google-style docstrings on all public functions, classes, methods
- module-exports -- every module declares explicit __all__
- pydantic-frozen -- ConfigDict(frozen=True) unless mutation required
- utc-only -- datetime.now(UTC); no naive datetimes
- slots-dataclass -- @dataclass(slots=True) for structured data
- enum-dispatch -- match/case for enum dispatch; always include case _: default
- no-print -- logging.getLogger(__name__) in library code; no print()
- secrets-keychain -- secrets in OS keychain only; never in config files
- layer-order -- no imports from higher layers (config < auth < capabilities
                   < api/connectors < agents/.../templates/assessment/execution < cli)
- test-naming -- test_<function>_<scenario> convention
- 100-coverage -- 100% line coverage; enforced by CI but not hard-blocked at write time

## ADR Catalog

| ADR | Title | Enforcement | Status |
|-----|-------|-------------|--------|
| 001 | API-direct architecture (no Claude Code dependency) | none | accepted |
| 002 | Template distribution via GitHub sync | agent | accepted |
| 003 | Assessment 3-gate model | agent | accepted |
| 004 | CalVer versioning (YYYY.0M.PATCH) | agent | accepted |
| 005 | Connector plugin system | agent | accepted |

Full ADR files: .primer/adr/
