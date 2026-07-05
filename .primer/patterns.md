# NEXUS -- Architecture Patterns

## Layer dependency rule

Import direction is strictly bottom-to-top. Never import from a higher layer.

  cache -> (nothing in nexus)            # Layer 0 utility (ADR-017)
  knowledge -> (nothing in nexus)        # Layer 0 leaf (KB loader/index)
  config -> cache
  auth -> config, cache
  capabilities -> config, auth, cache
  api -> capabilities, cache
  connectors -> cache
  plugins -> config, cache
  capture -> connectors, config
  schema -> connectors, api, config
  agents -> api, connectors, knowledge, cache      # scaffolded, stubs
  templates -> connectors, knowledge, cache
  assessment -> connectors, cache
  instances -> auth, plugins, config, cache, ui/components
  replatform -> capture, schema, config, ui/components
  execution -> agents, templates, assessment, api, cache   # scaffolded, stubs
  updater -> config, cache               # Layer 7 (ADR-020)
  migrate -> capture, schema, instances, plugins, connectors, config, ui/components
  cli -> execution, templates, assessment, capture, plugins, instances, migrate,
         replatform, schema, config, auth, capabilities, cache, updater
  ui -> cli (NiceGUI dashboard -- planned)

`ui/components/` (StatusBadge, DataTable, ...) is a shared Rich-rendering
presentation library imported by mid-graph packages (instances, migrate,
replatform) for terminal output; it is distinct from the planned top-level
NiceGUI dashboard (`ui`) that wraps the CLI. "ui/components" above refers to the
former. `agents/` and `execution/` are scaffolded at the positions shown but are
not yet wired (see Agent pattern).

If you need to pass data between layers, use the types defined in base.py / schemas.py.
Never import upward.

## Pydantic everywhere

Every data structure crossing a module boundary is a Pydantic model.
All models use model_config = ConfigDict(frozen=True) unless mutation is required.
Field validators for constraints, model validators for cross-field logic.
No raw dicts as public API.

## Error hierarchy

No shared `NexusError` base exists -- each layer subclasses `Exception`
directly (a few subclass RuntimeError/ValueError). Real families by layer:

  api         AnthropicError, KrokiError
  auth        AuthError, KeychainUnavailableError          (carry `suggestion`)
  cache       CacheKeyError
  connectors  SNClientError -> SNAuthError (401/403), SNNotFoundError (404),
              SNRateLimitError (429)                        (carry `suggestion`)
  capture     CaptureError -> ScopeNotFoundError, TableUnavailableError,
              ArchiveCorruptError, UpdateSetError
  templates   TemplatesError -> InvalidGitHubRepoError, TemplateLoadError,
              ScopeNotFoundError
  schema      SchemaError -> AreaNotFoundError, ScopeNotFoundError,
              SchemaArchiveError, ScopeRecordCountError
  assessment  AssessmentError -> RulesetLoadError; InteractiveRequiredError
  instances   InstanceError -> InvalidProfileNameError, InstanceNotFoundError,
              OAuthError, TokenExpiredError, SnapshotError
  plugins     PluginScanError, PluginAdvisoryDataError, PluginImpactError,
              PluginExecutionError -> Progress/Timeout/NotFound/Batch/
              ImpactBlock/Unsupported; BaselineNotFoundError, AdvisoryOverrideError
  updater     UpdaterError

CLI exit codes: 0=success, 1=blocking error, 2=usage error.
Errors to stderr. Machine-readable output to stdout.

## Logging

Every module: log = logging.getLogger(__name__)
No print() in library modules. Only CLI entry points and hooks use print.
Configure logging only in __main__ and conftest.py.
Log file paths, not file contents.
Log counts and flags for structured objects, never full dicts.
Levels: DEBUG=high-volume detail, INFO=phase boundaries, WARNING=recoverable errors,
        ERROR=unrecovered failures.

User-facing output goes through rich.Console (cli.py) or print() in updater hooks.
sys.stdout.write / sys.stderr.write are banned in src/nexus/ (semgrep-enforced).

## Hot-path I/O has a gate

Anything wired into the CLI callback (@app.callback), per-command hooks, or
loops that fire on every invocation MUST gate or cache external I/O. The
auto-updater's check_and_maybe_update() runs on every nexus command; it
hides a 3-second-timeout GitHub call behind a 24-hour mtime gate
(_should_check_now / _record_check_attempt) so 99.99% of launches pay
nothing. Apply the same shape (timestamp file, in-process cache, or env
flag) when adding background work to a hot path. Caught in /simplify of
PR #8 (ADR-020).

## Path getters are pure

Functions that return a Path do not mkdir as a side effect. Centralise
directory creation in NexusPaths.ensure_dirs() (called once at startup)
or at the immediate point of write. Mixing path resolution with
filesystem mutation makes the function untestable in isolation and
surprises future readers. Caught in /simplify of PR #8.

