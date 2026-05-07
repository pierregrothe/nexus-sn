# API Client Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement AnthropicClient with auto-discovering ModelTier, prompt caching, error mapping, cache-hit logging, a FakeAnthropicClient test double, and rotating log configuration.

**Architecture:** `client.py` is updated in two passes (ModelTier/discovery, then AnthropicClient body). `errors.py` and `logging_config.py` are new focused single-purpose modules. All tests use fakes, never mocks.

**Tech Stack:** anthropic SDK, httpx (already a dep), Python stdlib logging.handlers, pytest caplog fixture.

---

## File Map

```
Modify:  src/nexus/api/client.py        -- ModelTier, _discover_model, Protocol, AnthropicClient
Create:  src/nexus/api/errors.py        -- AnthropicError
Create:  src/nexus/api/logging_config.py -- configure_logging
Modify:  src/nexus/api/__init__.py      -- export new public types
Create:  tests/fakes/fake_anthropic_client.py -- FakeAnthropicClient
Modify:  tests/fakes/__init__.py        -- export FakeAnthropicClient
Create:  tests/test_api_client.py       -- 9 tests
Modify:  pyproject.toml                 -- raise --cov-fail-under to 50
```

---

## Task 1: AnthropicError

**Files:**
- Create: `src/nexus/api/errors.py`
- Test: `tests/test_api_client.py` (first test)

- [ ] **Step 1: Create test file with the first test**

```python
# tests/test_api_client.py
# API client layer tests.
# Author: Pierre Grothe
# Date: 2026-05-07
"""Tests for AnthropicError, AnthropicClient, FakeAnthropicClient, and ToolRegistry."""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from nexus.api.errors import AnthropicError


def test_anthropic_error_has_status_code_and_message() -> None:
    exc = AnthropicError(429, "Rate limit exceeded")
    assert exc.status_code == 429
    assert exc.message == "Rate limit exceeded"
    assert "429" in str(exc)
```

- [ ] **Step 2: Run test to verify it fails**

```
poetry run pytest tests/test_api_client.py::test_anthropic_error_has_status_code_and_message -v
```

Expected: `ImportError: cannot import name 'AnthropicError'`

- [ ] **Step 3: Create errors.py**

```python
# src/nexus/api/errors.py
# Anthropic API error types.
# Author: Pierre Grothe
# Date: 2026-05-07
"""Typed exceptions for the Anthropic API layer."""

__all__ = ["AnthropicError"]


class AnthropicError(Exception):
    """Raised when the Anthropic API returns an error status.

    Args:
        status_code: HTTP status code from the API response.
        message: Error message from the API response body.
    """

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"Anthropic API error {status_code}: {message}")
```

- [ ] **Step 4: Run test to verify it passes**

```
poetry run pytest tests/test_api_client.py::test_anthropic_error_has_status_code_and_message -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/nexus/api/errors.py tests/test_api_client.py
git commit -m "feat: add AnthropicError and first api client test"
```

---

## Task 2: configure_logging

**Files:**
- Create: `src/nexus/api/logging_config.py`
- Test: `tests/test_api_client.py` (append test)

- [ ] **Step 1: Append test to test_api_client.py**

Add after the existing test:

```python
from nexus.api.logging_config import configure_logging
from nexus.config.paths import NexusPaths


def test_configure_logging_creates_logs_directory(tmp_path: Any) -> None:
    paths = NexusPaths(root=tmp_path / ".nexus")
    configure_logging(paths)
    assert (tmp_path / ".nexus" / "logs").is_dir()
```

- [ ] **Step 2: Run test to verify it fails**

```
poetry run pytest tests/test_api_client.py::test_configure_logging_creates_logs_directory -v
```

Expected: `ImportError: cannot import name 'configure_logging'`

- [ ] **Step 3: Create logging_config.py**

