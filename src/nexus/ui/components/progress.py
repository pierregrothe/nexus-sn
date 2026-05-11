# src/nexus/ui/components/progress.py
# Styled Rich Progress factory for long-running CLI operations.
# Author: Pierre Grothe
# Date: 2026-05-11

"""nexus_progress: brand-styled Rich Progress.

Rich's Progress is already a context manager with mutable state, so we
expose a factory function rather than wrapping it in a Pydantic model.
"""

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Column

__all__ = ["nexus_progress"]


def nexus_progress(console: Console) -> Progress:
    """Return a brand-styled Progress bound to ``console``.

    Args:
        console: The Console to render onto. Caller-controlled so the same
            Console (with its theme) stays in scope for prompts during the
            operation.

    Returns:
        A transient Progress with spinner, text, bar, M/N count, and elapsed
        columns. The bar uses the project gradient endpoints; the spinner
        uses the brand blue.
    """
    return Progress(
        SpinnerColumn(style="border.start"),
        TextColumn(
            "[label]{task.description}",
            table_column=Column(min_width=50, no_wrap=True),
        ),
        BarColumn(
            bar_width=30,
            style="bar.back",
            complete_style="border.end",
            finished_style="border.end",
            pulse_style="border.end",
        ),
        MofNCompleteColumn(table_column=Column(style="border.end", no_wrap=True)),
        TimeElapsedColumn(table_column=Column(style="dim", no_wrap=True)),
        console=console,
        transient=True,
    )
