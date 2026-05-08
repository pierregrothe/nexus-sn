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
    _str_field,
    _subscription_from_account,
)
from tests.fakes.fake_keychain import FakeKeychainClient

# ---------------------------------------------------------------------------
# _subscription_from_account unit tests
# ---------------------------------------------------------------------------


def test_subscription_from_account_with_none_returns_none() -> None:
    assert _subscription_from_account(None) is None


def test_subscription_from_account_maps_claude_enterprise_to_enterprise() -> None:
    assert _subscription_from_account({"organizationType": "claude_enterprise"}) == "enterprise"


def test_subscription_from_account_passes_through_pro() -> None:
    assert _subscription_from_account({"organizationType": "pro"}) == "pro"


def test_subscription_from_account_returns_none_for_unknown_type() -> None:
    assert _subscription_from_account({"organizationType": "free_tier"}) is None


def test_subscription_from_account_returns_none_when_key_missing() -> None:
    assert _subscription_from_account({}) is None


# ---------------------------------------------------------------------------
# _str_field unit tests
# ---------------------------------------------------------------------------


def test_str_field_returns_string_value() -> None:
    assert _str_field({"email": "a@b.com"}, "email") == "a@b.com"


def test_str_field_returns_none_for_none_account() -> None:
    assert _str_field(None, "email") is None


def test_str_field_returns_none_when_key_missing() -> None:
    assert _str_field({}, "email") is None


def test_str_field_returns_none_for_non_string_value() -> None:
    assert _str_field({"count": 5}, "count") is None


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


def test_filesystem_reader_reads_email_and_org_from_oauth_account(tmp_path: Path) -> None:
    (tmp_path / ".claude.json").write_text(
        json.dumps(
            {
                "oauthAccount": {
                    "emailAddress": "alice@example.com",
                    "displayName": "Alice",
                    "organizationName": "Example Corp",
                    "organizationType": "claude_enterprise",
                }
            }
        ),
        encoding="utf-8",
    )
    reader = FilesystemClaudeCodeConfigReader(
        keychain=FakeKeychainClient(), home=tmp_path, os_user="alice"
    )
    cfg = reader.read()
    assert cfg.email == "alice@example.com"
    assert cfg.display_name == "Alice"
    assert cfg.organization_name == "Example Corp"
    assert cfg.subscription_type == "enterprise"


def test_filesystem_reader_subscription_falls_back_to_oauth_account(tmp_path: Path) -> None:
    (tmp_path / ".claude.json").write_text(
        json.dumps({"oauthAccount": {"organizationType": "claude_enterprise"}}),
        encoding="utf-8",
    )
    reader = FilesystemClaudeCodeConfigReader(
        keychain=FakeKeychainClient(), home=tmp_path, os_user="alice"
    )
    cfg = reader.read()
    assert cfg.subscription_type == "enterprise"


def test_filesystem_reader_ignores_non_list_mcp_servers(tmp_path: Path) -> None:
    (tmp_path / ".claude.json").write_text(
        json.dumps({"claudeAiMcpEverConnected": "not-a-list"}),
        encoding="utf-8",
    )
    reader = FilesystemClaudeCodeConfigReader(
        keychain=FakeKeychainClient(), home=tmp_path, os_user="alice"
    )
    cfg = reader.read()
    assert cfg.org_mcp_servers == ()


def test_filesystem_reader_handles_malformed_needs_reauth_cache(tmp_path: Path) -> None:
    cache_dir = tmp_path / ".claude"
    cache_dir.mkdir()
    (cache_dir / "mcp-needs-auth-cache.json").write_text("not json", encoding="utf-8")
    reader = FilesystemClaudeCodeConfigReader(
        keychain=FakeKeychainClient(), home=tmp_path, os_user="alice"
    )
    cfg = reader.read()
    assert cfg.needs_reauth == ()


def test_filesystem_reader_ignores_credentials_file_that_is_json_array(tmp_path: Path) -> None:
    creds_dir = tmp_path / ".claude"
    creds_dir.mkdir()
    (creds_dir / ".credentials.json").write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    reader = FilesystemClaudeCodeConfigReader(
        keychain=FakeKeychainClient(), home=tmp_path, os_user="alice"
    )
    cfg = reader.read()
    assert cfg.subscription_type is None


def test_filesystem_reader_ignores_non_dict_claude_ai_oauth(tmp_path: Path) -> None:
    keychain = FakeKeychainClient(
        {("Claude Code-credentials", "alice"): json.dumps({"claudeAiOauth": "not-a-dict"})}
    )
    reader = FilesystemClaudeCodeConfigReader(keychain=keychain, home=tmp_path, os_user="alice")
    cfg = reader.read()
    assert cfg.subscription_type is None
