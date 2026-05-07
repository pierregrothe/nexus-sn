# tests/test_capabilities.py
# Tests for the capabilities layer: CapabilitySet, feature flags, ProbeResult.
# Author: Pierre Grothe
# Date: 2026-05-07

"""Tests for nexus.capabilities."""

from nexus.capabilities.feature_flags import FEATURE_MAP, FeatureFlag, MCPServer
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
    import pytest
    with pytest.raises(Exception):
        caps.available_servers = frozenset()  # type: ignore[misc]