```python
# src/nexus/api/logging_config.py
# Rotating log file setup for the NEXUS CLI session.
# Author: Pierre Grothe
# Date: 2026-05-07
"""configure_logging: attach TimedRotatingFileHandler to the root logger."""

import logging
import logging.handlers
from pathlib import Path

from nexus.config.paths import NexusPaths

__all__ = ["configure_logging"]

_FMT = "%(asctime)s %(levelname)-8s %(name)s -- %(message)s"


def configure_logging(paths: NexusPaths, level: int = logging.INFO) -> None:
    """Attach a rotating file handler and a stderr handler to the root logger.

    Creates the logs directory if it does not exist. Keeps 7 days of daily logs.
    No-op if the root logger already has handlers (safe to call multiple times).

    Args:
        paths: NexusPaths providing the runtime directory locations.
        level: Logging level applied to all handlers (default INFO).
    """
    logs_dir: Path = paths.root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if root.handlers:
        return
    file_handler = logging.handlers.TimedRotatingFileHandler(
        logs_dir / "nexus.log",
        when="midnight",
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(_FMT))
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter(_FMT))
    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(stream_handler)
```

- [ ] **Step 4: Run test to verify it passes**

```
poetry run pytest tests/test_api_client.py::test_configure_logging_creates_logs_directory -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/nexus/api/logging_config.py tests/test_api_client.py
git commit -m "feat: add configure_logging with 7-day rotating file handler"
```

---

## Task 3: ModelTier + _discover_model

**Files:**
- Modify: `src/nexus/api/client.py`
- Test: `tests/test_api_client.py` (append 4 tests)

- [ ] **Step 1: Append 4 tests to test_api_client.py**

```python
from nexus.api.client import (
    AnthropicClientProtocol,
    ModelTier,
    _TIER_DEFAULTS,
    _discover_model,
)


def test_model_tier_standard_default_is_sonnet() -> None:
    assert _TIER_DEFAULTS[ModelTier.STANDARD] == "claude-sonnet-4-6"


def test_discover_model_returns_newest_by_created_at() -> None:
    older = SimpleNamespace(
        id="claude-sonnet-4-5",
        created_at=datetime(2025, 9, 1, tzinfo=UTC),
    )
    newer = SimpleNamespace(
        id="claude-sonnet-4-6",
        created_at=datetime(2025, 12, 1, tzinfo=UTC),
    )

    class _FakeModels:
        def list(self) -> list:
            return [older, newer]

    result = _discover_model(SimpleNamespace(models=_FakeModels()), ModelTier.STANDARD)
    assert result == "claude-sonnet-4-6"


def test_discover_model_falls_back_when_list_raises() -> None:
    class _FakeModels:
        def list(self) -> list:
            raise RuntimeError("connection refused")

    result = _discover_model(SimpleNamespace(models=_FakeModels()), ModelTier.STANDARD)
    assert result == _TIER_DEFAULTS[ModelTier.STANDARD]


def test_discover_model_respects_env_var_override(monkeypatch: Any) -> None:
    monkeypatch.setenv("NEXUS_MODEL_STANDARD", "claude-sonnet-4-99")
    # models.list() is never called when env var is set
    result = _discover_model(SimpleNamespace(models=None), ModelTier.STANDARD)
    assert result == "claude-sonnet-4-99"
```

- [ ] **Step 2: Run tests to verify they fail**

```
poetry run pytest tests/test_api_client.py -k "model_tier or discover_model" -v
```

Expected: `ImportError` on `ModelTier`, `_TIER_DEFAULTS`, `_discover_model`

- [ ] **Step 3: Rewrite client.py with ModelTier, _discover_model, and Protocol**

Replace the entire content of `src/nexus/api/client.py`:

