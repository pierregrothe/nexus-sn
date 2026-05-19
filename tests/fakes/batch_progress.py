# tests/fakes/batch_progress.py
# Recording BatchProgressProtocol fake for executor/CLI integration tests.
# Author: Pierre Grothe
# Date: 2026-05-18

"""FakeBatchProgress: records every method call without rendering.

Used by tests that exercise ``PluginExecutor`` or CLI command wiring
without spinning up a real Rich Live region. Satisfies
:class:`BatchProgressProtocol` structurally.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from types import TracebackType

from rich.console import Console

__all__ = ["FakeBatchProgress"]


@dataclass(slots=True)
class FakeBatchProgress:
    """Recording fake satisfying ``BatchProgressProtocol``.

    Attributes:
        console: Console writing to an in-memory ``StringIO`` so tests
            can assert on captured output.
        recorded_calls: List of ``(method_name, kwargs)`` tuples
            appended in call order. Empty list at construction time.
        _next_task_id: Monotonic id source for ``start_item``.
    """

    console: Console = field(
        default_factory=lambda: Console(file=io.StringIO(), force_terminal=False, width=120)
    )
    recorded_calls: list[tuple[str, dict[str, object]]] = field(
        default_factory=list[tuple[str, dict[str, object]]]
    )
    _next_task_id: int = 0

    def start_batch(self, total: int) -> int:
        """Record the batch start and return task id 0."""
        self.recorded_calls.append(("start_batch", {"total": total}))
        return 0

    def start_item(self, plugin_id: str, family: str) -> int:
        """Record the item start and return a monotonic task id."""
        task_id = self._next_task_id
        self._next_task_id += 1
        self.recorded_calls.append(
            ("start_item", {"plugin_id": plugin_id, "family": family, "task_id": task_id})
        )
        return task_id

    def update_item(self, task_id: int, sn_pct: int) -> None:
        """Record an in-flight percent update."""
        self.recorded_calls.append(("update_item", {"task_id": task_id, "sn_pct": sn_pct}))

    def finish_item(self, task_id: int, duration_s: float, family: str, success: bool) -> None:
        """Record the item completion."""
        self.recorded_calls.append(
            (
                "finish_item",
                {
                    "task_id": task_id,
                    "duration_s": duration_s,
                    "family": family,
                    "success": success,
                },
            )
        )

    def __enter__(self) -> FakeBatchProgress:
        """No-op enter; the fake records calls eagerly."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """No-op exit."""
        return None
