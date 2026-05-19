# tests/fakes/gates.py
# Recording GateProtocol implementation for assessment tests.
# Author: Pierre Grothe
# Date: 2026-05-19

"""FakeGate: a structural GateProtocol impl that records calls."""

from __future__ import annotations

from dataclasses import dataclass, field

from nexus.assessment.context import GateContext
from nexus.assessment.report import GateReport

__all__ = ["FakeGate"]


@dataclass(slots=True)
class FakeGate:
    """Recording GateProtocol implementation.

    Stores every GateContext passed to .evaluate in `evaluated_ctxs` and
    returns a pre-configured `report`. Used by Story 06 CLI tests.

    Attributes:
        report: GateReport returned by every .evaluate call.
        evaluated_ctxs: Tuple of every GateContext received.
    """

    report: GateReport
    evaluated_ctxs: tuple[GateContext, ...] = field(default_factory=tuple)

    def evaluate(self, ctx: GateContext) -> GateReport:
        """Record `ctx` and return `self.report`."""
        self.evaluated_ctxs = (*self.evaluated_ctxs, ctx)
        return self.report
