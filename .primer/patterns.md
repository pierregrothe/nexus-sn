# NEXUS -- Architecture Patterns

## Layer dependency rule

Import direction is strictly bottom-to-top. Never import from a higher layer.

  cache -> (nothing in nexus)            # Layer 0 utility (ADR-017)
  config -> cache
  auth -> config, cache
  capabilities -> config, auth, cache
  api -> capabilities, cache
  connectors -> cache
  agents -> api, connectors, knowledge, cache
  templates -> connectors, knowledge, cache
  assessment -> connectors, cache
  execution -> agents, templates, assessment, api, cache
  cli -> execution, templates, assessment, config, auth, capabilities, cache
  ui -> cli (same API surface)

If you need to pass data between layers, use the types defined in base.py / schemas.py.
Never import upward.

## Pydantic everywhere

Every data structure crossing a module boundary is a Pydantic model.
All models use model_config = ConfigDict(frozen=True) unless mutation is required.
Field validators for constraints, model validators for cross-field logic.
No raw dicts as public API.

## Error hierarchy

NexusError (base)
  ConfigError       -- missing/invalid config
  AuthError         -- credential lookup failed
  SNClientError     -- SN REST API errors
    SNAuthError     -- 401/403
    SNNotFoundError -- 404
    SNRateLimitError -- 429
  TemplateError     -- invalid YAML
    SchemaError     -- Pydantic validation failure
    VersionError    -- SN version incompatibility
  AssessmentError   -- readiness gate failure
  ExecutionError    -- agent or dispatch failure

Errors carry: code (snake_case), message, suggestion, blocking flag.
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

ConnectorRegistry merges tool lists and routes calls.
ServiceNow connector is always registered. Others are optional.
With claude-agent-sdk, connector tools are exposed to the LLM via
ClaudeAgentOptions(mcp_servers=...). NEXUS-internal Python tool calls bypass
the LLM and go through ConnectorRegistry directly.

## Agent pattern

Every specialist implements AgentProtocol:
  name: str (property)
  domain: str (property)
  run(context: ExecutionContext) -> AgentResult

ExecutionContext is immutable (frozen dataclass). Agents never mutate shared state.
AgentResult carries: outputs dict (sys_ids, counts), errors list, summary string.
The execution dispatcher passes outputs from completed tasks into inputs of
dependent tasks via the execution context registry.

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

Agents pass a model string to AgentClient.complete(model=...) when they need
to override the SDK default. The Agent SDK picks the model when the argument
is None. NEXUS does not maintain its own model-discovery layer -- that
responsibility moved to the SDK with ADR-015.

## Fake-as-Protocol-implementation test doubles

Test fakes implement the exact Protocol the production code consumes. Naming
convention: FakeXClient where XClient is the real class. Fakes use
@dataclass(slots=True), expose a `calls: list[dict]` for assertion, and return
a configurable canned_response field. Example: FakeAgentClient implements
AgentClientProtocol; tests inject it where the production code expects the
Protocol. side_effect on a fake lets tests trigger error paths without
patching. No mocks anywhere -- all test doubles are real Python classes with
the same interface.
Prefer match over if/elif chains for 3+ branches.
