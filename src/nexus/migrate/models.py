# src/nexus/migrate/models.py
# Frozen plan-file models for the selective-migration planner.
# Author: Pierre Grothe
# Date: 2026-07-02

"""Pydantic models for nexus.migrate.

Defines Selection, MigrationPlan, Wave, PlanItem, IntegrityFinding, Waiver,
and Acknowledgment plus the PlanLane / FindingKind enums, and the
byte-stable YAML emit/load pair that makes the plan file the auditable
artifact of record (ADR-026 Decision 2). All models are
frozen+strict+extra=forbid; this module holds no closure, waiver-approval,
or CLI logic -- models and YAML emit/load only.
"""

from enum import StrEnum
from typing import Annotated, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from nexus.config.types import UtcDatetime

__all__ = [
    "Acknowledgment",
    "FindingKind",
    "IntegrityFinding",
    "MigrationPlan",
    "PlanItem",
    "PlanLane",
    "Selection",
    "SelectionItem",
    "Waiver",
    "Wave",
    "emit_plan_yaml",
    "load_plan_yaml",
]

_FROZEN = ConfigDict(frozen=True, strict=True, extra="forbid")


class PlanLane(StrEnum):
    """Provisional, schema-versioned routing hint for the runbook (ADR-026 Decision 5).

    Binding lane/transport architecture is deferred to ADR-027; a spike
    outcome may relabel lanes without invalidating plan files.
    """

    APP_REPO = "APP_REPO"
    UPDATE_SET = "UPDATE_SET"
    DATA = "DATA"
    MANUAL = "MANUAL"


class FindingKind(StrEnum):
    """Kind of integrity finding raised while closing a selection.

    Open to extension by later stories (e.g. Story 04's access-posture-drift
    rule); this module fixes only the members required by this story.
    """

    STRANDED_DEPENDENCY = "STRANDED_DEPENDENCY"
    DATA_PREREQUISITE = "DATA_PREREQUISITE"
    CYCLE = "CYCLE"


class SelectionItem(BaseModel):
    """One curated row in a Selection.

    Attributes:
        key: Natural key, e.g. ``{scope}|{table}|{name}``.
        disposition: Whether the item is included, excluded, or still undecided.
        annotation: Free-text consultant note explaining the disposition.
        annotated_by: Author of the annotation.
    """

    model_config = _FROZEN

    key: str
    disposition: Literal["include", "exclude", "undecided"]
    annotation: str = ""
    annotated_by: str = ""


class Selection(BaseModel):
    """A curated selection of source-instance items awaiting closure.

    Attributes:
        source_profile: Instance profile the selection was captured from.
        target_profile: Instance profile the selection will be migrated to.
        source_captured_at: When the source snapshot was captured (UTC).
        items: The curated items, in curation order.
    """

    model_config = _FROZEN

    source_profile: str
    target_profile: str
    source_captured_at: UtcDatetime
    items: tuple[SelectionItem, ...]


class PlanItem(BaseModel):
    """One item placed into a migration wave.

    Attributes:
        key: Natural key matching the originating SelectionItem or an item
            added by dependency closure.
        lane: Provisional routing hint for the runbook.
        added_by_closure: True when this item was pulled in by dependency
            closure rather than explicit curation.
        wave_index: Index of the wave this item executes in.
    """

    model_config = _FROZEN

    key: str
    lane: PlanLane
    added_by_closure: bool = False
    wave_index: Annotated[int, Field(ge=0)]


class Wave(BaseModel):
    """An ordered batch of PlanItems executed together.

    Attributes:
        index: Zero-based execution order of this wave.
        items: Items placed into this wave.
    """

    model_config = _FROZEN

    index: Annotated[int, Field(ge=0)]
    items: tuple[PlanItem, ...]


