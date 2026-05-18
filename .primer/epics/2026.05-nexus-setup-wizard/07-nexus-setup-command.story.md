# Story 07: nexus setup command (gate + reauth + clean-slate + closing Notice)

Status: done
Spec-Clarity: high
Depends-On: 02, 04, 06

## Story

As a new NEXUS user running `nexus setup` for the first time,
I want a single command that probes the keychain, scans for existing
profiles, runs the appropriate flow (clean-slate setup, inline reauth,
or already-configured summary), and points me at `nexus sync` as the
next step,
so that I have one obvious entry point regardless of my current state.

## Acceptance Criteria

AC1 (clean slate):
**Given** keychain is available, `~/.nexus/instances/` is empty or
absent
**When** I run `nexus setup`
**Then** it prompts via `run_instance_setup` (story 06), writes a
profile, prints a `KeyValuePanel` of the new instance, and prints
`Notice("Next: run \`nexus sync\` to pull the template catalog.")`,
exiting 0.

AC2 (already configured):
**Given** keychain is available, at least one valid profile exists,
keychain tokens for that profile are present
**When** I run `nexus setup`
**Then** it prints a `KeyValuePanel` listing existing profiles, prints
a `Hint` pointing at `nexus instance register` / `nexus reauth` /
`nexus sync`, and exits 0 WITHOUT any prompt.

AC3 (inline reauth):
**Given** keychain is available, a profile exists in the registry,
but `KeychainClient.get` for that profile returns no access_token
**When** I run `nexus setup`
**Then** it prints `Notice("Tokens missing for profile <name>; re-auth required")`,
prompts password only (host/username come from `meta.json`), runs
`SNOAuthClient.exchange` to refresh tokens, persists them, prints a
"tokens restored" Notice, and exits 0.

AC4 (corrupted profile):
**Given** keychain is available, `~/.nexus/instances/broken/meta.json`
is malformed JSON
**When** I run `nexus setup`
**Then** it prints an error panel naming the path and reason from
`ScanResult.corrupted` (story 04), prints a hint to inspect/remove the
file, and exits non-zero. It does NOT enter clean-slate or reauth
paths.

AC5 (keychain unavailable):
**Given** `KeychainClient.check_available()` returns `Err(...)`
**When** I run `nexus setup`
**Then** it prints the distro-specific hint from the Err payload and
exits 1 BEFORE any prompt or registry scan.

AC6 (closing Notice always):
**Given** any successful exit path (AC1, AC3)
**When** the command finishes successfully
**Then** the last line printed is the
`"Next: run \`nexus sync\` to pull the template catalog."` Notice.

AC7 (Ctrl-C resume):
**Given** a prior `nexus setup` was interrupted between
`provision_oauth` and `exchange`, leaving an orphan `oauth_entity` on
SN but no profile locally
**When** I run `nexus setup` again
**Then** the second run takes the clean-slate path, `provision_oauth`
finds the existing SN entity by deterministic name (story 05), reuses
or rotates the secret, and completes registration. The SN
`oauth_entity_profile` count for the deterministic name stays at 1.

## Must NOT

- Must NOT auto-invoke `nexus sync` -- print the next-step Notice only.
- Must NOT prompt before the keychain probe and registry scan.
- Must NOT delete corrupted `meta.json` automatically -- surface and
  exit.
- Must NOT depend on `~/.nexus/config.yaml` existing
  (`ConfigManager.load` returns defaults without writing).
- Must NOT swallow exceptions from `run_instance_setup`; propagate as
  exit 1 with the Err message.

## Tasks / Subtasks

- [ ] Create `src/nexus/cli/commands_setup.py` (AC: 1-7)
  - [ ] File header + Google docstrings + `__all__`
  - [ ] Typer command `setup()` with no args (matches `commands_top.py`
        wiring expectations)
  - [ ] Flow:
        1. `KeychainClient.check_available()` -> Err: print + exit 1
        2. `registry.scan_profile_dirs()`
        3. If `scan.corrupted`: print panel, exit 1
        4. If `scan.valid` empty: clean-slate via
           `run_instance_setup` (story 06) -> print panel + closing
           Notice
        5. Else: per valid profile probe keychain token; if missing,
           run inline reauth; if all present, print summary + Hint
        6. Closing Notice on every successful path
- [ ] Implement private `_inline_reauth(profile, prompts, ...) -> Result[None, str]`
      (AC: 3)
- [ ] Replace `commands_top.py:38` stub with a re-export-or-rewire of
      `commands_setup.setup` (AC: 1)
- [ ] Update `help_text.py` setup entry to match new behavior
- [ ] Add `tests/test_cli_setup.py` (AC: 1-7)
  - [ ] `TestSetupCleanSlateHappyPath` (AC1)
  - [ ] `TestSetupIdempotentSkipWhenValidProfileExists` (AC2)
  - [ ] `TestSetupRunsInlineReauthWhenTokensMissing` (AC3)
  - [ ] `TestSetupSurfacesCorruptedProfileWithPath` (AC4)
  - [ ] `TestSetupFailsFastWhenKeychainUnavailable` (AC5)
  - [ ] `TestSetupClosingNoticePrintedOnSuccess` (AC6)
  - [ ] `TestSetupResumesAfterOauthEntityOrphan` (AC7)
  - [ ] `TestSetupHandlesWarnTokenCapNetworkErrorSilently` (adversarial
        review item)
  - [ ] `TestSetupRejectsInvalidProfileName` (rejection routed through
        story 03 validator; story 06 retries, this test verifies the
        command-level surface)

## Existing Code

- `src/nexus/cli/commands_top.py:38` -- `def setup()` stub raising
  `typer.Exit`. Replace.
- `src/nexus/cli/help_text.py:412-416` -- already advertises wizard
  semantics. Update wording to match shipped behavior (idempotent,
  fail-fast on keychain).
- All other primitives consumed are completed in stories 01-06.

## Dev Notes

### Modules Affected

- `src/nexus/cli/commands_setup.py` (new)
- `src/nexus/cli/commands_top.py` (rewire `setup`)
- `src/nexus/cli/help_text.py` (update entry)
- `tests/test_cli_setup.py` (new)

### Testing Approach

- Class-based pytest tests (`TestSetup*`). `typer.testing.CliRunner`
  drives the full command, with
  `ScriptedPromptSource` (story 01), `FakeKeychain` configurable for
  available/unavailable/missing-tokens (story 02), `FakeSNClient` with
  oauth_entity registry (story 05), and `tmp_path` for `instances_dir`.
- Each AC gets one focused test. Naming `test_<function>_<scenario>`.
- Verify exit codes via `CliRunner.invoke(...).exit_code`.
- Verify output content via Rich's `console.export_text()` or by
  redirecting Console to a `StringIO`.

### Conventions

- File header, Google docstrings, `__all__`.
- Synchronous Typer command; any async client wrapped with `asyncio.run`
  at the boundary.
- Python 3.14 `match/case` over the gate states (corrupted / empty /
  partial / full) is encouraged.

## References

- Brainstorming: `.primer/brainstorming/2026-05-18-nexus-setup-credential-wizard.md`,
  Recommendation 1 + Recommendation 4 + Closing message + entire
  Failure-mode table
- Existing stub: `src/nexus/cli/commands_top.py:38`
- Help text: `src/nexus/cli/help_text.py:412-416`
- Rule: `~/.claude/rules/file-size-management.md`
