# src/nexus/assessment/gate.py
# GateProtocol -- structural interface for Gate1Readiness, Gate2Validation, HealthScan.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Protocol declaring the contract every Gate implementation satisfies."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from nexus.assessment.context import GateContext
from nexus.assessment.report import GateReport

__all__ = ["GateProtocol"]


@runtime_checkable
class GateProtocol(Protocol):
    """Uniform structural interface for assessment gates.

    Each implementation (Gate1Readiness, Gate2Validation, HealthScan)
    loads its own ruleset slug and delegates rule evaluation to
    `nexus.assessment.engine.evaluate`. The verdict-derivation step
    happens via `GateReport.from_findings`.
    """

    def evaluate(self, ctx: GateContext) -> GateReport:
        """Evaluate the gate against the given context and return a GateReport."""
        ...  # pragma: no cover -- Protocol method body
