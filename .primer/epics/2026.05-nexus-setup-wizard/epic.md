# Epic: nexus setup credential wizard (v1)

Phase: 2026.05-setup-sync
Status: planned

## Goal

Ship `nexus setup` as an idempotent, fail-fast credential wizard that
orchestrates existing auth primitives (`provision_oauth`,
`SNOAuthClient.exchange`, `InstanceRegistry.register`, `KeychainClient`)
behind a testable prompt abstraction.

## Source

- Brainstorming: `../../brainstorming/2026-05-18-nexus-setup-credential-wizard.md`
- Roadmap phase: 2026.05-setup-sync, item `nexus-setup-command`

## Requirements Inventory

### Functional Requirements

- FR1 (idempotent re-run): If `~/.nexus/instances/` has at least one valid
  profile, `nexus setup` prints a summary panel and exits 0 without
  re-prompting. [Source: brainstorming Recommendation 4]
- FR2 (fail-fast on keychain): If `keyring.get_keyring()` returns a
  fail/null backend, `nexus setup` exits 1 with a distro-specific hint
  before any prompt. [Source: brainstorming Key Insight 3]
- FR3 (no SN orphans on Ctrl-C): `provision_oauth` is idempotent on a
  deterministic OAuth entity name; resume after interruption reuses the
  existing entity. [Source: brainstorming Recommendation 5]
- FR4 (testable prompts, no-mocks): All prompts route through a
  `PromptSource` Protocol; tests use `ScriptedPromptSource`, never
  `unittest.mock`. [Source: brainstorming Recommendation 2]
- FR5 (inline reauth): If a profile exists but keychain tokens are missing,
  `nexus setup` re-prompts password and re-runs `exchange` inline.
  [Source: brainstorming Recommendation 4]
- FR6 (surface corrupted profiles): If a profile dir exists but
  `meta.json` is malformed, surface the path + reason instead of silently
  skipping. [Source: brainstorming Recommendation 4]
- FR7 (reject path-traversal in profile names): `validate_profile_name`
  rejects `../`, `\`, leading `.`, names > 64 chars, and non-`[A-Za-z0-9_-]`
  characters. [Source: brainstorming failure-mode table]

### Non-Functional Requirements

- NFR1: 0 errors mypy strict + pyright strict. [Source: CLAUDE.md]
- NFR2: No `unittest.mock` / `MagicMock`. [Source: CLAUDE.md, .claude/rules/no-mocks.md]
- NFR3: Python 3.14 syntax: `|` unions, `match/case`, PEP 758 multi-except.
  [Source: .claude/rules/python-314.md]
- NFR4: Pydantic models stay `frozen=True, strict=True, extra="forbid"`.
  [Source: CLAUDE.md]
- NFR5: ASCII only. File headers + Google docstrings + `__all__`.
  [Source: global rules]
- NFR6: File-size cap 800 src / 1400 tests. [Source: ADR-023]

### Constraints

- C1: OS keychain via `keyring` only; no encrypted file fallback.
  [Source: CLAUDE.md]
- C2: Pre-edit hook blocks bare `except`, relative imports, `dict[str, Any]`
  in signatures. [Source: enforcement model in CLAUDE.md]

## Stories

| #  | Title                                                | Clarity | Depends-On | Status  |
|----|------------------------------------------------------|---------|------------|---------|
| 01 | PromptSource protocol + impls                        | high    | none       | backlog |
| 02 | KeychainClient.check_available() fail-fast probe     | high    | none       | backlog |
| 03 | validate_profile_name() input validator              | high    | none       | backlog |
| 04 | InstanceRegistry.scan_profile_dirs() corrupted-aware | high    | none       | backlog |
| 05 | Idempotent provision_oauth + PromptSource injection  | high    | 01         | backlog |
| 06 | run_instance_setup helper (shared by register+setup) | high    | 01, 03, 05 | backlog |
| 07 | nexus setup command (gate + reauth + clean-slate)    | high    | 02, 04, 06 | backlog |

## Coverage Map

- FR1 -> 04, 07
- FR2 -> 02, 07
- FR3 -> 05
- FR4 -> 01, all callers (05, 06, 07)
- FR5 -> 02, 07
- FR6 -> 04, 07
- FR7 -> 03, 06
- NFR1..6 -> all stories

## Existing Code Reused (delta-only)

- `src/nexus/cli/commands_instance.py:376-440` (`instance_register`) ->
  becomes ~10 LOC wrapper around story-06 helper.
- `src/nexus/cli/oauth.py:247-306` (`provision_oauth`) -> add idempotent
  lookup-or-create + `PromptSource` parameter (story 5).
- `src/nexus/instances/registry.py:105-121` (`list_all`) -> stays
  unchanged; new `scan_profile_dirs` added (story 4).
- `src/nexus/auth/keychain.py:24-85` (`KeychainClient`) -> add
  `check_available` (story 2).
- `src/nexus/cli/commands_top.py:38` (setup stub) -> replaced by direct
  command definition in `commands_setup.py` (story 7).

## Progress

- Stories: 0/7 done, 0 in-progress, 7 backlog
