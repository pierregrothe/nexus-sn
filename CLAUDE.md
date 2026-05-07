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

- Python 3.12+. Do NOT use Python 3.14-only syntax (PEP 758, Path.copy, etc.).
- Package manager: Poetry.
- Line length: 100. Formatter: black. Linter: ruff. Type checker: mypy strict.
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
