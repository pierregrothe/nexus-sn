# src/nexus/ui/components/batch_progress.py
# BatchProgressProtocol + Rich/Plain implementations + factory for plugin batches.
# Author: Pierre Grothe
# Date: 2026-05-18

r"""Adaptive progress display for plugin upgrade batches.

The :class:`BatchProgressProtocol` defines the contract between the CLI
command (which knows the user-facing target list) and
:class:`~nexus.plugins.executor.PluginExecutor` (which knows when items
start, update, and finish). Two implementations cover the four
RenderProfiles:

* :class:`RichBatchProgress` -- RICH/BASIC. Wraps a ``rich.progress.Progress``
  with an overall task and transient per-item tasks. Brand spinner on
  RICH (omitted on BASIC). ``WeightedETAColumn`` reads its EMA seed
  from a per-family :class:`EmaPriorStore`.
* :class:`PlainBatchProgress` -- LEGACY/PLAIN. Prints one ``console.print``
  line per event. No Live region, no ``\r`` rewrites, multiplexer-safe.

Both implementations route caller output through their ``console``
property so ``console.print(...)`` interleaves correctly with the Live
region (RICH/BASIC) or appears in stream order (LEGACY/PLAIN). Both are
context managers; ``with make_batch_progress(ctx, total=N) as bp:`` is
the standard call site.
"""

from dataclasses import dataclass, field
from types import TracebackType
from typing import Protocol, runtime_checkable

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    ProgressColumn,
    SpinnerColumn,
    TaskID,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)

from nexus.ui.capabilities import RenderProfile
from nexus.ui.components.eta import WeightedETAColumn, ema_compute
from nexus.ui.components.eta_store import EmaPriorStore
from nexus.ui.render_context import RenderContext

__all__ = [
    "BatchProgressProtocol",
    "PlainBatchProgress",
    "RichBatchProgress",
    "make_batch_progress",
]


