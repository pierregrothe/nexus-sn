# Brainstorming: nexus setup credential wizard (v1)

Date: 2026-05-18
Mode: assumptions (research-driven, skipped technique rounds)
Techniques: assumptions-mode + adversarial-review
Trigger: `nexus setup` is the next implementation target per
`active.md` / `roadmap.md` (phase 2026.05-setup-sync). Today it
is a `NotImplementedError` stub at `commands_top.py:38`.

## Context Brief

NEXUS is a Python 3.14 CLI for ServiceNow architect work. Secrets
live in the OS keychain via the `keyring` package (CLAUDE.md
mandate). Pydantic conventions are frozen=True + strict=True +
extra=forbid across `InstanceMeta`, `NexusConfig`, etc.

Setup is orchestration, not new auth logic. Every primitive
already exists:

- `instance_register()` at `commands_instance.py:376-440` -- the
  closest prior art: prompts host/user/password, calls
  `provision_oauth()`, exchanges token via `SNOAuthClient.exchange`,
  writes `InstanceMeta` via `InstanceRegistry.register`.
- `provision_oauth()` at `cli/oauth.py:40` (and `:247-306` for the
  prompt + provisioning path) -- auto-creates SN OAuth app via
  Basic auth, prints manual instructions on failure.
- `KeychainClient` at `auth/keychain.py:24-85` -- wraps `keyring`.
- `InstanceRegistry.register/load/list_all` at `registry.py:48-121`.
- `ConfigManager.load()` at `config/manager.py:34-51` -- returns
  defaults without writing, so `~/.nexus/config.yaml` may not
  exist on a working install.
- Rich console + KeyValuePanel/Notice/Hint already in `ui/`.

## Key Insights

1. The wizard is orchestration over existing primitives, not new
   auth code. The new code is one command + idempotence + clean
   error story.
2. Idempotence is the v1 differentiator over `nexus instance
   register`. The boundary is `InstanceRegistry.scan_profile_dirs()`
   returning non-empty -- NOT `config.yaml` existence, which is
   unreliable.
3. Keychain availability must be probed before any prompt. Probe
   via `keyring.get_keyring()` returning `fail.Keyring` /
   `null.Keyring`. Fail-fast with distro-specific hint.
4. The wizard's job ends at "you have one working instance." Sync
   is named in the closing Notice but not invoked -- decouples
   setup's ship date from sync's.

## Recommendations

1. **New module** `src/nexus/cli/commands_setup.py`. Direct command
   definition replaces stub at `commands_top.py:38`. The stub
   raises `typer.Exit`, not `NotImplementedError`; no callers
   catch anything.
2. **New abstraction** `src/nexus/cli/prompts.py` defining a
   `PromptSource` Protocol with `ask(message, *, hide=False) ->
   str` and `confirm(message) -> bool`. Default
   `TyperPromptSource` wraps `typer.prompt`/`typer.confirm`. Test
   impl `ScriptedPromptSource` consumes a pre-loaded `deque[str]`.
   Required by the no-mocks rule -- `typer.prompt` cannot be
   patched and the existing tests can't drive the prompt path.
3. **Helper extraction** `src/nexus/instances/wizard.py:
   run_instance_setup(prompts, console, console_err) ->
   InstanceMeta` (synchronous, matches `instance_register`). Both
   `instance register` and `setup` call into it. Grep
   `instance_register` callers first.
4. **Idempotent gate** at top of `setup()`:
   - Probe keychain -> fail-fast if unavailable.
   - `scan = registry.scan_profile_dirs()`.
   - If `scan.corrupted`: surface error with path, exit 1.
   - If not `scan.valid`: clean-slate path.
   - For each valid profile, verify keychain tokens:
     - Missing -> inline reauth flow (re-prompt password, exchange
       with stored `client_id`/`client_secret`).
     - Present -> print summary panel + Hint, exit 0.
5. **Idempotent `provision_oauth`**: lookup-or-create on
   deterministic OAuth entity name (e.g., `nexus-cli-<hostname>`).
   Prevents orphaned `oauth_entity` on Ctrl-C between provisioning
   and token exchange.
