# src/nexus/replatform/models.py
# Frozen domain models for the replatform analysis layer.
# Author: Pierre Grothe
# Date: 2026-06-29

"""Pydantic models for nexus.replatform.

Defines WorkflowRef, UseCase, UseCaseInventory, ChecklistItem, and
MigrationChecklist plus the ChecklistStatus / ChecklistKind enums. All models
are frozen+strict+extra=forbid; the layer is advisory and never mutates an
instance.
"""

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from nexus.config.types import UtcDatetime

__all__ = [
    "ChecklistItem",
    "ChecklistKind",
    "ChecklistStatus",
    "MigrationChecklist",
    "UseCase",
    "UseCaseInventory",
    "WorkflowRef",
]

_FROZEN = ConfigDict(frozen=True, strict=True, extra="forbid")


class ChecklistStatus(StrEnum):
    """Status of a checklist item in a replatform migration."""

    TODO = "TODO"
    DONE = "DONE"
    PARTIAL = "PARTIAL"
    EXTRA = "EXTRA"


class ChecklistKind(StrEnum):
    """Whether a checklist item is a use-case roll-up or a single workflow."""

    USE_CASE = "USE_CASE"
    WORKFLOW = "WORKFLOW"


class WorkflowRef(BaseModel):
    """A captured workflow artifact identified by a normalized natural key.

    Attributes:
        key: Normalized natural key ``{scope}|{type}|{casefold(name)}``.
        name: Display name of the workflow.
        type: Source table (e.g. ``sys_hub_flow``, ``ai_skill``).
        scope: Technical scope key (e.g. ``x_acme_app``).
    """

    model_config = _FROZEN

    key: str
    name: str
    type: str
    scope: str


class UseCase(BaseModel):
    """A bucket of workflows discovered on one instance, grouped by domain.

    Attributes:
        key: Stable use-case key (the scope or family identifier).
        name: Display name.
        domain: The catalog product name for known OOB scopes, the
            application display name for other scopes, a ``--domain-map``
            override when supplied, or ``Uncategorized`` only for
            unresolvable scopes.
        workflows: Workflows belonging to this use case.
        evidence: Scopes/plugins that justify this use case.
    """

    model_config = _FROZEN

    key: str
    name: str
    domain: str
    workflows: tuple[WorkflowRef, ...]
    evidence: tuple[str, ...] = ()


class UseCaseInventory(BaseModel):
    """The classified use-case inventory for a single instance.

    Attributes:
        profile: Instance profile the inventory was built from.
        captured_at: When the underlying capture was taken (UTC).
        coverage: Table groups that fed this inventory.
        use_cases: The classified use cases, in classifier order.
        skipped_tables: Tables absent on this instance (HTTP 400/404 during the
            live listing), sorted. Empty when every table was reachable.
    """

    model_config = _FROZEN

    profile: str
    captured_at: UtcDatetime
    coverage: tuple[str, ...]
    use_cases: tuple[UseCase, ...]
    skipped_tables: tuple[str, ...] = ()


class ChecklistItem(BaseModel):
    """One row of a migration checklist -- a use-case roll-up or a workflow.

    Attributes:
        key: Item key (use-case key for USE_CASE; workflow key for WORKFLOW).
        name: Display name.
        domain: Product family / domain (sort-key segment).
        use_case_key: Parent use-case key (equals ``key`` for USE_CASE items).
        kind: USE_CASE roll-up or WORKFLOW leaf.
        status: TODO | DONE | PARTIAL | EXTRA.
        built_count: Workflows built on target (USE_CASE only; None for WORKFLOW).
        total_count: Workflows on source (USE_CASE only; None for WORKFLOW).
        evidence: Optional supporting scope/plugin references.
    """

    model_config = _FROZEN

    key: str
    name: str
    domain: str
    use_case_key: str
    kind: ChecklistKind
    status: ChecklistStatus
    built_count: int | None = None
    total_count: int | None = None
    evidence: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _check_counts(self) -> Self:
        """Enforce the per-kind count invariant.

        Returns:
            Self when the counts are coherent for the item kind.

        Raises:
            ValueError: When a WORKFLOW item carries counts, or a USE_CASE item
                is missing counts, has a negative count, or has
                ``built_count > total_count``.
        """
        if self.kind is ChecklistKind.WORKFLOW:
            if self.built_count is not None or self.total_count is not None:
                raise ValueError("WORKFLOW items must not carry built/total counts")
            return self
        if self.built_count is None or self.total_count is None:
            raise ValueError("USE_CASE items must carry built_count and total_count")
        if self.built_count < 0 or self.total_count < 0:
            raise ValueError("counts must be non-negative")
        if self.built_count > self.total_count:
            raise ValueError("built_count must not exceed total_count")
        return self


class MigrationChecklist(BaseModel):
    """The bi-directional replatform checklist comparing two instances.

    Attributes:
        source_profile: Profile of the OLD instance.
        target_profile: Profile of the NEW (clean) instance.
        source_captured_at: When the source inventory was captured (UTC).
        target_captured_at: When the target inventory was captured (UTC).
        coverage: Sorted union of source + target coverage.
        items: Checklist items in stable ``(domain, use_case_key, kind, key)`` order.
    """

    model_config = _FROZEN

    source_profile: str
    target_profile: str
    source_captured_at: UtcDatetime
    target_captured_at: UtcDatetime
    coverage: tuple[str, ...]
    items: tuple[ChecklistItem, ...]