```python
# src/nexus/api/client.py
# Anthropic SDK wrapper with prompt caching and MCP tool injection.
# Author: Pierre Grothe
# Date: 2026-05-07
"""AnthropicClient: wraps anthropic.Anthropic with caching, model auto-discovery, and retry."""

import logging
import os
import re
from enum import StrEnum
from typing import Any, Protocol

import anthropic

from nexus.api.errors import AnthropicError
from nexus.auth.errors import AuthError
from nexus.capabilities.registry import CapabilitySet

log = logging.getLogger(__name__)

__all__ = ["AnthropicClient", "AnthropicClientProtocol", "ModelTier"]

_MAX_RETRIES = 3
_DATE_RE = re.compile(r"-\d{8}$")


class ModelTier(StrEnum):
    """Model capability tier.

    Agents declare their tier requirement; they never reference a specific
    model version string. The actual model ID is resolved at AnthropicClient
    init via auto-discovery from client.models.list().
    """

    STANDARD = "standard"
    POWERFUL = "powerful"
    FAST = "fast"


_TIER_FAMILY: dict[ModelTier, str] = {
    ModelTier.STANDARD: "claude-sonnet-",
    ModelTier.POWERFUL: "claude-opus-",
    ModelTier.FAST: "claude-haiku-",
}

_TIER_DEFAULTS: dict[ModelTier, str] = {
    ModelTier.STANDARD: "claude-sonnet-4-6",
    ModelTier.POWERFUL: "claude-opus-4-7",
    ModelTier.FAST: "claude-haiku-4-5",
}

_TIER_ENV: dict[ModelTier, str] = {
    ModelTier.STANDARD: "NEXUS_MODEL_STANDARD",
    ModelTier.POWERFUL: "NEXUS_MODEL_POWERFUL",
    ModelTier.FAST: "NEXUS_MODEL_FAST",
}


def _discover_model(client: anthropic.Anthropic, tier: ModelTier) -> str:
    """Return the newest available model ID for the given tier.

    Resolution order: env var override, auto-discover via API, hardcoded fallback.

    Args:
        client: anthropic.Anthropic instance (or duck-typed fake for tests).
        tier: Desired model capability tier.

    Returns:
        Model ID string suitable for the messages.create() call.
    """
    env_val = os.environ.get(_TIER_ENV[tier])
    if env_val:
        return env_val
    prefix = _TIER_FAMILY[tier]
    try:
        candidates = sorted(
            [
                m
                for m in client.models.list()
                if m.id.startswith(prefix)
                and not _DATE_RE.search(m.id)
                and "preview" not in m.id
            ],
            key=lambda m: m.created_at,
            reverse=True,
        )
        if candidates:
            return candidates[0].id
    except Exception:
        log.warning("model discovery failed for tier=%s; using fallback", tier)
    return _TIER_DEFAULTS[tier]


class AnthropicClientProtocol(Protocol):
    """Interface for the Anthropic API client.

    All agents and CLI commands type-hint against this Protocol.
    FakeAnthropicClient in tests/fakes/ implements it.
    """

    def complete(
        self,
        messages: list[dict[str, Any]],
        system: str,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 8192,
    ) -> anthropic.types.Message: ...


class AnthropicClient:
    """Anthropic API wrapper with prompt caching and capability-aware tools.

    Args:
        api_key: Claude Enterprise API key.
        capabilities: Session capability set from startup probe.
        tier: Model capability tier (default STANDARD).
        _sdk_client: Injectable anthropic.Anthropic instance (tests only).
    """

    def __init__(
        self,
        api_key: str,
        capabilities: CapabilitySet,
        tier: ModelTier = ModelTier.STANDARD,
        _sdk_client: anthropic.Anthropic | None = None,
    ) -> None:
        self._client = _sdk_client or anthropic.Anthropic(
            api_key=api_key, max_retries=_MAX_RETRIES
        )
        self._capabilities = capabilities
        self._model = _discover_model(self._client, tier)
        log.info("AnthropicClient initialised: tier=%s model=%s", tier, self._model)

    def complete(
        self,
        messages: list[dict[str, Any]],
        system: str,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 8192,
    ) -> anthropic.types.Message:
        """Send a completion request with prompt caching enabled.

        The system prompt is wrapped with cache_control ephemeral on every call
        to enable cross-turn caching when the system prompt is identical.

        Args:
            messages: Conversation history.
            system: System prompt text (cached per session).
            tools: Anthropic-format tool definitions.
            max_tokens: Maximum tokens in the response.

        Returns:
            Raw anthropic.types.Message response.

        Raises:
            AuthError: When the API key is invalid or expired.
            AnthropicError: For other API status errors (4xx/5xx).
        """
        log.debug("completion: model=%s messages=%d", self._model, len(messages))
        try:
            msg = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=[
                    {
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=messages,
                tools=tools or [],
            )
        except anthropic.AuthenticationError as exc:
            raise AuthError(
                "anthropic",
                "api_key",
                "Run 'nexus setup' to reconfigure your API key",
            ) from exc
        except anthropic.APIStatusError as exc:
            raise AnthropicError(exc.status_code, str(exc)) from exc
        u = msg.usage
        log.info(
            "completion done: in=%d out=%d cache_write=%d cache_read=%d model=%s",
            u.input_tokens,
            u.output_tokens,
            getattr(u, "cache_creation_input_tokens", 0),
            getattr(u, "cache_read_input_tokens", 0),
            self._model,
        )
        return msg
```

