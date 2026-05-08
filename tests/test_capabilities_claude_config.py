# tests/test_capabilities_claude_config.py
# Tests for ClaudeCodeConfig types and the filesystem reader.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for nexus.capabilities.claude_config."""

import dataclasses
from typing import Any

import pytest

from nexus.capabilities.claude_config import ClaudeCodeConfig, ClaudeCodeConfigReader


def test_claude_code_config_default_construction() -> None:
    cfg = ClaudeCodeConfig(
        subscription_type=None,
        org_mcp_servers=(),
        needs_reauth=(),
    )
    assert cfg.subscription_type is None
    assert cfg.org_mcp_servers == ()
    assert cfg.needs_reauth == ()


def test_claude_code_config_is_frozen() -> None:
    cfg = ClaudeCodeConfig(subscription_type="enterprise", org_mcp_servers=(), needs_reauth=())
    cfg_any: Any = cfg
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg_any.subscription_type = "pro"


def test_claude_code_config_reader_protocol_satisfied_by_simple_reader() -> None:
    """A minimal reader class structurally satisfies the Protocol."""

    class _OneShot:
        def read(self) -> ClaudeCodeConfig:
            return ClaudeCodeConfig(subscription_type=None, org_mcp_servers=(), needs_reauth=())

    reader: ClaudeCodeConfigReader = _OneShot()
    assert reader.read().subscription_type is None
