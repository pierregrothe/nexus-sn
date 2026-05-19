# src/nexus/assessment/verdict.py
# GateVerdict StrEnum.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Three-valued verdict carried by GateReport.

PASS  -- gate evaluated, no failing rules.
BLOCK -- gate evaluated, at least one failing rule that contributes to block.
ERROR -- gate could not evaluate (capture incomplete, ruleset load failed,
         phase mismatch at the gate boundary).

ERROR is distinct from BLOCK: BLOCK is a known-bad rule outcome; ERROR is
"we could not give you a verdict". CLI exit-code mapping differs (BLOCK
exits 2, ERROR exits 1).
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["GateVerdict"]


class GateVerdict(StrEnum):
    """Top-level gate outcome."""

    PASS = "PASS"
    BLOCK = "BLOCK"
    ERROR = "ERROR"