- [ ] **Step 4: Run the 4 tests to verify they pass**

```
poetry run pytest tests/test_api_client.py -k "model_tier or discover_model" -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add src/nexus/api/client.py tests/test_api_client.py
git commit -m "feat: add ModelTier auto-discovery and AnthropicClientProtocol"
```

---

## Task 4: AnthropicClient.complete() tests

**Files:**
- Test: `tests/test_api_client.py` (append 4 tests using FakeSdk helpers)

- [ ] **Step 1: Append FakeSdk helpers and 4 tests to test_api_client.py**

```python
import anthropic
from nexus.api.client import AnthropicClient, ModelTier
from nexus.auth.errors import AuthError
from nexus.capabilities.registry import CapabilitySet


# ---------------------------------------------------------------------------
# FakeSdk helpers -- local to this file, only used for AnthropicClient tests
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class _FakeSdkMessages:
    response: object
    side_effect: Exception | None = None
    last_kwargs: dict[str, Any] = field(default_factory=dict)

    def create(self, **kwargs: Any) -> object:
        self.last_kwargs = dict(kwargs)
        if self.side_effect is not None:
            raise self.side_effect
        return self.response


@dataclass(slots=True)
class _FakeSdk:
    messages: _FakeSdkMessages
    model_list: list[Any] = field(default_factory=list)

    @property
    def models(self) -> Any:
        items = self.model_list
        return SimpleNamespace(list=lambda: items)


_CANNED_RESPONSE = SimpleNamespace(
    content=[SimpleNamespace(type="text", text="ok")],
    stop_reason="end_turn",
    usage=SimpleNamespace(
        input_tokens=10,
        output_tokens=5,
        cache_creation_input_tokens=3,
        cache_read_input_tokens=7,
    ),
)


def _make_client(messages_fake: _FakeSdkMessages) -> AnthropicClient:
    """Construct AnthropicClient with injected FakeSdk (empty model list -> fallback)."""
    return AnthropicClient(
        api_key="test-key",
        capabilities=CapabilitySet.none(),
        _sdk_client=_FakeSdk(messages=messages_fake),
    )


def _make_httpx_response(status_code: int) -> httpx.Response:
    return httpx.Response(
        status_code, request=httpx.Request("POST", "https://api.anthropic.com")
    )


# ---------------------------------------------------------------------------
# AnthropicClient tests
# ---------------------------------------------------------------------------


def test_complete_adds_cache_control_to_system() -> None:
    fake_messages = _FakeSdkMessages(response=_CANNED_RESPONSE)
    client = _make_client(fake_messages)
    client.complete(messages=[{"role": "user", "content": "hi"}], system="Be helpful.")
    system_block = fake_messages.last_kwargs["system"][0]
    assert system_block["cache_control"] == {"type": "ephemeral"}
    assert system_block["text"] == "Be helpful."


def test_complete_maps_authentication_error_to_auth_error() -> None:
    side_effect = anthropic.AuthenticationError(
        message="invalid key",
        response=_make_httpx_response(401),
        body={"error": {"message": "unauthorized"}},
    )
    fake_messages = _FakeSdkMessages(response=_CANNED_RESPONSE, side_effect=side_effect)
    client = _make_client(fake_messages)
    with pytest.raises(AuthError):
        client.complete(messages=[{"role": "user", "content": "hi"}], system="sys")


def test_complete_maps_api_status_error_to_anthropic_error() -> None:
    side_effect = anthropic.APIStatusError(
        message="server error",
        response=_make_httpx_response(500),
        body={"error": {"message": "internal"}},
    )
    fake_messages = _FakeSdkMessages(response=_CANNED_RESPONSE, side_effect=side_effect)
    client = _make_client(fake_messages)
    with pytest.raises(AnthropicError) as exc_info:
        client.complete(messages=[{"role": "user", "content": "hi"}], system="sys")
    assert exc_info.value.status_code == 500


def test_complete_logs_cache_tokens(caplog: Any) -> None:
    fake_messages = _FakeSdkMessages(response=_CANNED_RESPONSE)
    client = _make_client(fake_messages)
    with caplog.at_level(logging.INFO, logger="nexus.api.client"):
        client.complete(messages=[{"role": "user", "content": "hi"}], system="sys")
    assert "cache_write=3" in caplog.text
    assert "cache_read=7" in caplog.text
```

