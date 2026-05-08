# tests/test_cli_status.py
# Tests for `nexus status` and `nexus reauth` CLI commands.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for the status and reauth CLI commands."""

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
    assert "Anonymous" in result.output


def test_nexus_status_refresh_clears_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    clear_cache(TierDetector.detect)
    runner.invoke(app, ["status"])
    result = runner.invoke(app, ["status", "--refresh"])
    assert result.exit_code == 0
