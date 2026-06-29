# src/nexus/replatform/__init__.py
# Replatform analysis layer: cross-instance use-case inventory + migration checklist.
# Author: Pierre Grothe
# Date: 2026-06-29

"""Replatform analysis layer for ServiceNow replatforming.

Deterministic use-case classification and a bi-directional migration checklist.
Advisory only: this layer consumes captured data and never mutates an instance.
"""

from nexus.replatform.classifier import classify
from nexus.replatform.diff import build_checklist
from nexus.replatform.models import (
    ChecklistItem,
    ChecklistKind,
    ChecklistStatus,
    MigrationChecklist,
    UseCase,
    UseCaseInventory,
    WorkflowRef,
)

__all__ = [
    "ChecklistItem",
    "ChecklistKind",
    "ChecklistStatus",
    "MigrationChecklist",
    "UseCase",
    "UseCaseInventory",
    "WorkflowRef",
    "build_checklist",
    "classify",
]
