# Story 02: KeychainClient.check_available() fail-fast probe

Status: backlog
Spec-Clarity: high
Depends-On: none

## Story

As a NEXUS user running `nexus setup` on a headless Linux box or CI
runner,
I want the command to fail before any prompt with a distro-specific hint
when the OS keychain backend is unusable,
so that I do not type a password into a wizard that will throw on save.

## Acceptance Criteria

| Backend state                                          | check_available()                       | Notes                                                  |
|--------------------------------------------------------|-----------------------------------------|--------------------------------------------------------|
| `keyring.backends.SecretService.Keyring` ready         | `Ok(None)`                              | Linux GNOME/KDE happy path                             |
| `keyring.backends.Windows.WinVaultKeyring` ready       | `Ok(None)`                              | Windows happy path                                     |
| `keyring.backends.macOS.Keyring` ready                 | `Ok(None)`                              | macOS happy path                                       |
| `keyring.backends.fail.Keyring`                        | `Err("...install secret-service...")`   | Linux headless, no D-Bus session                       |
| `keyring.backends.null.Keyring`                        | `Err("...keyring disabled...")`         | Explicitly disabled via `KEYRING_BACKEND=null`         |
| Real backend present, set/get raises `keyring.errors.KeyringLocked` | `Err("...unlock keychain...")` | Locked macOS keychain                                  |
| Real backend, set/get raises `keyring.errors.NoKeyringError` | `Err("...no usable backend...")`  | Generic catch                                          |

AC1: Distinguishing fail / null / locked / no-backend is done by
`isinstance` checks against the keyring backend classes plus a
round-trip set+delete on a sentinel key. The probe MUST NOT leave the
sentinel in the keychain on success.

## Must NOT

- Must NOT write the user's real credentials during the probe -- sentinel
  service name only (e.g., `nexus-probe`).
- Must NOT swallow `KeyringError` silently; every error variant maps to
  a distinct hint string.
- Must NOT add a fallback to file-based or env-var storage in this story
  (out of scope per brainstorming).
- Must NOT introduce a global on-import probe; `check_available()` is
  called explicitly by the wizard.

## Tasks / Subtasks

- [ ] Add `check_available(self) -> Result[None, str]` to `KeychainClient`
      in `src/nexus/auth/keychain.py` (AC: 1)
  - [ ] Use `match/case` on `type(keyring.get_keyring())` for backend dispatch
  - [ ] Round-trip a sentinel: `set` -> `get` -> `delete`; catch
        `keyring.errors.KeyringError` subclasses with PEP 758 multi-except
  - [ ] Each `Err` payload is an actionable string ending with a hint
        like `"Run: sudo apt install gnome-keyring"` (Linux) or
        `"Unlock your login keychain in Keychain Access"` (macOS)
- [ ] Extend `tests/fakes/fake_keychain.py` (AC: 1)
  - [ ] `FakeKeychain(available: bool = True, failure_kind: str | None = None)`
        where `failure_kind in {"fail", "null", "locked", "no-backend"}`
  - [ ] `check_available()` returns the right `Result` per `failure_kind`
- [ ] Add test class `TestKeychainCheckAvailable` in
      `tests/test_auth_keychain.py` (AC: 1)
  - [ ] One test per row of the AC table
  - [ ] Verify the sentinel is deleted after a successful probe (no
        leftover state)

## Existing Code

- `src/nexus/auth/keychain.py:24-85` -- `KeychainClient` wraps `keyring`.
  Adds one method; no signature changes to existing methods.
- `tests/fakes/fake_keychain.py` -- already used by oauth tests; extend
  with the failure_kind parameter without breaking existing callers.

## Dev Notes

### Modules Affected

- `src/nexus/auth/keychain.py`
- `tests/fakes/fake_keychain.py`
- `tests/test_auth_keychain.py`

### Testing Approach

- Class-based pytest tests (`TestKeychainCheckAvailable`), real
  `keyring` backend swapping via `keyring.set_keyring(...)` in a
  fixture that resets afterwards. Real-impl testing, not mocking.
- Use the `keyring.backends.fail.Keyring` and `keyring.backends.null.Keyring`
  classes that ship with `keyring` to drive the unavailable cases
  authentically.
- For `KeyringLocked`, instantiate a tiny test-only backend class that
  raises on `set_password`. This is a real Protocol implementation, not
  a mock.

### Conventions

- `Result[None, str]` from the existing project Result type (grep
  `src/nexus/` for `class Result` or `from .result import Result`
  before importing -- use canonical path).
- Python 3.14 multi-except: `except KeyringLocked, NoKeyringError: ...`.
- Frozen / `slots=True` if a new dataclass is introduced (unlikely here).

## References

- Brainstorming: `.primer/brainstorming/2026-05-18-nexus-setup-credential-wizard.md`,
  section "Failure-mode handling" row 4 + Key Insight 3
- Existing: `src/nexus/auth/keychain.py:24-85`
- Rule: `~/.claude/rules/python-314.md` (PEP 758 multi-except)
