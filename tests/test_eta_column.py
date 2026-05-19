# tests/test_eta_column.py
# Tests for ema_compute and WeightedETAColumn render behaviour.
# Author: Pierre Grothe
# Date: 2026-05-18

"""Tests for :mod:`nexus.ui.components.eta`.

Covers the pure ``ema_compute`` helper across edge cases and the
``WeightedETAColumn`` render output for estimating-mode + MM:SS mode.
"""

from __future__ import annotations

import io

from rich.console import Console
from rich.progress import Progress, TaskID
from rich.text import Text

from nexus.ui.components.eta import WeightedETAColumn, ema_compute


def test_ema_compute_with_empty_samples_returns_zero() -> None:
    assert ema_compute(()) == 0.0


def test_ema_compute_with_one_sample_returns_sample() -> None:
    assert ema_compute((7.5,)) == 7.5


def test_ema_compute_with_two_samples_biases_recent() -> None:
    result = ema_compute((1.0, 100.0), alpha=0.4)
    expected = 0.4 * 100.0 + 0.6 * 1.0
    assert abs(result - expected) < 1e-9


def test_ema_compute_with_homogeneous_samples_converges() -> None:
    assert ema_compute((10.0, 10.0, 10.0, 10.0)) == 10.0


def test_ema_compute_with_alpha_one_uses_latest_only() -> None:
    assert ema_compute((1.0, 2.0, 3.0), alpha=1.0) == 3.0


def _render_task(
    *,
    total: int,
    completed: int,
    sn_pct: float = 0,
    ema_duration_s: float = 0.0,
) -> Text:
    column = WeightedETAColumn()
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, width=120)
    with Progress(column, console=console) as progress:
        task_id: TaskID = progress.add_task(
            "test", total=total, sn_pct=sn_pct, ema_duration_s=ema_duration_s
        )
        progress.update(task_id, completed=completed)
        task = progress.tasks[0]
        return column.render(task)


def test_weightedetacolumn_with_no_samples_renders_estimating() -> None:
    text = _render_task(total=3, completed=0, sn_pct=0, ema_duration_s=0.0)
    assert "ETA: estimating..." in str(text)
    assert text.style == "dim"


def test_weightedetacolumn_with_one_sample_renders_mm_ss() -> None:
    text = _render_task(total=3, completed=1, sn_pct=50, ema_duration_s=60.0)
    assert str(text) == "ETA: 01:30"


def test_weightedetacolumn_blends_sn_percent_with_ema() -> None:
    text = _render_task(total=2, completed=0, sn_pct=25, ema_duration_s=40.0)
    assert str(text) == "ETA: 01:10"


def test_weightedetacolumn_renders_mm_ss_over_60_minutes() -> None:
    text = _render_task(total=10, completed=0, sn_pct=0, ema_duration_s=720.0)
    assert str(text) == "ETA: 120:00"


def test_weightedetacolumn_with_completed_equal_to_total_returns_zero() -> None:
    text = _render_task(total=3, completed=3, sn_pct=100, ema_duration_s=60.0)
    assert str(text) == "ETA: 00:00"


def test_weightedetacolumn_returns_rich_text_instance() -> None:
    text = _render_task(total=3, completed=0, sn_pct=0, ema_duration_s=0.0)
    assert isinstance(text, Text)
