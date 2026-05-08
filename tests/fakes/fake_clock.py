# tests/fakes/fake_clock.py
# Deterministic clock for TTL tests -- no time.monotonic, no mocks.
# Author: Pierre Grothe
# Date: 2026-05-08
"""FakeClock: a controllable monotonic clock for tests."""

from dataclasses import dataclass

__all__ = ["FakeClock"]


@dataclass(slots=True)
class FakeClock:
    """A deterministic clock for tests.

    Use ``now()`` where production code calls ``time.monotonic()``.
    Use ``advance(seconds)`` to move time forward.

    Attributes:
        current: The current time (float seconds, monotonic-style).
    """

    current: float = 0.0

    def now(self) -> float:
        """Return the current monotonic-style time."""
        return self.current

    def advance(self, seconds: float) -> None:
        """Move the clock forward by ``seconds``."""
        self.current += seconds
