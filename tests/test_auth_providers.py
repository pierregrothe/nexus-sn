# tests/test_auth_providers.py
# Tests for AuthProvider Protocol, ClaudeCodeOAuthProvider, and the default chain.
# Author: Pierre Grothe
# Date: 2026-05-07

"""Tests for nexus.auth.providers and nexus.auth.oauth."""

import json
from pathlib import Path

import pytest

from nexus.auth.errors import AuthError
from nexus.auth.oauth import ClaudeCodeOAuthProvider
from tests.fakes.fake_auth_provider import FakeAuthProvider


def test_fake_auth_provider_default_is_available() -> None:
    fake = FakeAuthProvider()
    assert fake.is_available() is True
    assert fake.name == "fake"


def test_fake_auth_provider_returns_configured_unavailability() -> None:
    fake = FakeAuthProvider(available=False)
    assert fake.is_available() is False


def _write_credentials(path: Path, access_token: str) -> None:
    """Write a credentials.json file at path with the given accessToken."""
    creds = {"claudeAiOauth": {"accessToken": access_token, "refreshToken": "ref-xyz"}}
    path.write_text(json.dumps(creds), encoding="utf-8")


def test_oauth_provider_name_is_claude_code_oauth() -> None:
    assert ClaudeCodeOAuthProvider().name == "claude_code_oauth"


def test_oauth_provider_is_available_true_with_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok-from-env")
    assert ClaudeCodeOAuthProvider().is_available() is True


def test_oauth_provider_is_available_true_with_credentials_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    _write_credentials(tmp_path / ".credentials.json", "tok-from-file")
    assert ClaudeCodeOAuthProvider().is_available() is True


def test_oauth_provider_is_available_false_when_nothing_present(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.delenv("USER", raising=False)
    assert ClaudeCodeOAuthProvider().is_available() is False


def test_oauth_provider_is_available_false_when_credentials_file_malformed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.delenv("USER", raising=False)
    (tmp_path / ".credentials.json").write_text("not json", encoding="utf-8")
    assert ClaudeCodeOAuthProvider().is_available() is False


def test_oauth_provider_create_client_uses_auth_token_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok-from-env")
    client = ClaudeCodeOAuthProvider().create_client(max_retries=3)
    assert client.auth_token == "tok-from-env"
    assert client.api_key is None


def test_oauth_provider_create_client_uses_auth_token_from_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    _write_credentials(tmp_path / ".credentials.json", "tok-from-file")
    client = ClaudeCodeOAuthProvider().create_client(max_retries=3)
    assert client.auth_token == "tok-from-file"


def test_oauth_provider_priority_env_over_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok-from-env")
    _write_credentials(tmp_path / ".credentials.json", "tok-from-file")
    client = ClaudeCodeOAuthProvider().create_client(max_retries=3)
    assert client.auth_token == "tok-from-env"


def test_oauth_provider_create_client_raises_when_no_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "nonexistent"))
    monkeypatch.delenv("USER", raising=False)
    with pytest.raises(AuthError):
        ClaudeCodeOAuthProvider().create_client(max_retries=3)
