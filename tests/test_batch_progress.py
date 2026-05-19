# tests/test_batch_progress.py
# Tests for RichBatchProgress, PlainBatchProgress, and make_batch_progress factory.
# Author: Pierre Grothe
# Date: 2026-05-18

"""Tests for :mod:`nexus.ui.components.batch_progress`.

Covers protocol satisfaction, transient per-item tasks, EmaPriorStore
read/write, output routing, no-CR contract for PlainBatchProgress, and
factory profile-dispatch across all four RenderProfiles.
"""

from __future__ import annotations

import io
from pathlib import Path

from rich.console import Console

from nexus.ui.capabilities import (
    ColorDepth,
    RenderProfile,
    TerminalCapabilities,
)
from nexus.ui.components.batch_progress import (
    BatchProgressProtocol,
    PlainBatchProgress,
    RichBatchProgress,
    make_batch_progress,
)
from nexus.ui.components.eta_store import EmaPriorStore
from nexus.ui.render_context import RenderContext
from nexus.ui.theme import NEXUS_THEME


def _ctx(profile: RenderProfile) -> tuple[RenderContext, io.StringIO]:
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, width=120, theme=NEXUS_THEME)
    caps = TerminalCapabilities(
        is_tty=True,
        is_ci=False,
        color_depth=ColorDepth.TRUECOLOR,
        cols=120,
        rows=40,
        legacy_windows=False,
        term_program="",
        is_dumb_terminal=False,
        is_multiplexer=False,
        no_color_env=False,
        forced_plain=False,
        supports_hyperlinks=True,
    )
    return RenderContext(console=console, caps=caps, profile=profile), buffer


def _store(tmp_path: Path) -> EmaPriorStore:
    return EmaPriorStore(cache_path=tmp_path / "eta.jsonl")


def test_make_batch_progress_returns_rich_for_rich_profile(tmp_path: Path) -> None:
    ctx, _ = _ctx(RenderProfile.RICH)
    bp = make_batch_progress(ctx, total=2, store=_store(tmp_path))
    assert isinstance(bp, RichBatchProgress)


def test_make_batch_progress_returns_rich_for_basic_profile(tmp_path: Path) -> None:
    ctx, _ = _ctx(RenderProfile.BASIC)
    bp = make_batch_progress(ctx, total=2, store=_store(tmp_path))
    assert isinstance(bp, RichBatchProgress)


def test_make_batch_progress_returns_plain_for_legacy_profile(tmp_path: Path) -> None:
    ctx, _ = _ctx(RenderProfile.LEGACY)
    bp = make_batch_progress(ctx, total=2, store=_store(tmp_path))
    assert isinstance(bp, PlainBatchProgress)


def test_make_batch_progress_returns_plain_for_plain_profile(tmp_path: Path) -> None:
    ctx, _ = _ctx(RenderProfile.PLAIN)
    bp = make_batch_progress(ctx, total=2, store=_store(tmp_path))
    assert isinstance(bp, PlainBatchProgress)


def test_make_batch_progress_results_satisfy_protocol_runtime_check(tmp_path: Path) -> None:
    for profile in (
        RenderProfile.RICH,
        RenderProfile.BASIC,
        RenderProfile.LEGACY,
        RenderProfile.PLAIN,
    ):
        ctx, _ = _ctx(profile)
        bp = make_batch_progress(ctx, total=1, store=_store(tmp_path))
        assert isinstance(bp, BatchProgressProtocol)


def test_richbatchprogress_finish_item_records_to_store_on_success(tmp_path: Path) -> None:
    ctx, _ = _ctx(RenderProfile.RICH)
    store = _store(tmp_path)
    with make_batch_progress(ctx, total=1, store=store) as bp:
        assert isinstance(bp, RichBatchProgress)
        bp.start_batch(1)
        item_id = bp.start_item("plugin.a", "com.snc.x")
        bp.finish_item(item_id, duration_s=42.0, family="com.snc.x", success=True)
    assert store.load("com.snc.x") == (42.0,)


def test_richbatchprogress_finish_item_skips_store_on_failure(tmp_path: Path) -> None:
    ctx, _ = _ctx(RenderProfile.RICH)
    store = _store(tmp_path)
    with make_batch_progress(ctx, total=1, store=store) as bp:
        assert isinstance(bp, RichBatchProgress)
        bp.start_batch(1)
        item_id = bp.start_item("plugin.a", "com.snc.x")
        bp.finish_item(item_id, duration_s=42.0, family="com.snc.x", success=False)
    assert store.load("com.snc.x") == ()


def test_richbatchprogress_start_item_seeds_ema_from_store(tmp_path: Path) -> None:
    ctx, _ = _ctx(RenderProfile.RICH)
    store = _store(tmp_path)
    store.record("com.snc.x", duration_s=30.0)
    store.record("com.snc.x", duration_s=60.0)
    with make_batch_progress(ctx, total=1, store=store) as bp:
        assert isinstance(bp, RichBatchProgress)
        bp.start_batch(1)
        item_id = bp.start_item("plugin.a", "com.snc.x")
        task = next(t for t in bp._progress.tasks if t.id == item_id)
        assert task.fields["ema_duration_s"] > 0.0


