# tests/test_capabilities_claude_config.py
# Tests for ClaudeCodeConfig types and the filesystem reader.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for nexus.capabilities.claude_config."""

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from nexus.capabilities.claude_config import (
    ClaudeCodeConfig,
    ClaudeCodeConfigReader,
    FilesystemClaudeCodeConfigReader,
)
from tests.fakes.fake_keychain import FakeKeychainClient


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


def test_filesystem_reader_reads_subscription_from_keychain(tmp_path: Path) -> None:
    keychain = FakeKeychainClient(
        {
            ("Claude Code-credentials", "alice"): json.dumps(
                {"claudeAiOauth": {"subscriptionType": "enterprise"}}
            )
        },
    )
    reader = FilesystemClaudeCodeConfigReader(keychain=keychain, home=tmp_path, os_user="alice")
    cfg = reader.read()
    assert cfg.subscription_type == "enterprise"


def test_filesystem_reader_falls_back_to_credentials_file_when_keychain_missing(
    tmp_path: Path,
) -> None:
    creds_file = tmp_path / ".claude" / ".credentials.json"
    creds_file.parent.mkdir(parents=True)
    creds_file.write_text(
        json.dumps({"claudeAiOauth": {"subscriptionType": "pro"}}), encoding="utf-8"
    )
    reader = FilesystemClaudeCodeConfigReader(
        keychain=FakeKeychainClient(), home=tmp_path, os_user="alice"
    )
    cfg = reader.read()
    assert cfg.subscription_type == "pro"


def test_filesystem_reader_returns_none_subscription_when_no_sources(tmp_path: Path) -> None:
    reader = FilesystemClaudeCodeConfigReader(
        keychain=FakeKeychainClient(), home=tmp_path, os_user="alice"
    )
    cfg = reader.read()
    assert cfg.subscription_type is None


def test_filesystem_reader_handles_malformed_keychain_payload(tmp_path: Path) -> None:
    keychain = FakeKeychainClient(
        {("Claude Code-credentials", "alice"): "not json"},
    )
    reader = FilesystemClaudeCodeConfigReader(keychain=keychain, home=tmp_path, os_user="alice")
    cfg = reader.read()
    assert cfg.subscription_type is None


def test_filesystem_reader_reads_org_mcp_servers_from_claude_json(tmp_path: Path) -> None:
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text(
        json.dumps({"claudeAiMcpEverConnected": ["claude.ai ValueMelody", "claude.ai BT1_MCP"]}),
        encoding="utf-8",
    )
    reader = FilesystemClaudeCodeConfigReader(
        keychain=FakeKeychainClient(), home=tmp_path, os_user="alice"
    )
    cfg = reader.read()
    assert cfg.org_mcp_servers == ("claude.ai ValueMelody", "claude.ai BT1_MCP")


def test_filesystem_reader_returns_empty_org_mcp_when_claude_json_missing(tmp_path: Path) -> None:
    reader = FilesystemClaudeCodeConfigReader(
        keychain=FakeKeychainClient(), home=tmp_path, os_user="alice"
    )
    cfg = reader.read()
    assert cfg.org_mcp_servers == ()


def test_filesystem_reader_handles_malformed_claude_json(tmp_path: Path) -> None:
    (tmp_path / ".claude.json").write_text("not json", encoding="utf-8")
    reader = FilesystemClaudeCodeConfigReader(
        keychain=FakeKeychainClient(), home=tmp_path, os_user="alice"
    )
    cfg = reader.read()
    assert cfg.org_mcp_servers == ()


def test_filesystem_reader_reads_needs_reauth_from_cache_file(tmp_path: Path) -> None:
    cache_file = tmp_path / ".claude" / "mcp-needs-auth-cache.json"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps(
            {
                "claude.ai Marketing MCP": {"timestamp": 1, "id": "x"},
                "claude.ai Microsoft 365": {"timestamp": 2, "id": "y"},
            }
        ),
        encoding="utf-8",
    )
    reader = FilesystemClaudeCodeConfigReader(
        keychain=FakeKeychainClient(), home=tmp_path, os_user="alice"
    )
    cfg = reader.read()
    assert set(cfg.needs_reauth) == {"claude.ai Marketing MCP", "claude.ai Microsoft 365"}
