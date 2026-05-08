# tests/test_cli_status.py
# Tests for `nexus status` and `nexus reauth` CLI commands.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for the status and reauth CLI commands."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nexus.cache import clear_cache
from nexus.capabilities.tier import TierDetector
from nexus.cli import app

runner = CliRunner()


def test_nexus_status_command_runs_and_prints_anonymous_for_isolated_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    clear_cache(TierDetector.detect)
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "ANONYMOUS" in result.output


def test_nexus_status_refresh_clears_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    clear_cache(TierDetector.detect)
    runner.invoke(app, ["status"])
    result = runner.invoke(app, ["status", "--refresh"])
    assert result.exit_code == 0


def test_nexus_reauth_with_no_flagged_returns_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    clear_cache(TierDetector.detect)
    result = runner.invoke(app, ["reauth"])
    assert result.exit_code == 0
    assert "All MCP servers authenticated" in result.output


def test_nexus_reauth_with_flagged_server_prints_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "mcp-needs-auth-cache.json").write_text(
        json.dumps({"claude.ai Marketing MCP": {"timestamp": 1, "id": "x"}}),
        encoding="utf-8",
    )
    (tmp_path / ".claude.json").write_text(
        json.dumps({"claudeAiMcpEverConnected": ["claude.ai Marketing MCP"]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    clear_cache(TierDetector.detect)
    result = runner.invoke(app, ["reauth"])
    assert result.exit_code == 0
    assert "claude /mcp" in result.output
    assert "Marketing MCP" in result.output


def test_nexus_reauth_with_unknown_server_returns_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    clear_cache(TierDetector.detect)
    result = runner.invoke(app, ["reauth", "--server", "marketing"])
    assert result.exit_code == 1