def test_richbatchprogress_update_item_changes_sn_pct(tmp_path: Path) -> None:
    ctx, _ = _ctx(RenderProfile.RICH)
    store = _store(tmp_path)
    with make_batch_progress(ctx, total=1, store=store) as bp:
        assert isinstance(bp, RichBatchProgress)
        bp.start_batch(1)
        item_id = bp.start_item("plugin.a", "com.snc.x")
        bp.update_item(item_id, sn_pct=50)
        task = next(t for t in bp._progress.tasks if t.id == item_id)
        assert task.fields["sn_pct"] == 50


def test_richbatchprogress_console_property_returns_progress_console(tmp_path: Path) -> None:
    ctx, _ = _ctx(RenderProfile.RICH)
    bp = make_batch_progress(ctx, total=1, store=_store(tmp_path))
    assert isinstance(bp, RichBatchProgress)
    assert bp.console is ctx.console


def test_plainbatchprogress_start_item_emits_upgrading_line(tmp_path: Path) -> None:
    ctx, buffer = _ctx(RenderProfile.PLAIN)
    bp = make_batch_progress(ctx, total=1, store=_store(tmp_path))
    assert isinstance(bp, PlainBatchProgress)
    bp.start_batch(1)
    bp.start_item("plugin.a", "com.snc.x")
    assert "upgrading plugin.a" in buffer.getvalue()


def test_plainbatchprogress_update_item_emits_percent_line(tmp_path: Path) -> None:
    ctx, buffer = _ctx(RenderProfile.PLAIN)
    bp = make_batch_progress(ctx, total=1, store=_store(tmp_path))
    assert isinstance(bp, PlainBatchProgress)
    item_id = bp.start_item("plugin.a", "com.snc.x")
    bp.update_item(item_id, sn_pct=50)
    assert "50%" in buffer.getvalue()


def test_plainbatchprogress_finish_item_success_emits_upgraded_line(tmp_path: Path) -> None:
    ctx, buffer = _ctx(RenderProfile.PLAIN)
    bp = make_batch_progress(ctx, total=1, store=_store(tmp_path))
    assert isinstance(bp, PlainBatchProgress)
    item_id = bp.start_item("plugin.a", "com.snc.x")
    bp.finish_item(item_id, duration_s=12.0, family="com.snc.x", success=True)
    assert "upgraded plugin.a" in buffer.getvalue()
    assert "00:12" in buffer.getvalue()


def test_plainbatchprogress_finish_item_failure_emits_failed_line(tmp_path: Path) -> None:
    ctx, buffer = _ctx(RenderProfile.PLAIN)
    bp = make_batch_progress(ctx, total=1, store=_store(tmp_path))
    assert isinstance(bp, PlainBatchProgress)
    item_id = bp.start_item("plugin.a", "com.snc.x")
    bp.finish_item(item_id, duration_s=5.0, family="com.snc.x", success=False)
    assert "failed plugin.a" in buffer.getvalue()


def test_plainbatchprogress_output_contains_no_carriage_return(tmp_path: Path) -> None:
    ctx, buffer = _ctx(RenderProfile.PLAIN)
    bp = make_batch_progress(ctx, total=2, store=_store(tmp_path))
    assert isinstance(bp, PlainBatchProgress)
    bp.start_batch(2)
    item_id = bp.start_item("plugin.a", "com.snc.x")
    bp.update_item(item_id, sn_pct=50)
    bp.finish_item(item_id, duration_s=12.0, family="com.snc.x", success=True)
    assert "\r" not in buffer.getvalue()


def test_plainbatchprogress_finish_item_skips_store_on_failure(tmp_path: Path) -> None:
    ctx, _ = _ctx(RenderProfile.PLAIN)
    store = _store(tmp_path)
    bp = make_batch_progress(ctx, total=1, store=store)
    assert isinstance(bp, PlainBatchProgress)
    item_id = bp.start_item("plugin.a", "com.snc.x")
    bp.finish_item(item_id, duration_s=12.0, family="com.snc.x", success=False)
    assert store.load("com.snc.x") == ()


def test_plainbatchprogress_finish_item_records_store_on_success(tmp_path: Path) -> None:
    ctx, _ = _ctx(RenderProfile.PLAIN)
    store = _store(tmp_path)
    bp = make_batch_progress(ctx, total=1, store=store)
    assert isinstance(bp, PlainBatchProgress)
    item_id = bp.start_item("plugin.a", "com.snc.x")
    bp.finish_item(item_id, duration_s=12.0, family="com.snc.x", success=True)
    assert store.load("com.snc.x") == (12.0,)


def test_plainbatchprogress_context_manager_no_op(tmp_path: Path) -> None:
    ctx, _ = _ctx(RenderProfile.PLAIN)
    with make_batch_progress(ctx, total=1, store=_store(tmp_path)) as bp:
        assert isinstance(bp, PlainBatchProgress)
