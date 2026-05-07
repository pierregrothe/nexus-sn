# NEXUS API Client -- Design Spec
# Author: Pierre Grothe
# Date: 2026-05-07

## Overview

Implements `AnthropicClient` (the Anthropic SDK wrapper), `AnthropicClientProtocol`
(the testable interface), `FakeAnthropicClient` (test double), and
`configure_logging()` (rotating log setup). This is MVP Step 1 -- the first
layer-4 component and the only production code that calls the Anthropic API.

---

## Scope

5 files, all under 100 lines each:

  src/nexus/api/client.py         -- update existing stub
  src/nexus/api/errors.py         -- new
  src/nexus/api/logging_config.py -- new
  tests/fakes/fake_anthropic_client.py  -- new
  tests/test_api_client.py        -- new

No other files are modified. `cli.py` will call `configure_logging()` in a
later step (MVP Step 6). For now the function exists but is not wired.

---

## 1. ModelTier and auto-discovery

### 1.1 ModelTier enum

```python
class ModelTier(StrEnum):
    STANDARD = "standard"   # Sonnet -- default for most agents
    POWERFUL = "powerful"   # Opus   -- complex multi-step reasoning
    FAST     = "fast"       # Haiku  -- lightweight / high-throughput tasks
```

Agents declare their tier requirement. They never reference a specific model
version string. The tier-to-model mapping is resolved at `AnthropicClient`
init time.

### 1.2 Model resolution

Resolution order (first match wins):

  1. Env var: NEXUS_MODEL_STANDARD / NEXUS_MODEL_POWERFUL / NEXUS_MODEL_FAST
     -- developer/CI override only, not documented to end users
  2. Auto-discover: query `client.models.list()`, filter by family prefix,
     pick newest floating alias by `created_at`
  3. Hardcoded fallback: used when API unreachable at init

Family prefixes:

  STANDARD -> "claude-sonnet-"
  POWERFUL -> "claude-opus-"
  FAST     -> "claude-haiku-"

Filtering rules for auto-discovery:
  - ID starts with the family prefix
  - ID does NOT match `-\d{8}$` (excludes date-pinned variants)
  - ID does NOT contain "preview"

Sort by `created_at` descending; take first result.

Hardcoded fallbacks (updated when a new stable family ships):

  STANDARD -> "claude-sonnet-4-6"
  POWERFUL -> "claude-opus-4-7"
  FAST     -> "claude-haiku-4-5"

The resolved model ID is logged at INFO on every `AnthropicClient` init.
When Anthropic ships a 1M context model ID, it will be picked automatically
by the `created_at` sort as soon as it appears in the listing.

### 1.3 AnthropicClientProtocol

```python
class AnthropicClientProtocol(Protocol):
    def complete(
        self,
        messages: list[dict[str, Any]],
        system: str,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 8192,
    ) -> anthropic.types.Message: ...
```

All agents and CLI commands type-hint against `AnthropicClientProtocol`, not
`AnthropicClient` directly. This makes them testable with `FakeAnthropicClient`
without any mocking.

---

## 2. AnthropicClient

### 2.1 Construction

```python
AnthropicClient(
    api_key: str,
    capabilities: CapabilitySet,
    tier: ModelTier = ModelTier.STANDARD,
    _sdk_client: anthropic.Anthropic | None = None,  # injectable for tests
)
```

The `_sdk_client` parameter is a test seam. Production callers never pass it;
tests inject a `FakeSdkClient` to avoid real API calls when testing
`AnthropicClient` internals (error mapping, cache_control shape, etc.).

Calls `_discover_model()` once at init. Failure to discover (network issue) is
caught silently; the hardcoded fallback is used. Discovery errors are logged at
WARNING, not raised.

### 2.2 complete()

```python
def complete(
    self,
    messages: list[dict[str, Any]],
    system: str,
    tools: list[dict[str, Any]] | None = None,
    max_tokens: int = 8192,
) -> anthropic.types.Message
```

System prompt is wrapped with `cache_control: {"type": "ephemeral"}` on every
call. This enables prompt caching across turns where the system prompt is
identical (the common case in NEXUS agents).

