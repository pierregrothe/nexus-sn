# src/nexus/assessment/__init__.py
# Assessment package: rules, gates, reporter, scanner.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Assessment and health scanning package.

Public re-exports for the most commonly used types. Detail lives in
submodules:
- schemas: Pydantic rule models
- loader: YAML ruleset loader
- errors: AssessmentError hierarchy
"""

from __future__ import annotations

from nexus.assessment.context import ApplyResult, GateContext
from nexus.assessment.dsl import ConstraintResult
from nexus.assessment.engine import evaluate
from nexus.assessment.errors import AssessmentError, RulesetLoadError
from nexus.assessment.findings import Finding
from nexus.assessment.gate import GateProtocol
from nexus.assessment.gates import Gate1Readiness, Gate2Validation, HealthScan
from nexus.assessment.loader import load_ruleset
from nexus.assessment.report import GateReport, GateSummary
from nexus.assessment.schemas.constraints import (
    CountGteConstraint,
    CountLteConstraint,
    FieldEqualsConstraint,
    FieldFilter,
    FieldFilterPair,
    FieldInConstraint,
    RecordExistsConstraint,
    RuleConstraint,
)
from nexus.assessment.schemas.enums import Logic, Phase, Severity
from nexus.assessment.schemas.rule import AssessmentRule
from nexus.assessment.schemas.ruleset import Ruleset
from nexus.assessment.schemas.scope import CrossTableScope, RuleScope, TableScope
from nexus.assessment.verdict import GateVerdict

__all__ = [
    "ApplyResult",
    "AssessmentError",
    "AssessmentRule",
    "ConstraintResult",
    "CountGteConstraint",
    "CountLteConstraint",
    "CrossTableScope",
    "FieldEqualsConstraint",
    "FieldFilter",
    "FieldFilterPair",
    "FieldInConstraint",
    "Finding",
    "Gate1Readiness",
    "Gate2Validation",
    "GateContext",
    "GateProtocol",
    "GateReport",
    "GateSummary",
    "GateVerdict",
    "HealthScan",
    "Logic",
    "Phase",
    "RecordExistsConstraint",
    "RuleConstraint",
    "RuleScope",
    "Ruleset",
    "RulesetLoadError",
    "Severity",
    "TableScope",
    "evaluate",
    "load_ruleset",
]
