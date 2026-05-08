# nexus/capabilities/__init__.py
# MCP capability detection public exports.
# Author: Pierre Grothe
# Date: 2026-05-07

"""MCP server availability detection and feature flag management."""

from nexus.capabilities.claude_config import ClaudeCodeConfig, ClaudeCodeConfigReader
from nexus.capabilities.feature_flags import FEATURE_MAP, FeatureFlag
from nexus.capabilities.probe import MCPProbe, ProbeResult
from nexus.capabilities.registry import CapabilitySet

__all__ = [
    "FEATURE_MAP",
    "CapabilitySet",
    "ClaudeCodeConfig",
    "ClaudeCodeConfigReader",
    "FeatureFlag",
    "MCPProbe",
    "ProbeResult",
]