Error mapping:

  anthropic.AuthenticationError  ->  AuthError("anthropic", "api_key", suggestion)
  anthropic.APIStatusError        ->  AnthropicError(status_code, message)

The SDK's built-in retry (max_retries=3, exponential backoff) handles transient
failures before errors reach this mapping layer.

After a successful response, the following is logged at INFO:

  completion done: in=N out=N cache_write=N cache_read=N model=<id>

`cache_write` = `usage.cache_creation_input_tokens` (0 if not present)
`cache_read`  = `usage.cache_read_input_tokens` (0 if not present)

---

## 3. errors.py

Single exception class:

```python
class AnthropicError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"Anthropic API error {status_code}: {message}")
```

`AuthError` (from `auth/errors.py`) is reused for 401 responses -- no new
auth-related exception type is introduced.

---

## 4. logging_config.py

```python
def configure_logging(paths: NexusPaths, level: int = logging.INFO) -> None
```

Creates `~/.nexus/logs/` if it does not exist. Attaches two handlers to the
root logger:

  TimedRotatingFileHandler  -- ~/.nexus/logs/nexus.log
    when="midnight", backupCount=7, encoding="utf-8"
  StreamHandler             -- stderr (INFO and above)

Log format: `%(asctime)s %(levelname)-8s %(name)s -- %(message)s`

Called once from `cli.py` before any other code runs. Not called from tests.

---

## 5. FakeAnthropicClient

Located at `tests/fakes/fake_anthropic_client.py`. Implements
`AnthropicClientProtocol`.

```python
@dataclass(slots=True)
class FakeAnthropicClient:
    calls: list[dict[str, Any]] = field(default_factory=list)

    def complete(self, messages, system, tools=None, max_tokens=8192):
        self.calls.append({"messages": messages, "system": system, "tools": tools})
        return CANNED_MESSAGE
```

`CANNED_MESSAGE` is a module-level `SimpleNamespace` (or minimal dataclass)
with the fields agents actually read: `content`, `stop_reason`, `usage`.

```python
CANNED_MESSAGE = SimpleNamespace(
    content=[SimpleNamespace(type="text", text="ok")],
    stop_reason="end_turn",
    usage=SimpleNamespace(
        input_tokens=10,
        output_tokens=5,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
    ),
)
```

`calls` is inspected in tests to assert what was sent to the client.

---

## 6. Tests (tests/test_api_client.py)

9 test functions, all using `FakeAnthropicClient` or `FakeSdkClient` (a thin
fake of `anthropic.Anthropic.messages` injected via the `_sdk_client` param):

  test_model_tier_resolves_standard_default
    -- default tier resolves to a non-empty model string

  test_discover_model_uses_newest_by_created_at
    -- given two fake model entries, returns the one with later created_at

  test_discover_model_falls_back_when_list_raises
    -- APIError during discovery -> returns hardcoded fallback, no exception raised

  test_complete_adds_cache_control_to_system
    -- system block in the outbound request has cache_control.type == "ephemeral"

  test_complete_maps_authentication_error_to_auth_error
    -- anthropic.AuthenticationError raised by SDK -> AuthError raised by client

  test_complete_maps_api_status_error_to_anthropic_error
    -- anthropic.APIStatusError(status_code=500) -> AnthropicError(500, ...)

  test_complete_logs_cache_tokens (verifies log output contains cache_write/cache_read)
    -- cache_creation_input_tokens and cache_read_input_tokens appear in log record

  test_fake_client_records_calls
    -- FakeAnthropicClient.calls captures messages and system after complete()

  test_tool_registry_assembles_anthropic_format
    -- ToolRegistry.as_anthropic_tools() returns list with name/description/input_schema

---

## 7. Coverage target

These 5 files replace the two stub files currently at 0% coverage. The
`--cov-fail-under` threshold in `pyproject.toml` should be raised from 40 to
50 once these tests pass, reflecting the real coverage gain.

---

## Layer compliance

`api/` depends on:  `capabilities/` (CapabilitySet), `auth/` (AuthError)
`api/` does NOT import from: `agents/`, `templates/`, `assessment/`, `execution/`, `cli.py`

No circular imports introduced.
