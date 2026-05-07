# NEXUS -- Architecture Patterns

## Layer dependency rule

Import direction is strictly bottom-to-top. Never import from a higher layer.

  config -> (nothing in nexus)
  auth -> config
  capabilities -> config, auth
  api -> capabilities
  connectors -> (nothing in nexus)
  agents -> api, connectors, knowledge
  templates -> connectors, knowledge
  assessment -> connectors
  execution -> agents, templates, assessment, api
  cli -> execution, templates, assessment, config, auth, capabilities
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
The Anthropic API receives the merged tool list as the tools= parameter.

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

## Tier-based model resolution (api/ layer)

Agents declare a capability tier (StrEnum), never a specific model version string.
The tier is resolved to an actual model ID at AnthropicClient init via
_discover_model() which queries client.models.list(), filters by family prefix
(claude-sonnet-, claude-opus-, claude-haiku-), excludes date-pinned variants
(-YYYYMMDD) and "preview" entries, then sorts by created_at desc. Env vars
(NEXUS_MODEL_STANDARD/POWERFUL/FAST) override discovery; hardcoded defaults are
the offline fallback. When a new Sonnet ships, no code change is needed --
discovery picks it up automatically.

## Structural Protocol chains at SDK boundaries

When wrapping a third-party SDK type, define narrow private Protocols that
describe only the duck-typed interface used. Example: _ModelEntry (id, created_at)
+ _ModelsList (list() -> Iterable[_ModelEntry]) + _ModelDiscoveryClient (models
property). This pattern keeps test fakes simple (a tiny dataclass satisfies the
Protocol structurally) and avoids leaking SDK types upstream. Use Iterable, not
list, in Protocol returns -- list is invariant; Iterable is covariant.

## Fake-as-Protocol-implementation test doubles

Test fakes implement the exact Protocol the production code consumes. Naming
convention: FakeXClient where XClient is the real class. Fakes use
@dataclass(slots=True), expose a `calls: list[dict]` for assertion, and return
a module-level CANNED_RESPONSE constant. Example: FakeAnthropicClient implements
AnthropicClientProtocol; tests inject it where the production code expects the
Protocol. No mocks anywhere -- all test doubles are real Python classes with the
same interface.
Prefer match over if/elif chains for 3+ branches.
