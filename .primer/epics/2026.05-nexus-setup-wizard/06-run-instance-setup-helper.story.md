# Story 06: run_instance_setup helper (shared by instance register + setup)

Status: backlog
Spec-Clarity: high
Depends-On: 01, 03, 05

## Story

As a NEXUS developer maintaining both `nexus instance register` and
`nexus setup`,
I want the host/user/password/profile prompt + OAuth provisioning +
token exchange + registry write flow extracted into one synchronous
helper function,
so that both commands share one tested path and feature work (e.g.,
adding a new prompt) lands in exactly one place.

## Acceptance Criteria

AC1:
**Given** a fresh `instances_dir` and a working SN host
**When** `run_instance_setup(prompts, console, console_err, registry)`
is called with a scripted prompt source returning answers
`[host, username, password, profile_name]`
**Then** it returns an `Ok(InstanceMeta)` and `meta.json` exists at
`<instances_dir>/<profile_name>/meta.json` with tokens stored in the
keychain.

AC2:
**Given** the prompts deliver a profile name rejected by
`validate_profile_name` (story 03)
**When** the helper consumes that prompt
**Then** it re-prompts with a `Notice` listing allowed characters; the
test verifies the scripted source has the rejected answer plus a valid
follow-up answer, and the function returns Ok using the second answer.

AC3:
**Given** `provision_oauth` returns an error (e.g., Basic-auth
forbidden)
**When** `run_instance_setup` propagates that error
**Then** the helper returns `Err(...)` with the underlying message, no
`meta.json` is written, and no partial keychain entry remains.

AC4:
**Given** `nexus instance register` is invoked
**When** it executes
**Then** it constructs `TyperPromptSource()` and a `Registry` instance
and calls `run_instance_setup(...)`, doing nothing else of substance.
The original 65-LOC body becomes a ~10-LOC wrapper.

AC5:
**Given** any prior tests for `instance register`
**When** the refactor lands
**Then** those tests pass UNCHANGED if they tested observable behavior
(host/user prompted, profile written), or they are converted to use
`ScriptedPromptSource` if they were patching `typer.prompt`. Net test
count does not decrease.

## Must NOT

- Must NOT make the helper `async`. `instance_register` is synchronous;
  any async layer below (the HTTP client) is wrapped with `asyncio.run`
  at the Typer boundary. (Note: adversarial review caught this in v1.)
- Must NOT change the on-disk `meta.json` schema.
- Must NOT change `nexus instance register`'s CLI flags, help text, or
  exit codes.
- Must NOT couple to a specific `Console` impl -- accept the existing
  Rich console abstraction.

## Tasks / Subtasks

- [ ] Create `src/nexus/instances/wizard.py` (AC: 1, 2, 3)
  - [ ] File header, Google docstrings, `__all__`
  - [ ] Function signature:
        ```
        def run_instance_setup(
            prompts: PromptSource,
            console: Console,
            console_err: Console,
            registry: InstanceRegistry,
            keychain: KeychainClient,
            sn_client_factory: Callable[[str, str, str], SNClient],
        ) -> Result[InstanceMeta, str]:
        ```
  - [ ] Loop prompt-then-validate for profile name (AC: 2)
  - [ ] Call `provision_oauth(...)` from story 05
  - [ ] Call `SNOAuthClient.exchange(...)` and persist tokens via
        `keychain.set(...)`
  - [ ] Detect SN version (non-fatal); write `meta.json` after
  - [ ] Return Ok(meta) or Err(reason)
- [ ] Refactor `cli/commands_instance.py:instance_register` to call
      the helper (AC: 4)
  - [ ] Grep callers of `instance_register` before editing
  - [ ] Wrapper builds `TyperPromptSource()` + collaborators, calls
        helper, prints success/error
- [ ] Update `tests/test_cli_instance_register.py` (AC: 5)
  - [ ] Verify ScriptedPromptSource end-to-end happy path still passes
  - [ ] Add `TestRunInstanceSetupHelper` calling the helper directly
        with covering AC1-3
- [ ] Add `TestRunInstanceSetupProfileNameRetry` to cover AC2

## Existing Code

- `src/nexus/cli/commands_instance.py:376-440` -- the body to extract.
  ~65 LOC. After this story it is ~10 LOC.
- `src/nexus/cli/oauth.py:provision_oauth` -- called from helper
  (story 05 dependency).
- `src/nexus/instances/oauth.py:SNOAuthClient.exchange` -- called from
  helper, unchanged.
- `src/nexus/instances/registry.py:register` -- called from helper,
  unchanged.

## Dev Notes

### Modules Affected

- `src/nexus/instances/wizard.py` (new)
- `src/nexus/cli/commands_instance.py` (slim down)
- `tests/test_cli_instance_register.py` (refactor to scripted prompts)
- `tests/test_instances_wizard.py` (new, direct helper tests)

### Testing Approach

- Class-based pytest tests across two files: one driving via the Typer
  `CliRunner` end-to-end for `instance register`, one calling
  `run_instance_setup` directly with scripted collaborators.
- `tests/fakes/fake_sn_client.py` is the SN client factory.
- No `unittest.mock`. Grep verify.

### Conventions

- Synchronous function. Any async call sites use `asyncio.run`.
- `Result` return type from project's existing Result module.
- `PromptSource` injection.

## References

- Brainstorming: `.primer/brainstorming/2026-05-18-nexus-setup-credential-wizard.md`,
  Recommendation 3 + Adversarial Review note on async correction
- Existing: `src/nexus/cli/commands_instance.py:376-440`
- Rule: `~/.claude/rules/refactoring.md` (grep callers, checkpoint commits)