- [ ] **Step 2: Run the 4 tests to verify they fail**

```
poetry run pytest tests/test_api_client.py -k "complete" -v
```

Expected: 4 failures (client not yet updated -- but wait, client.py was already written in Task 3 Step 3). These tests should PASS since we wrote client.py already. If they pass, skip to Step 4.

> Note: In TDD the tests are written before the implementation. Since client.py was fully written in Task 3 to make all tests pass at once, these tests may already pass. Run them to confirm.

- [ ] **Step 3: Run tests**

```
poetry run pytest tests/test_api_client.py -k "complete" -v
```

Expected: `4 passed`

- [ ] **Step 4: Commit**

```bash
git add tests/test_api_client.py
git commit -m "test: add AnthropicClient.complete() tests (cache, errors, logging)"
```

---

## Task 5: FakeAnthropicClient

**Files:**
- Create: `tests/fakes/fake_anthropic_client.py`
- Modify: `tests/fakes/__init__.py`
- Test: `tests/test_api_client.py` (append 1 test)

- [ ] **Step 1: Append test to test_api_client.py**

```python
from tests.fakes.fake_anthropic_client import CANNED_MESSAGE, FakeAnthropicClient


def test_fake_client_records_calls() -> None:
    client = FakeAnthropicClient()
    client.complete(messages=[{"role": "user", "content": "hi"}], system="sys")
    assert len(client.calls) == 1
    assert client.calls[0]["system"] == "sys"
    assert client.calls[0]["messages"] == [{"role": "user", "content": "hi"}]
```

- [ ] **Step 2: Run test to verify it fails**

```
poetry run pytest tests/test_api_client.py::test_fake_client_records_calls -v
```

Expected: `ImportError: cannot import name 'FakeAnthropicClient'`

- [ ] **Step 3: Create tests/fakes/fake_anthropic_client.py**

```python
# tests/fakes/fake_anthropic_client.py
# Fake AnthropicClient for use in tests.
# Author: Pierre Grothe
# Date: 2026-05-07
"""FakeAnthropicClient: implements AnthropicClientProtocol with canned responses."""

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

__all__ = ["FakeAnthropicClient", "CANNED_MESSAGE"]

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


@dataclass(slots=True)
class FakeAnthropicClient:
    """Test double for AnthropicClientProtocol.

    Returns CANNED_MESSAGE on every complete() call and records all
    call arguments in self.calls for assertion in tests.
    """

    calls: list[dict[str, Any]] = field(default_factory=list)

    def complete(
        self,
        messages: list[dict[str, Any]],
        system: str,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 8192,
    ) -> object:
        """Record call arguments and return CANNED_MESSAGE.

        Args:
            messages: Conversation history passed by the caller.
            system: System prompt passed by the caller.
            tools: Tool definitions passed by the caller.
            max_tokens: Max tokens requested by the caller.

        Returns:
            CANNED_MESSAGE, a minimal Message-like namespace object.
        """
        self.calls.append({"messages": messages, "system": system, "tools": tools})
        return CANNED_MESSAGE
```

- [ ] **Step 4: Update tests/fakes/__init__.py**

Replace the file content:

```python
# tests/fakes/__init__.py
# Fake implementations used in tests. No mocks anywhere.
# Author: Pierre Grothe
# Date: 2026-05-07
"""Fake connectors and clients for use in tests."""

from tests.fakes.fake_anthropic_client import FakeAnthropicClient
from tests.fakes.fake_keychain import FakeKeychainClient
from tests.fakes.fake_sn_client import FakeServiceNowClient

__all__ = ["FakeAnthropicClient", "FakeKeychainClient", "FakeServiceNowClient"]
```

- [ ] **Step 5: Run test to verify it passes**

