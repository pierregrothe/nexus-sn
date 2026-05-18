# Story 01: PromptSource protocol + Typer and scripted impls

Status: backlog
Spec-Clarity: high
Depends-On: none

## Story

As a NEXUS developer,
I want a typed `PromptSource` Protocol with a Typer-backed default and a
scripted test impl,
so that wizard code can be driven from tests without `unittest.mock` and
without patching `typer.prompt`.

## Acceptance Criteria

AC1:
**Given** any caller in `cli/` or `instances/` needs interactive input
**When** the caller takes a `PromptSource` parameter and calls
`prompts.ask("Host", hide=False)` or `prompts.confirm("Continue?")`
**Then** in production the Typer impl forwards to `typer.prompt` /
`typer.confirm`, and in tests the scripted impl pops the next pre-loaded
answer from a `deque[str]` (`bool` answers parsed as `"y"`/`"n"`).

AC2:
**Given** a test pre-loads a `ScriptedPromptSource` with N answers
**When** the wizard consumes exactly N prompts
**Then** the test passes; if the wizard asks N+1 prompts the scripted
impl raises `PromptExhaustedError` (so under-specified tests fail loudly
instead of hanging).

AC3:
**Given** the Typer impl is called with `hide=True`
**When** the user types a password
**Then** the underlying `typer.prompt` is invoked with
`hide_input=True, confirmation_prompt=False`.

## Must NOT

- Must NOT depend on `unittest.mock` anywhere (rule: no-mocks).
- Must NOT inherit from `typer.Typer` or other framework base classes;
  this is a Protocol, not a concrete class hierarchy.
- Must NOT add new dependencies; `typer` is already pinned.
- Must NOT route through `print()` or `sys.stdin.readline` directly --
  Typer/Rich own all user I/O.

## Tasks / Subtasks

- [ ] Create `src/nexus/cli/prompts.py` with file header + Google docstrings
      (AC: 1)
  - [ ] Define `PromptSource` runtime-checkable Protocol with
        `ask(message: str, *, hide: bool = False) -> str` and
        `confirm(message: str) -> bool`
  - [ ] Define `TyperPromptSource` (frozen dataclass with `slots=True`)
        wrapping `typer.prompt` / `typer.confirm`
  - [ ] Define `PromptExhaustedError(Exception)` for the scripted impl
  - [ ] `__all__` exports both impls + the protocol + the exception
- [ ] Create `tests/fakes/scripted_prompt.py` with `ScriptedPromptSource`
      (AC: 2)
  - [ ] `__init__(answers: Iterable[str])` -> stores `deque[str]`
  - [ ] `ask()` and `confirm()` pop the next answer; raise
        `PromptExhaustedError` when empty
- [ ] Create `tests/test_cli_prompts.py` with class-based tests
      (AC: 1, 2, 3)
  - [ ] `TestPromptSourceProtocol`: contract test -- both impls satisfy
        the Protocol via `isinstance(...)` runtime check
  - [ ] `TestTyperPromptSource`: covers `ask` non-hidden, `ask` hidden
        (verify keyword args via a fake `prompt_fn` injection), `confirm`
  - [ ] `TestScriptedPromptSource`: covers happy path, exhaustion raise,
        bool parsing of `"y"` / `"yes"` / `"n"` / `"no"`

## Existing Code

Greenfield. No callers yet -- the protocol is introduced ahead of
stories 05, 06, 07 which will consume it.

## Dev Notes

### Modules Affected

- `src/nexus/cli/prompts.py` (new)
- `tests/fakes/scripted_prompt.py` (new)
- `tests/test_cli_prompts.py` (new)

### Testing Approach

- Class-based pytest tests, naming `test_<function>_<scenario>`.
- No mocks. The `TyperPromptSource` test injects a callable (the
  `prompt_fn` field, defaulting to `typer.prompt`) and inspects the
  arguments it receives -- this is a real call into a real fake, not a
  patched library.
- `ScriptedPromptSource` is itself the testing primitive used by later
  stories; this story validates the primitive.

### Conventions

- Frozen dataclass with `slots=True` for `TyperPromptSource`.
- File header + module-level `__all__`.
- Python 3.14: `|` unions, `match/case` if dispatch is needed (probably
  not for this story).
- ASCII only.

## References

- Brainstorming: `.primer/brainstorming/2026-05-18-nexus-setup-credential-wizard.md`,
  section "Adversarial Review" item 2 + Recommendation 2
- Rule: `~/.claude/rules/no-mocks.md`
- Rule: `~/.claude/rules/module-exports.md`
- Rule: `~/.claude/rules/file-headers.md`