6. **Closing message**: `Notice("Next: run \`nexus sync\` to pull
   the template catalog.")` on success.
7. **Tests** (`tests/test_cli_setup.py`):
   - `test_setup_clean_slate_happy_path`
   - `test_setup_idempotent_skip_when_valid_profile_exists`
   - `test_setup_runs_inline_reauth_when_tokens_missing`
   - `test_setup_surfaces_corrupted_profile_with_path`
   - `test_setup_fails_fast_when_keychain_unavailable`
   - `test_setup_resumes_after_oauth_entity_orphan`
   - `test_setup_rejects_invalid_profile_name`
   - `test_setup_handles_warn_token_cap_network_error_silently`
   - `test_setup_surfaces_oauth_provisioning_failure`

## Failure-mode handling

| Failure | Detection | Response |
|---|---|---|
| Ctrl-C between `provision_oauth` and `exchange` | Deterministic OAuth entity name + lookup-or-create | On resume reuse existing entity; rotate secret only if needed |
| Profile dir exists, `meta.json` malformed | New `scan_profile_dirs() -> (valid, corrupted)` instead of silent-skip in `list_all()` | Print path + reason, exit non-zero |
| Profile valid, keychain tokens missing | Per-profile `KeychainClient.get` probe after `list_all()` | Inline reauth flow (re-prompt password, re-exchange) |
| Keychain backend unavailable | `keyring.get_keyring()` is `fail.Keyring` / `null.Keyring` | Fail before any prompt with distro-specific hint |
| Profile-name path traversal (`../`, `\`, leading `.`) | New `validate_profile_name(name) -> Result[str, str]` (alphanumeric + `_-`, max 64) | Reject pre-prompt |
| `_detect_sn_version` network hang | Already non-fatal in current code | Confirm `meta.json` is written AFTER version probe |

## Trade-offs

| Option | Pro | Con | Position |
|---|---|---|---|
| Thin scope (1 instance, no sync) | Smallest diff, decoupled from sync feature | N-instance users loop manually via `instance register` | Take it |
| Idempotent over `--force` flag | No destructive UX, mirrors brew/git | Slightly more state-detection code | Take it |
| Fail-fast on keychain | Honest about CLAUDE.md mandate | Worse headless CI UX (no env-var override yet) | Take it; env-var ticket later |
| `PromptSource` Protocol | No-mocks compliant, reusable | New abstraction (~40 LOC) | Take it; required by rules |
| Idempotent `provision_oauth` lookup | No SN orphans on retry | Extra GET per provisioning | Take it |
| `scan_profile_dirs` API | Stops silent-skip masking corruption | New API surface on registry | Take it |
| Drop `config.yaml` from gate | Honest about `ConfigManager.load()` lazy behavior | Lose redundant signal | Take it |

## Out of Scope

- Encrypted file fallback for keychain (CLAUDE.md mandates OS
  keychain via `keyring`).
- Multi-instance looping in setup (use `nexus instance register`
  for additional instances).
- Auto-running `nexus sync` (sync is a separate feature; setup
  ships first).
- MCP probe at end of setup (`_check_server()` still stubbed at
  `probe.py:106`).
- Moving `client_id` from `meta.json` to keychain (it isn't a
  secret).
- GUI/TUI form (Rich prompts sufficient).
- Cleaning up orphaned SN `oauth_entity` records that predate the
  idempotent fix (one-off manual cleanup).
- Migrating existing profile names that already violate the new
  validator (none expected -- verify with `ls ~/.nexus/instances/`).
- Env-var override for headless CI (separate ticket).

## Open Questions

None blocking. All four design choices decided in the assumptions
round:

1. Scope: thin -- creds + 1 instance, no sync.
2. Re-run: idempotent skip + corruption surfacing + inline reauth.
3. Keychain unavailable: fail-fast with distro hint.
4. Sync hook: closing Notice only, no invocation.

## Adversarial Review

Reviewer (`primer-adversarial`, no conversation context) flagged
four blocking gaps in the v1 synthesis:

1. **Ctrl-C orphan**: `provision_oauth` writes the SN
   `oauth_entity` before `exchange` writes tokens to keychain.
   Interrupt between them and the entity is orphaned; on re-run
   the registry is still empty so setup creates a second orphan.
   FIX -- idempotent `provision_oauth` via deterministic entity
   name + lookup-or-create. Captured in Recommendation 5.
2. **Testability gap**: `provision_oauth` calls `typer.prompt`
   directly. No-mocks rule prohibits patching it; the original
   "FakeKeychain + FakeSNOAuthClient" test plan cannot drive the
   prompt path. FIX -- `PromptSource` Protocol. Captured in
   Recommendation 2.
3. **`list_all()` silent-skip masks corruption**
   (`registry.py:119-120`). Idempotent gate sees empty registry
   even when a corrupted profile exists. FIX -- new
   `scan_profile_dirs()` exposes both arms. Captured in
   Recommendation 4 + failure-mode table.
4. **Registry-present + keychain-empty** routes to `reauth` which
   immediately fails on `KeychainClient.get`. FIX -- inline reauth
   inside the idempotent gate. Captured in Recommendation 4 +
   failure-mode table.

Also flagged but not blocking:
- Profile-name path traversal -- addressed in failure-mode table.
- Initial proposal said `async def run_instance_setup` -- corrected
  to sync (matches existing `instance_register`).
- `config.yaml exists` removed from gate (`ConfigManager.load()`
  returns defaults without writing).
- `warn_token_cap` network silence -- added to test coverage list.

## Research Findings Appendix

### Existing primitives the wizard wraps

- `commands_instance.py:376-440` -- `instance_register` synchronous
  prompts (typer.prompt) -> `provision_oauth` -> `SNOAuthClient.
  exchange` (writes keychain at `oauth.py:88-94`) -> `_detect_sn_
  version` (non-fatal) -> `InstanceRegistry.register` writes
  `meta.json`. Single-instance, refuses to overwrite.
- `cli/oauth.py:247-306` -- `provision_oauth` itself owns
  `typer.prompt` for the manual-fallback path. This is the source
  of the no-mocks testability gap.
- `cli/oauth.py:101` -- `warn_token_cap` swallows network errors
  silently (`except Exception: pass`). Acceptable but worth a
  dedicated test.

### Pydantic + storage shape

- `InstanceMeta` at `instances/models.py:33-90` -- `ConfigDict
  (frozen=True, strict=True, extra="forbid")` at `:18`.
- `NexusConfig` / `InstancesConfig` at `config/settings.py:87-101`
  -- same conventions.
- `client_id` lives plaintext in `meta.json`; `client_secret` +
  `access_token` + `refresh_token` live in keychain via
  `KeychainClient`.

### Idempotence signals

- `InstanceRegistry.list_all()` at `registry.py:119-120` silently
  skips entries that fail Pydantic validation. Replace with
  `scan_profile_dirs()` that returns `(valid, corrupted)`.
- `ConfigManager.load()` at `config/manager.py:34-51` returns
  defaults without writing -- so `config.yaml` existence is NOT a
  reliable signal.
- Profile-name validation does not exist today; `instance_register`
  accepts any string.

## Session Notes

This was an assumptions-mode session: researcher agent populated
the Confident / Likely / Unclear tiers from a fresh codebase read,
user confirmed all four Unclear items with the recommended option
(thin / idempotent / fail-fast / closing-Notice), adversarial
agent flagged the four blocking gaps, user chose "Revise -- address
all four." Synthesis was revised; final version above.

Estimated scope:
- New code: `commands_setup.py` (~120 LOC), `prompts.py` (~40
  LOC), `wizard.py` (~80 LOC), `validate_profile_name` (~15 LOC),
  `scan_profile_dirs` (~30 LOC), idempotent `find_oauth_entity`
  (~20 LOC).
- Refactor: `instance_register` becomes a ~10 LOC wrapper;
  `provision_oauth` accepts `PromptSource`.
- Tests: 9 new tests (~250 LOC).
- Total: 5-6 files touched, ~600 LOC including tests. Fits
  "feature" magnitude anchor (<= 10 files).
