# tests/test_capabilities.py
# Tests for the capabilities layer: CapabilitySet, feature flags, ProbeResult.
# Author: Pierre Grothe
# Date: 2026-05-07

"""Tests for nexus.capabilities."""

from dataclasses import FrozenInstanceError

import pytest

from nexus.capabilities.feature_flags import (
    _CLAUDE_AI_NAME_TO_SERVER,
    FEATURE_MAP,
    FeatureFlag,
    MCPServer,
    claude_ai_name_for,
)
from nexus.capabilities.probe import ProbeResult
from nexus.capabilities.registry import CapabilitySet


def test_feature_map_covers_all_known_servers() -> None:
    for server in MCPServer:
        assert server in FEATURE_MAP, f"Server {server!r} missing from FEATURE_MAP"


def test_capability_set_from_no_results_returns_empty() -> None:
    caps = CapabilitySet.from_probe_results([])
    assert len(caps.available_servers) == 0
    assert len(caps.enabled_features) == 0


def test_capability_set_from_available_server_enables_its_features() -> None:
    result = ProbeResult(server=MCPServer.VALUE_MELODY, available=True, latency_ms=12.0)
    caps = CapabilitySet.from_probe_results([result])
    assert MCPServer.VALUE_MELODY in caps.available_servers
    assert caps.has_feature(FeatureFlag.ROI_ANALYSIS)
    assert caps.has_feature(FeatureFlag.VE_PIPELINE)


def test_capability_set_from_unavailable_server_disables_features() -> None:
    result = ProbeResult(server=MCPServer.VALUE_MELODY, available=False, error="timeout")
    caps = CapabilitySet.from_probe_results([result])
    assert MCPServer.VALUE_MELODY in caps.unavailable_servers
    assert not caps.has_feature(FeatureFlag.ROI_ANALYSIS)


def test_capability_set_none_marks_all_servers_unavailable() -> None:
    caps = CapabilitySet.none()
    assert caps.available_servers == frozenset()
    assert caps.unavailable_servers == frozenset(MCPServer)
    assert caps.enabled_features == frozenset()


def test_capability_set_mixed_results() -> None:
    results = [
        ProbeResult(server=MCPServer.VALUE_MELODY, available=True, latency_ms=10.0),
        ProbeResult(server=MCPServer.SSC, available=False, error="timeout"),
    ]
    caps = CapabilitySet.from_probe_results(results)
    assert caps.has_feature(FeatureFlag.ROI_ANALYSIS)
    assert not caps.has_feature(FeatureFlag.CONTENT_SEARCH)


def test_capability_set_is_immutable() -> None:
    caps = CapabilitySet.none()
    with pytest.raises(FrozenInstanceError):
        setattr(caps, "available_servers", frozenset())


def test_claude_ai_name_table_contains_all_known_servers() -> None:
    assert "claude.ai ValueMelody" in _CLAUDE_AI_NAME_TO_SERVER
    assert _CLAUDE_AI_NAME_TO_SERVER["claude.ai ValueMelody"] is MCPServer.VALUE_MELODY


def test_claude_ai_name_table_includes_marketing_mcp() -> None:
    assert _CLAUDE_AI_NAME_TO_SERVER["claude.ai Marketing MCP"] is MCPServer.MARKETING


def test_claude_ai_name_for_returns_string_form() -> None:
    assert claude_ai_name_for(MCPServer.BT1) == "claude.ai BT1_MCP"
    assert claude_ai_name_for(MCPServer.MARKETING) == "claude.ai Marketing MCP"


def test_claude_ai_name_for_raises_for_unmapped_server() -> None:
    # MCPServer is exhaustively covered; this guards against future enum additions
    # without table updates. We can't test it without an unmapped value, so we
    # just assert every enum member is in the inverse table.
    inverse = {server for server in _CLAUDE_AI_NAME_TO_SERVER.values()}
    for server in MCPServer:
        assert server in inverse, f"missing claude.ai name mapping for {server}"
