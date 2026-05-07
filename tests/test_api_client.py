# tests/test_api_client.py
# API client layer tests.
# Author: Pierre Grothe
# Date: 2026-05-07
"""Tests for the NEXUS api layer."""

import logging
import logging.handlers
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

import anthropic
import httpx
import pytest

from nexus.api.client import _TIER_DEFAULTS, AnthropicClient, ModelTier, _discover_model
from nexus.api.errors import AnthropicError
from nexus.api.logging_config import configure_logging
from nexus.api.tool_registry import ToolRegistry
from nexus.auth.errors import AuthError
from nexus.capabilities.registry import CapabilitySet
from nexus.config.paths import NexusPaths
from nexus.connectors.base import Tool
from nexus.connectors.registry import ConnectorRegistry
from tests.fakes.fake_anthropic_client import FakeAnthropicClient


def test_anthropic_error_has_status_code_and_message() -> None:
    exc = AnthropicError(429, "Rate limit exceeded")
    assert exc.status_code == 429
    assert exc.message == "Rate limit exceeded"
    assert "429" in str(exc)


def test_configure_logging_creates_logs_directory_and_attaches_handlers(
    tmp_path: Path,
) -> None:
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    root.handlers.clear()
    try:
        paths = NexusPaths(root=tmp_path / ".nexus")
        configure_logging(paths)
        assert (tmp_path / ".nexus" / "logs").is_dir()
        handler_types = {type(h) for h in root.handlers}
        assert logging.handlers.TimedRotatingFileHandler in handler_types
        assert logging.StreamHandler in handler_types
        assert root.level == logging.INFO
    finally:
        for h in root.handlers:
            h.close()
        root.handlers.clear()
        root.handlers.extend(saved_handlers)
        root.level = saved_level


@dataclass(slots=True)
class _FakeModel:
    """Test double satisfying _ModelEntry -- used in model discovery tests."""

    id: str
    created_at: datetime


def test_model_tier_standard_default_is_sonnet() -> None:
    assert _TIER_DEFAULTS[ModelTier.STANDARD] == "claude-sonnet-4-6"


def test_discover_model_returns_newest_by_created_at() -> None:
    older = _FakeModel(id="claude-sonnet-4-5", created_at=datetime(2025, 9, 1, tzinfo=UTC))
    newer = _FakeModel(id="claude-sonnet-4-6", created_at=datetime(2025, 12, 1, tzinfo=UTC))

    class _FakeModels:
        def list(self) -> list[_FakeModel]:
            """Return fake model list."""
            return [older, newer]

    class _FakeClient:
        @property
        def models(self) -> _FakeModels:
            """Return fake models accessor."""
            return _FakeModels()

    result = _discover_model(_FakeClient(), ModelTier.STANDARD)
    assert result == "claude-sonnet-4-6"


def test_discover_model_falls_back_when_list_raises() -> None:
    class _FakeModels:
        def list(self) -> list[_FakeModel]:
            """Raise to simulate discovery failure."""
            raise RuntimeError("connection refused")

    class _FakeClient:
        @property
        def models(self) -> _FakeModels:
            """Return fake models accessor."""
            return _FakeModels()

    result = _discover_model(_FakeClient(), ModelTier.STANDARD)
    assert result == _TIER_DEFAULTS[ModelTier.STANDARD]


def test_discover_model_respects_env_var_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_MODEL_STANDARD", "claude-sonnet-4-99")

    class _FakeModels:
        def list(self) -> list[_FakeModel]:
            """Never called -- env var takes priority."""
            return []  # pragma: no cover

    class _FakeClient:
        @property
        def models(self) -> _FakeModels:
            """Never called -- env var takes priority."""
            return _FakeModels()  # pragma: no cover

    result = _discover_model(_FakeClient(), ModelTier.STANDARD)
    assert result == "claude-sonnet-4-99"


