# src/nexus/ui/components/eta.py
# EMA helper and Rich ProgressColumn for plugin-upgrade ETA estimation.
# Author: Pierre Grothe
# Date: 2026-05-18

"""ETA blend column for the batch-progress display.

:func:`ema_compute` is a pure exponential moving average over completed
durations -- alpha-weighted toward recent samples. :class:`WeightedETAColumn`
reads two task fields injected by :class:`RichBatchProgress`:

* ``sn_pct`` -- the percent ServiceNow reports for the in-flight item
* ``ema_duration_s`` -- the EMA of completed-item durations for the
  current plugin family, computed via :func:`ema_compute`

When ``ema_duration_s`` is zero (no prior samples), the column renders
``"ETA: estimating..."`` until the first item completes and seeds the
EMA. After that, the column renders ``"ETA: MM:SS"`` using the formula
``remaining_full_items * ema + (1 - sn_pct/100) * ema`` -- the time to
finish the current item, plus the EMA-weighted time for each remaining
item.
"""

from rich.progress import ProgressColumn, Task
from rich.text import Text

__all__ = ["WeightedETAColumn", "ema_compute"]

_DEFAULT_ALPHA = 0.4


def ema_compute(samples: tuple[float, ...], alpha: float = _DEFAULT_ALPHA) -> float:
    """Compute an exponential moving average over ``samples``.

    The recursive form ``ema_n = alpha * x_n + (1 - alpha) * ema_{n-1}``
    is seeded with ``samples[0]``. Larger alpha biases toward recent
    observations. Pure: same inputs always yield the same output.

    Args:
        samples: Tuple of completed-item durations in file order
            (oldest first, most recent last).
        alpha: Smoothing factor in ``(0, 1]``. Default ``0.4`` matches
            the ``WeightedETAColumn`` blend.

    Returns:
        ``0.0`` when ``samples`` is empty; the lone sample when it has
        length 1; otherwise the EMA over all samples.
    """
    if not samples:
        return 0.0
    ema = samples[0]
    for sample in samples[1:]:
        ema = alpha * sample + (1 - alpha) * ema
    return ema


class WeightedETAColumn(ProgressColumn):
    """Rich ProgressColumn that renders an EMA-blended ETA.

    Reads ``task.fields`` for ``sn_pct`` (int 0..100) and
    ``ema_duration_s`` (float seconds). On a task with no prior samples
    (``ema_duration_s == 0.0``), renders ``"ETA: estimating..."`` in
    the dim theme token. Otherwise renders ``"ETA: MM:SS"`` using the
    standard NEXUS MM:SS format (no HH:MM:SS rollover).
    """

    def render(self, task: Task) -> Text:
        """Return the column text for the given ``task``.

        Args:
            task: The Rich progress task being rendered.

        Returns:
            ``Text`` containing either the estimating placeholder
            (dim) or the formatted ``MM:SS`` ETA.
        """
        ema_duration_s = float(task.fields.get("ema_duration_s", 0.0) or 0.0)
        if ema_duration_s <= 0.0:
            return Text("ETA: estimating...", style="dim")
        sn_pct = int(task.fields.get("sn_pct", 0) or 0)
        total = int(task.total) if task.total else 0
        completed = int(task.completed)
        remaining_full = max(0, total - completed - 1)
        current_remaining = max(0.0, 1.0 - sn_pct / 100.0)
        eta_seconds = remaining_full * ema_duration_s + current_remaining * ema_duration_s
        minutes = int(eta_seconds) // 60
        seconds = int(eta_seconds) % 60
        return Text(f"ETA: {minutes:02d}:{seconds:02d}")