@runtime_checkable
class BatchProgressProtocol(Protocol):
    """Contract for driving a plugin-upgrade batch progress display.

    Implementations are returned by :func:`make_batch_progress` and
    used as context managers from CLI commands.
    """

    @property
    def console(self) -> Console:
        """Console implementations should route caller prints through."""
        ...  # pragma: no cover -- Protocol stub

    def start_batch(self, total: int) -> int:
        """Begin a batch of ``total`` items; return the overall task id."""
        ...  # pragma: no cover -- Protocol stub

    def start_item(self, plugin_id: str, family: str) -> int:
        """Begin a per-item task; return its task id."""
        ...  # pragma: no cover -- Protocol stub

    def update_item(self, task_id: int, sn_pct: int) -> None:
        """Update the in-flight percent for ``task_id``."""
        ...  # pragma: no cover -- Protocol stub

    def finish_item(self, task_id: int, duration_s: float, family: str, success: bool) -> None:
        """Mark ``task_id`` complete; on success record duration."""
        ...  # pragma: no cover -- Protocol stub

    def __enter__(self) -> BatchProgressProtocol:
        """Activate the display."""
        ...  # pragma: no cover -- Protocol stub

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Tear down the display, cleaning up the Live region if any."""
        ...  # pragma: no cover -- Protocol stub


def _build_rich_progress(console: Console, *, with_spinner: bool) -> Progress:
    """Construct the Rich ``Progress`` used by ``RichBatchProgress``.

    Args:
        console: Console the Progress renders onto.
        with_spinner: Include a SpinnerColumn (RICH only) when True.

    Returns:
        Configured Rich ``Progress`` instance (not yet started).
    """
    columns: list[ProgressColumn] = []
    if with_spinner:
        columns.append(SpinnerColumn(style="border.start"))
    columns.extend(
        [
            TextColumn("[label]{task.description}"),
            BarColumn(
                bar_width=30,
                style="bar.back",
                complete_style="border.end",
                finished_style="border.end",
            ),
            TaskProgressColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            WeightedETAColumn(),
        ]
    )
    return Progress(*columns, console=console, transient=False)


@dataclass(slots=True)
class RichBatchProgress:
    """RICH/BASIC profile batch-progress driver.

    Wraps a ``rich.progress.Progress`` with an overall task and
    transient per-item tasks. Records successful-item durations to
    ``store`` so future batches' WeightedETA seed improves over time.

    Attributes:
        _progress: The Rich Progress instance.
        store: Per-family duration history; read on ``start_item`` to
            seed the EMA, appended on ``finish_item(..., success=True)``.
        _overall_task_id: Task id returned by ``start_batch``; -1 until set.
    """

    _progress: Progress
    store: EmaPriorStore
    _overall_task_id: int = -1

    @property
    def console(self) -> Console:
        """Console attached to the underlying Progress."""
        return self._progress.console

    def start_batch(self, total: int) -> int:
        """Register the overall task tracking ``total`` items."""
        task_id = self._progress.add_task(
            "Upgrading plugins",
            total=total,
            sn_pct=0,
            ema_duration_s=0.0,
        )
        self._overall_task_id = int(task_id)
        return self._overall_task_id

    def start_item(self, plugin_id: str, family: str) -> int:
        """Begin a per-item transient task seeded with the family's EMA."""
        ema = ema_compute(self.store.load(family))
        task_id = self._progress.add_task(
            f"  {plugin_id}",
            total=100,
            sn_pct=0,
            ema_duration_s=ema,
        )
        return int(task_id)

    def update_item(self, task_id: int, sn_pct: int) -> None:
        """Refresh the in-flight item's percent."""
        self._progress.update(TaskID(task_id), completed=sn_pct, sn_pct=sn_pct)

    def finish_item(self, task_id: int, duration_s: float, family: str, success: bool) -> None:
        """Complete the item; on success record duration to the store."""
        self._progress.update(TaskID(task_id), completed=100, sn_pct=100)
        self._progress.remove_task(TaskID(task_id))
        if self._overall_task_id >= 0:
            self._progress.advance(TaskID(self._overall_task_id), 1)
        if success:
            self.store.record(family, duration_s)

    def __enter__(self) -> RichBatchProgress:
        """Start the Live region."""
        self._progress.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Stop the Live region, restoring the terminal cleanly."""
        self._progress.stop()


@dataclass(slots=True)
class PlainBatchProgress:
    """LEGACY/PLAIN profile batch-progress driver.

    Emits one line per event via ``console.print``. No Live region; no
    carriage-return rewrites. Suitable for CI logs, tmux/screen
    sessions, and piped output.

    Attributes:
        console: Console all output flows through.
        store: Per-family duration history for parity with
            :class:`RichBatchProgress`; updated on
            ``finish_item(..., success=True)``.
        _next_task_id: Monotonic id source for ``start_item``.
        _start_times: Map task_id -> wall-clock seconds at start_item;
            consumed on finish_item.
        _plugin_ids: Map task_id -> plugin_id for the finish-line label.
    """

    console: Console
    store: EmaPriorStore
    _next_task_id: int = 0
    _start_times: dict[int, float] = field(default_factory=dict[int, float])
    _plugin_ids: dict[int, str] = field(default_factory=dict[int, str])

    def start_batch(self, total: int) -> int:
        """Print a one-line batch banner; return id 0 (no overall task)."""
        self.console.print(f"batch starting: {total} item(s)")
        return 0

    def start_item(self, plugin_id: str, family: str) -> int:
        """Print ``upgrading <plugin_id>``; return a monotonic task id."""
        del family
        task_id = self._next_task_id
        self._next_task_id += 1
        import time  # noqa: PLC0415

        self._start_times[task_id] = time.monotonic()
        self._plugin_ids[task_id] = plugin_id
        self.console.print(f"upgrading {plugin_id}")
        return task_id

    def update_item(self, task_id: int, sn_pct: int) -> None:
        """Print a percent update line for ``task_id``."""
        plugin_id = self._plugin_ids.get(task_id, "unknown")
        self.console.print(f"upgrading {plugin_id} {sn_pct}%")

    def finish_item(self, task_id: int, duration_s: float, family: str, success: bool) -> None:
        """Print the finish line and record duration on success."""
        plugin_id = self._plugin_ids.pop(task_id, "unknown")
        self._start_times.pop(task_id, None)
        minutes = int(duration_s) // 60
        seconds = int(duration_s) % 60
        stamp = f"{minutes:02d}:{seconds:02d}"
        verb = "upgraded" if success else "failed"
        self.console.print(f"{verb} {plugin_id} {stamp}")
        if success:
            self.store.record(family, duration_s)

    def __enter__(self) -> PlainBatchProgress:
        """No-op; PlainBatchProgress has no Live region to start."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """No-op."""
        return None


def make_batch_progress(
    ctx: RenderContext, total: int, store: EmaPriorStore
) -> BatchProgressProtocol:
    """Factory selecting the right implementation for ``ctx.profile``.

    Args:
        ctx: Render context describing the active terminal.
        total: Number of items in the upcoming batch. Stored on the
            overall task at ``start_batch`` time; passed here so the
            caller's ``with`` block is the single call site.
        store: Per-family duration cache shared with the executor.

    Returns:
        ``RichBatchProgress`` for RICH/BASIC profiles, otherwise
        ``PlainBatchProgress``. Both satisfy
        :class:`BatchProgressProtocol`.
    """
    del total
    if ctx.profile in {RenderProfile.RICH, RenderProfile.BASIC}:
        progress = _build_rich_progress(ctx.console, with_spinner=ctx.profile is RenderProfile.RICH)
        return RichBatchProgress(_progress=progress, store=store)
    return PlainBatchProgress(console=ctx.console, store=store)
