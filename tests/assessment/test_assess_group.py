# tests/assessment/test_assess_group.py
# Tests for the `nexus assess` Typer group callback (Story 05).
# Author: Pierre Grothe
# Date: 2026-06-29

"""Group-callback behavior for the restructured `nexus assess`.

The callback runs the gate/health path only when no subcommand is invoked and
maps the run_assess exit code onto typer.Exit; a subcommand short-circuits it.
"""

from __future__ import annotations

import pytest
import typer
from typer.testing import CliRunner

from nexus.cli import commands_assess
from nexus.cli.apps import app
from nexus.cli.commands_assess import assess_callback


class _RecordingAssess:
    """Fake run_assess that records kwargs and returns a fixed exit code."""

    def __init__(self, exit_code: int) -> None:
        """Store the exit code the fake should return."""
        self.exit_code = exit_code
        self.calls: list[dict[str, object]] = []

    def __call__(self, **kwargs: object) -> int:
        """Record the call kwargs and return the configured exit code."""
        self.calls.append(kwargs)
        return self.exit_code


def test_assess_callback_routes_options_to_run_assess(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_AUTO_UPDATE", "0")
    fake = _RecordingAssess(0)
    monkeypatch.setattr(commands_assess, "run_assess", fake)
    result = CliRunner().invoke(app, ["assess", "--for", "acme"])
    assert result.exit_code == 0
    assert len(fake.calls) == 1
    assert fake.calls[0]["for_template"] == "acme"


def test_assess_callback_maps_block_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_AUTO_UPDATE", "0")
    fake = _RecordingAssess(2)
    monkeypatch.setattr(commands_assess, "run_assess", fake)
    result = CliRunner().invoke(app, ["assess"])
    assert result.exit_code == 2


def test_assess_callback_skips_gate_when_subcommand_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _RecordingAssess(0)
    monkeypatch.setattr(commands_assess, "run_assess", fake)
    harness = typer.Typer()
    harness.callback(invoke_without_command=True)(assess_callback)

    @harness.command("noop")
    def _noop() -> None:  # pyright: ignore[reportUnusedFunction]
        """Placeholder subcommand proving the callback short-circuits."""

    result = CliRunner().invoke(harness, ["noop"])
    assert result.exit_code == 0
    assert fake.calls == []