def test_discover_model_excludes_date_pinned_variants() -> None:
    date_pinned = _FakeModel(
        id="claude-sonnet-4-6-20250101",
        created_at=datetime(2025, 12, 1, tzinfo=UTC),
    )
    floating = _FakeModel(
        id="claude-sonnet-4-6",
        created_at=datetime(2025, 9, 1, tzinfo=UTC),
    )

    class _FakeModels:
        def list(self) -> list[_FakeModel]:
            """Return mix of date-pinned and floating model."""
            return [date_pinned, floating]

    class _FakeClient:
        @property
        def models(self) -> _FakeModels:
            """Return fake models accessor."""
            return _FakeModels()

    result = _discover_model(_FakeClient(), ModelTier.STANDARD)
    assert result == "claude-sonnet-4-6"


def test_discover_model_excludes_preview_models() -> None:
    preview = _FakeModel(
        id="claude-sonnet-4-preview",
        created_at=datetime(2025, 12, 1, tzinfo=UTC),
    )
    stable = _FakeModel(
        id="claude-sonnet-4-6",
        created_at=datetime(2025, 9, 1, tzinfo=UTC),
    )

    class _FakeModels:
        def list(self) -> list[_FakeModel]:
            """Return mix of preview and stable model."""
            return [preview, stable]

    class _FakeClient:
        @property
        def models(self) -> _FakeModels:
            """Return fake models accessor."""
            return _FakeModels()

    result = _discover_model(_FakeClient(), ModelTier.STANDARD)
    assert result == "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# FakeSdk helpers -- used only in this file for AnthropicClient tests
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _FakeSdkMessages:
    response: object
    side_effect: BaseException | None = None
    last_kwargs: dict[str, object] = field(default_factory=dict)

    def create(self, **kwargs: object) -> object:
        """Capture kwargs and return canned response or raise side_effect."""
        self.last_kwargs = dict(kwargs)
        if self.side_effect is not None:
            raise self.side_effect
        return self.response


@dataclass(slots=True)
class _FakeSdk:
    messages: _FakeSdkMessages
    model_list: list[object] = field(default_factory=list)

    @property
    def models(self) -> SimpleNamespace:
        """Return fake models namespace with list() method."""
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
    """Build minimal httpx.Response for constructing Anthropic SDK exceptions."""
    return httpx.Response(
        status_code, request=httpx.Request("POST", "https://api.anthropic.com")
    )


# ---------------------------------------------------------------------------
# AnthropicClient.complete() tests
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


def test_complete_logs_cache_tokens(caplog: pytest.LogCaptureFixture) -> None:
    fake_messages = _FakeSdkMessages(response=_CANNED_RESPONSE)
    client = _make_client(fake_messages)
    with caplog.at_level(logging.INFO, logger="nexus.api.client"):
        client.complete(messages=[{"role": "user", "content": "hi"}], system="sys")
    assert "cache_write=3" in caplog.text
    assert "cache_read=7" in caplog.text


def test_fake_client_records_calls() -> None:
    client = FakeAnthropicClient()
    client.complete(messages=[{"role": "user", "content": "hi"}], system="sys")
    assert len(client.calls) == 1
    assert client.calls[0]["system"] == "sys"
    assert client.calls[0]["messages"] == [{"role": "user", "content": "hi"}]


def test_tool_registry_assembles_anthropic_format() -> None:
    class _FakeConnector:
        name: ClassVar[str] = "fake"

        def tools(self) -> list[Tool]:
            """Return single fake tool."""
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

        async def call(self, tool_name: str, **kwargs: object) -> object:
            """No-op call implementation."""
            return None

    registry = ConnectorRegistry()
    registry.register(_FakeConnector())
    tool_reg = ToolRegistry(registry)

    tools = tool_reg.as_anthropic_tools()
    assert len(tools) == 1
    assert tools[0]["name"] == "fake_search"
    assert tools[0]["description"] == "Search for things"
    assert "input_schema" in tools[0]
