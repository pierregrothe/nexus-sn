# Story 05: Idempotent provision_oauth + PromptSource injection

Status: backlog
Spec-Clarity: high
Depends-On: 01

## Story

As a NEXUS user whose first `nexus setup` run got Ctrl-C-ed between
OAuth-entity creation on SN and local token storage,
I want re-running `nexus setup` to detect the existing
`oauth_entity_profile` on the SN side and reuse it,
so that I do not accumulate orphaned `oauth_entity_profile` records on
the instance every time the wizard is interrupted.

## Acceptance Criteria

AC1:
**Given** SN has NO existing `oauth_entity_profile` with the
deterministic name `nexus-cli-<sanitized-hostname>`
**When** `provision_oauth(client, prompts, host, ...)` runs
**Then** it creates a new `oauth_entity_profile`, returns its
`(client_id, client_secret)`, and a new record is visible in SN with
that name.

AC2:
**Given** SN already has an `oauth_entity_profile` with the deterministic
name (created by a prior interrupted run)
**When** `provision_oauth(...)` runs against the same host
**Then** it does NOT create a duplicate, returns the existing
`client_id`, and either (a) reuses the stored `client_secret` if still
available in keychain, or (b) rotates the secret on the SN side and
returns the new pair. Whichever branch is taken, the count of
`oauth_entity_profile` records on SN does not grow.

AC3:
**Given** `provision_oauth` previously called `typer.prompt` directly
**When** the refactored signature takes a `PromptSource` parameter
**Then** all manual-fallback prompts (when Basic-auth provisioning
fails) route through `prompts.ask(...)` instead of `typer.prompt`. The
public Typer command callers pass `TyperPromptSource()`; tests pass
`ScriptedPromptSource([...])`.

AC4:
**Given** the deterministic name is computed from `host`
**When** `host` contains characters not allowed in SN entity names
(dots, colons, slashes from a URL)
**Then** a helper function sanitizes the hostname before composing the
name (lowercase, replace non-alphanumeric with `-`, collapse runs of
`-`, strip leading/trailing `-`, cap at 32 chars), and the same
sanitized name is produced deterministically across runs.

## Must NOT

- Must NOT change the return type of `provision_oauth` (callers in
  `instance_register` and the new wizard expect the same shape).
- Must NOT delete pre-existing entities that don't match the
  deterministic name -- only the named one is owned by NEXUS.
- Must NOT log `client_secret` at any level (verify by grepping the
  diff for `logger\..*secret`).
- Must NOT call `typer.prompt` directly anywhere in `cli/oauth.py`
  after this story (rule: all prompts via `PromptSource`).

## Tasks / Subtasks

- [ ] Add helper `_sanitize_oauth_entity_name(host: str) -> str` to
      `src/nexus/cli/oauth.py` (AC: 4)
- [ ] Add helper `find_oauth_entity(client, name) -> dict[str, object] | None`
      to `src/nexus/cli/oauth.py` (AC: 2)
  - [ ] Queries `/api/now/table/oauth_entity_profile?sysparm_query=name=<name>`
        via the existing SN client
  - [ ] Returns the first match or None; never raises on 404
- [ ] Refactor `provision_oauth` signature to take `prompts: PromptSource`
      and call `find_oauth_entity` BEFORE attempting to create
      (AC: 1, 2, 3)
  - [ ] If found: branch (a) reuse keychain secret or (b) rotate via
        SN. Pick (b) for v1 -- simpler, no keychain coupling here
  - [ ] All manual-fallback prompts route through `prompts.ask`
- [ ] Update `print_oauth_setup` and any other callers in
      `cli/oauth.py` that called `typer.prompt`
- [ ] Refactor `commands_instance.py:instance_register` to pass
      `TyperPromptSource()` to `provision_oauth` (no behavior change in
      that command; story 06 will fully convert it)
- [ ] Update `tests/test_cli_oauth.py` (AC: 1-4)
  - [ ] `TestProvisionOauthCreateWhenAbsent`: AC1
  - [ ] `TestProvisionOauthReuseWhenPresent`: AC2 -- count assertion via
        fake SN client that records create calls
  - [ ] `TestProvisionOauthPromptSourceWiring`: AC3 -- scripted prompts
        consumed in order
  - [ ] `TestSanitizeOauthEntityName`: AC4 -- table per sanitization
        rule
- [ ] Extend `tests/fakes/fake_sn_client.py` with an
      `oauth_entity_profiles` registry and a `query` method backing
      `find_oauth_entity`

## Existing Code

- `src/nexus/cli/oauth.py:40-102` -- `provision_oauth` (Basic-auth
  path), `warn_token_cap` (silent network swallow). REFACTOR.
- `src/nexus/cli/oauth.py:247-306` -- manual-prompt fallback. REFACTOR
  prompts to `PromptSource`.
- `src/nexus/cli/commands_instance.py:376-440` -- `instance_register`,
  CALLER. Update to pass `TyperPromptSource()`.
- `src/nexus/instances/oauth.py:42-94` -- `SNOAuthClient.exchange`,
  UNCHANGED.

## Dev Notes

### Modules Affected

- `src/nexus/cli/oauth.py`
- `src/nexus/cli/commands_instance.py` (signature touch only, no logic
  change in this story)
- `tests/test_cli_oauth.py`
- `tests/fakes/fake_sn_client.py`

### Testing Approach

- Class-based pytest tests (`TestProvisionOauth*`, `TestSanitizeOauthEntityName`).
  Real `FakeSNClient` with an in-memory `oauth_entity_profiles` table
  that supports `create` + `query`. Count assertions verify idempotence.
- `ScriptedPromptSource` from story 01 drives manual-fallback prompts.
- No mocks anywhere. Grep the test file for `mock` / `MagicMock` to
  verify.

### Conventions

- `PromptSource` injection (story 01 dependency).
- Python 3.14: `match/case` for branching on found-vs-absent if it
  improves clarity.
- Type hints on every new function (mypy strict + pyright strict
  enforced).

## References

- Brainstorming: `.primer/brainstorming/2026-05-18-nexus-setup-credential-wizard.md`,
  section "Failure-mode handling" row 1 + Adversarial Review item 1
- Existing: `src/nexus/cli/oauth.py:40-306`
