# NEXUS -- Project Instructions for Claude Code

## Project summary

NEXUS is a standalone Python CLI tool that acts as a ServiceNow AI architect agent.
It uses the Anthropic API directly (no Claude Code dependency), ships as a pip package,
and runs identically on Windows, macOS, and Linux.

Key concepts:
- Templates are declarative YAML artifacts versioned in this GitHub repo.
- The local tool syncs against the registry, validates against Pydantic schemas,
  and applies templates through an AI-assisted execution engine.
- ServiceNow enterprise MCP servers (Value Melody, SSC, BT1, etc.) are probed at
  startup. Features requiring unavailable servers are disabled transparently.

## Standards (from skills-dev)

- Python 3.14+. All Python 3.14 syntax is permitted including PEP 758 (unparenthesized multi-except).
- Package manager: Poetry.
- Line length: 100. Formatter: black. Linter: ruff. Type checkers: mypy strict + pyright strict (both must report 0 errors).
  No # type: ignore anywhere. For untyped packages add stubs to src/stubs/.
- Versioning: CalVer (YYYY.0M.PATCH).
- No mocks. Use fakes in tests/fakes/.
- 100% line coverage. mypy strict: 0 errors. ruff: 0 violations.
- Test naming: test_<function>_<scenario>.
- Logging: log = logging.getLogger(__name__) at module level. No print() in library code.
- Secrets: OS keychain via keyring. Env vars as CI override. Never in config files.
- Absolute imports only. No relative imports.
- Bare except clauses are blocked by pre-edit hook.
- @cache over @lru_cache(maxsize=None).
- @dataclass(slots=True) for structured data.
- match/case for enum dispatch (always include case _: default).

## Enforcement Model

Three tiers. All checks run automatically via Claude Code hooks.

**Tier 1 -- Blocking (pre-edit hook, PostToolUse):** Fails before file is written.
  Rules: no-mocks, no-relative-imports, no-bare-except, no-lru-cache-none,
         no-unittest-testcase, no-sys-argv, no-type-ignore, no-bare-any-in-sig,
         no-dict-any-in-sig, no-deferred-import

**Tier 2 -- Ratchet (.ratchet.json, tracked in post-edit hook):** Coverage and
  complexity metrics can only decrease, never increase. (Baseline file: Plan 2)

**Tier 3 -- Soft (post-edit warning):** Advisory only, never blocks.
  Rules: missing-test-file, unclosed-resource-handle (Plan 2)

## Pydantic Conventions

All Pydantic models use frozen + strict + no-extra:

```python
model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
```

Fields with constraints use `Annotated[Type, Field(...)]`.
Cross-field validators use `@model_validator(mode="after")` and return `Self`.
No `dict[str, Any]` in Pydantic model definitions -- use TypedDicts for complex fields.

## Architecture

See docs/superpowers/specs/2026-05-07-nexus-design.md for the full design spec.

Layer dependency order (lower layers have no imports from higher):
  1. config/
  2. auth/
  3. capabilities/
  4. api/ + connectors/
  5. agents/ + knowledge/ + templates/ + assessment/ + execution/
  6. cli.py
  7. ui/ (optional)

## Hooks

- PreToolUse: .claude/hooks/pre-edit-validate.py -- blocks anti-patterns
- PostToolUse: .claude/hooks/post-edit-lint.py -- runs ruff + mypy after every edit

## Layout

src/nexus/     -- Python package source (src layout)
tests/         -- pytest suite, fakes in tests/fakes/
templates/     -- community template library (YAML)
docs/          -- design spec, contributing guide, ADRs

## File headers

Every new Python file must start with:
  # src/nexus/path/to/file.py
  # Brief one-line description
  # Author: Pierre Grothe
  # Date: YYYY-MM-DD

## Template contribution

Templates live in templates/ at the repo root.
Each template type has a Pydantic schema in src/nexus/templates/schemas/.
CI validates all YAML on PR via .github/workflows/validate-templates.yml.
See docs/CONTRIBUTING.md for the contribution process.