## Testing

No mocks. No unittest.mock, MagicMock, patch, pytest_mock. Blocked by pre-edit hook.
Use fakes: tests/fakes/fake_sn_client.py, tests/fakes/fake_keychain.py.
Use tmp_path for all file I/O in tests.
100% line coverage. mypy strict on all test files.
Test naming: test_<function_name>_<scenario>.
All test functions have complete type annotations.
Test happy path AND all error/fallback branches.

pytest's monkeypatch fixture IS allowed as a function parameter for env var manipulation:
  def test_foo(monkeypatch: pytest.MonkeyPatch) -> None:
      monkeypatch.setenv("MY_VAR", "value")
The pre-edit hook blocks import-based mocking (unittest.mock, pytest_mock imports),
not pytest's built-in monkeypatch fixture parameter.

asyncio_mode = "auto" is configured in pyproject.toml. The @pytest.mark.asyncio
decorator is NOT required on async test functions -- just define them as async def.

## Connector pattern

Every connector implements ConnectorProtocol:
  name: str (property)
  tools() -> list[Tool]
  call(tool_name, **kwargs) -> ToolResult

ConnectorRegistry (src/nexus/connectors/registry.py) and ServiceNowConnector
implement this protocol but are not yet instantiated anywhere; today the CLI and
engines call ServiceNow through ServiceNowClient directly.

Planned: a composition root that registers connectors on a ConnectorRegistry and
exposes their tools to the LLM via ClaudeAgentOptions(mcp_servers=...) --
agent_client.py currently passes only system_prompt/model/max_turns.

## Agent pattern (scaffolded -- not yet wired)

The AgentProtocol / ExecutionContext / AgentResult types are defined
(src/nexus/agents/base.py):
  name: str (property)
  domain: str (property)
  run(context: ExecutionContext) -> AgentResult

ExecutionContext is immutable (frozen dataclass); AgentResult carries an
outputs dict (sys_ids, counts), errors list, and summary string.

Planned: the execution dispatcher will pass outputs from completed tasks into
dependent tasks via an execution context registry. Today src/nexus/execution/
(planner, dispatcher, reporter, rollback) and src/nexus/agents/specialists/ are
stubs -- no orchestration runs yet.

## Template YAML contract

Every template YAML must have: name, version, type, sn_version, spec, tests.
Validated against the Pydantic schema for its type before any apply.
CI validates all YAML in PRs via validate-templates.yml.
manifest.json at templates/ root is the registry index.

## Capability-gated features

Check capabilities before using any enterprise MCP feature:
  if capabilities.has_feature(FeatureFlag.ROI_ANALYSIS):
      # call value melody tools
  else:
      log.info("value_melody unavailable, skipping ROI analysis")

Never raise an error for a missing capability. Degrade gracefully.

## Async conventions

httpx for SN REST (async with ServiceNowClient() as client).
asyncio.gather() for parallel SN operations within a single task.
Probe all MCP servers concurrently (asyncio.gather + asyncio.timeout).
pytest-asyncio asyncio_mode = "auto" -- no @pytest.mark.asyncio needed on test functions.

## File headers (every new Python file)

# src/nexus/path/to/file.py
# Brief one-line description of the module.
# Author: Pierre Grothe
# Date: YYYY-MM-DD

## __all__ in every module

Every Python module declares __all__. Export in category order:
  1. Factories (create_* functions)
  2. Protocols
  3. Configuration / settings classes
  4. Models / dataclasses
  5. Enums / constants
  6. Errors

## match/case for dispatch

Use match/case for multi-branch dispatch on enums and string codes.
Always include a case _: default branch.

## Model selection

CLI command handlers (e.g. plugins explain / roadmap / recommend deactivate)
pass a model string to AgentClient.complete(model=...) when they need to
override the SDK default. The Agent SDK picks the model when the argument is
None. NEXUS does not maintain its own model-discovery layer -- that
responsibility moved to the SDK with ADR-015. (Specialist agents are scaffolded
but not yet wired -- see Agent pattern.)

## Fake-as-Protocol-implementation test doubles

Test fakes implement the exact Protocol the production code consumes. Naming
convention: FakeXClient where XClient is the real class. The simplest shape --
used by FakeAgentClient (tests/fakes/fake_agent_client.py) -- is a
@dataclass(slots=True) exposing a `calls: list[dict]` for assertion and a
configurable canned_response field. Stateful fakes use whatever shape their
domain needs: FakeServiceNowClient is a plain class with a
`calls: list[tuple[str, str]]` log, and FakeKeychainClient is a plain
KeychainClient subclass with an in-memory store. side_effect / failure-mode
fields let tests trigger error paths without patching. No mocks anywhere -- all
test doubles are real Python classes implementing the same Protocol.
Prefer match over if/elif chains for 3+ branches.