```
poetry run pytest tests/test_api_client.py::test_fake_client_records_calls -v
```

Expected: `PASSED`

- [ ] **Step 6: Commit**

```bash
git add tests/fakes/fake_anthropic_client.py tests/fakes/__init__.py tests/test_api_client.py
git commit -m "feat: add FakeAnthropicClient test double"
```

---

## Task 6: ToolRegistry test + exports + coverage gate

**Files:**
- Test: `tests/test_api_client.py` (append 1 test)
- Modify: `src/nexus/api/__init__.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Append ToolRegistry test**

```python
from nexus.api.tool_registry import ToolRegistry
from nexus.connectors.base import Tool
from nexus.connectors.registry import ConnectorRegistry


def test_tool_registry_assembles_anthropic_format() -> None:
    class _FakeConnector:
        name = "fake"

        def tools(self) -> list[Tool]:
            return [
                Tool(
                    name="fake_search",
                    description="Search for things",
                    parameters={
                        "type": "object",
                        "properties": {"q": {"type": "string"}},
                        "required": ["q"],
                    },
                    connector="fake",
                )
            ]

        async def call(self, tool_name: str, **kwargs: Any) -> Any:
            pass

    registry = ConnectorRegistry()
    registry.register(_FakeConnector())
    tool_reg = ToolRegistry(registry)

    tools = tool_reg.as_anthropic_tools()
    assert len(tools) == 1
    assert tools[0]["name"] == "fake_search"
    assert tools[0]["description"] == "Search for things"
    assert "input_schema" in tools[0]
```

- [ ] **Step 2: Run test**

```
poetry run pytest tests/test_api_client.py::test_tool_registry_assembles_anthropic_format -v
```

Expected: `PASSED` (ToolRegistry is already implemented)

- [ ] **Step 3: Update src/nexus/api/__init__.py**

Replace file content:

```python
# src/nexus/api/__init__.py
# Anthropic API layer public exports.
# Author: Pierre Grothe
# Date: 2026-05-07
"""Anthropic API client with prompt caching and tool registry."""

from nexus.api.client import AnthropicClient, AnthropicClientProtocol, ModelTier
from nexus.api.errors import AnthropicError
from nexus.api.logging_config import configure_logging
from nexus.api.tool_registry import ToolRegistry

__all__ = [
    "AnthropicClient",
    "AnthropicClientProtocol",
    "AnthropicError",
    "ModelTier",
    "ToolRegistry",
    "configure_logging",
]
```

- [ ] **Step 4: Run full test suite**

```
poetry run pytest -v
```

Expected: `48 passed` (39 existing + 9 new). All tests green.

- [ ] **Step 5: Raise coverage gate**

In `pyproject.toml`, change:

```toml
    "--cov-fail-under=40",
```

to:

```toml
    "--cov-fail-under=50",
```

- [ ] **Step 6: Run full suite to confirm coverage gate passes**

```
poetry run pytest -q
```

Expected: `48 passed`, coverage >= 50%, no failures.

- [ ] **Step 7: Final commit**

```bash
git add tests/test_api_client.py src/nexus/api/__init__.py pyproject.toml
git commit -m "feat: complete AnthropicClient MVP -- ModelTier, caching, logging, fakes"
```

---

## Self-Review Notes

- All 9 spec tests are covered across Tasks 1-6.
- `_discover_model` is tested as a module-level function (importable via `from nexus.api.client import _discover_model`).
- `FakeSdk` helpers (`_FakeSdkMessages`, `_FakeSdk`, `_CANNED_RESPONSE`, `_make_client`, `_make_httpx_response`) are defined locally in `test_api_client.py` -- they are not shared, so they do not belong in `tests/fakes/`.
- `AnthropicClient` is NOT tested with a real API call. All tests inject `_FakeSdk`.
- The `caplog` fixture (pytest built-in) is used for logging assertions -- this is a pytest fixture, not a mock.
- `monkeypatch` is used as a pytest fixture parameter (allowed by pre-edit hook).
- All imports at the top of `test_api_client.py` reference modules that exist after Task 3 Step 3. Earlier tasks only import what they need per test.
- Coverage rises from 42% to ~55% with these additions; the gate at 50% passes.
