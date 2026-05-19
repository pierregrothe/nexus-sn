# src/nexus/assessment/schemas/enums.py
# StrEnum types shared across assessment rule schemas.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Enums for rule severity, evaluation phase, and constraint composition."""

from __future__ import annotations

from enum import StrEnum

__all__ = ["Logic", "Phase", "Severity"]


class Severity(StrEnum):
    """Per-rule severity used when a rule emits a Finding.

    ERROR is always blocking. WARNING is blocking in PRE_APPLY context,
    advisory in POST_APPLY and STANDALONE. INFO never blocks.
    """

    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class Phase(StrEnum):
    """When a rule applies in the assessment lifecycle.

    PRE_APPLY rules evaluate readiness before `nexus apply`. POST_APPLY
    rules verify state after the apply completes. STANDALONE rules run
    in the unflagged `nexus assess` health scan.
    """

    PRE_APPLY = "PRE_APPLY"
    POST_APPLY = "POST_APPLY"
    STANDALONE = "STANDALONE"


class Logic(StrEnum):
    """Boolean composition across a rule's constraints.

    AND_ALL fails if any constraint fails. OR_ANY passes if any
    constraint passes. Flat composition only -- no nested trees.
    """

    AND_ALL = "AND_ALL"
    OR_ANY = "OR_ANY"