class Waiver(BaseModel):
    """An attributed waiver of a blocking integrity finding (ADR-026 Decision 3).

    Attributes:
        author: The consultant who requested the waiver.
        approver: The consultant who approved the waiver; must differ from
            ``author`` (segregation of duties).
        reason: Free-text justification.
        date: When the waiver was approved (UTC).
    """

    model_config = _FROZEN

    author: str
    approver: str
    reason: str
    date: UtcDatetime

    @model_validator(mode="after")
    def _check_segregation(self) -> Self:
        """Enforce author/approver segregation of duties.

        Returns:
            Self when author and approver differ.

        Raises:
            ValueError: When a waiver is self-approved.
        """
        if self.author == self.approver:
            raise ValueError("waiver approver must differ from author (segregation of duties)")
        return self


class Acknowledgment(BaseModel):
    """An attributed acknowledgment of a non-blocking integrity finding.

    Attributes:
        author: The consultant who acknowledged the finding.
        reason: Free-text justification.
        date: When the finding was acknowledged (UTC).
    """

    model_config = _FROZEN

    author: str
    reason: str
    date: UtcDatetime


class IntegrityFinding(BaseModel):
    """A dependency-closure finding attached to a MigrationPlan.

    Attributes:
        kind: The kind of finding.
        subject_key: Natural key of the item the finding concerns.
        detail: Free-text description of the finding.
        waiver: Waiver clearing a blocking finding, if any.
        acknowledgment: Acknowledgment of a non-blocking finding, if any.
    """

    model_config = _FROZEN

    kind: FindingKind
    subject_key: str
    detail: str
    waiver: Waiver | None = None
    acknowledgment: Acknowledgment | None = None


class MigrationPlan(BaseModel):
    """The schema-versioned plan file -- the auditable artifact of record.

    Attributes:
        schema_version: Plan file schema version.
        source_profile: Instance profile the plan migrates FROM.
        target_profile: Instance profile the plan migrates TO.
        source_captured_at: When the source snapshot was captured (UTC).
        target_captured_at: When the target snapshot was captured (UTC).
        waves: Ordered execution waves.
        findings: Dependency-closure findings, waived or acknowledged as needed.
        approved_by: Approver of the plan; empty when not yet approved.
        approved_at: When the plan was approved (UTC), or None.
        target_chain: Reserved promotion-chain field (PRD-005 Open
            Questions); v1 never populates more than one entry.
    """

    model_config = _FROZEN

    schema_version: str
    source_profile: str
    target_profile: str
    source_captured_at: UtcDatetime
    target_captured_at: UtcDatetime
    waves: tuple[Wave, ...]
    findings: tuple[IntegrityFinding, ...]
    approved_by: str = ""
    approved_at: UtcDatetime | None = None
    target_chain: tuple[str, ...] = ()


def emit_plan_yaml(plan: MigrationPlan) -> str:
    """Serialize a MigrationPlan to byte-stable YAML text.

    Args:
        plan: The plan to serialize.

    Returns:
        YAML text with LF-only line endings, key order matching model field
        declaration order (``sort_keys=False``).
    """
    data = plan.model_dump(mode="json")
    text: str = yaml.safe_dump(data, sort_keys=False, default_flow_style=False)
    return text.replace("\r\n", "\n")


def load_plan_yaml(text: str) -> MigrationPlan:
    """Deserialize a MigrationPlan from YAML text emitted by emit_plan_yaml.

    Pydantic strict mode rejects the plain ``str`` and ``list`` containers
    that ``yaml.safe_load`` produces for StrEnum fields (PlanLane,
    FindingKind) and tuple fields -- so this call passes ``strict=False`` to
    ``model_validate`` itself rather than relaxing model_config. The text is
    our own emitted format, so per-call laxity is acceptable, and the
    byte-stable round-trip test guards fidelity.

    Args:
        text: YAML text, as produced by emit_plan_yaml.

    Returns:
        The reconstructed MigrationPlan.

    Raises:
        ValueError: When text is not valid YAML or is not a mapping.
    """
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"plan YAML is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("plan YAML must be a mapping")
    return MigrationPlan.model_validate(data, strict=False)
