# src/nexus/replatform/diff.py
# Bi-directional replatform checklist diff over two use-case inventories.
# Author: Pierre Grothe
# Date: 2026-06-29

"""Pure diff producing a MigrationChecklist from a source + target inventory.

The analog of ``nexus.plugins.drift.compute_drift``, one altitude up: it matches
workflows on their normalized natural key (never sys_id), rolls each use case up
to DONE / TODO / PARTIAL with a built/total fraction, and lists target-only
workflows as informational EXTRA items. ``--scope-alias`` remaps renamed target
scopes back to the source scope before matching. No I/O.
"""

from nexus.replatform.models import (
    ChecklistItem,
    ChecklistKind,
    ChecklistStatus,
    MigrationChecklist,
    UseCase,
    UseCaseInventory,
    WorkflowRef,
)

__all__ = ["build_checklist"]


def build_checklist(
    source: UseCaseInventory,
    target: UseCaseInventory,
    aliases: tuple[tuple[str, str], ...] = (),
) -> MigrationChecklist:
    """Diff two use-case inventories into a bi-directional migration checklist.

    Args:
        source: Inventory of the OLD instance (what must exist on the target).
        target: Inventory of the NEW (clean) instance (what is already built).
        aliases: ``(old_scope, new_scope)`` pairs. Target workflows whose scope
            equals ``new_scope`` are remapped to ``old_scope`` before matching,
            so a renamed-scope workflow reads DONE rather than TODO + EXTRA.

    Returns:
        A frozen ``MigrationChecklist`` whose items are sorted by
        ``(domain, use_case_key, kind, key)``.
    """
    new_to_old = {new: old for old, new in aliases}
    target_by_key: dict[str, tuple[UseCase, WorkflowRef]] = {}
    for use_case in target.use_cases:
        for workflow in use_case.workflows:
            target_by_key[_remap(workflow, new_to_old)] = (use_case, workflow)

    source_keys: set[str] = set()
    items: list[ChecklistItem] = []
    for use_case in source.use_cases:
        built = 0
        for workflow in use_case.workflows:
            source_keys.add(workflow.key)
            present = workflow.key in target_by_key
            built += 1 if present else 0
            items.append(
                _workflow_item(
                    workflow,
                    use_case,
                    ChecklistStatus.DONE if present else ChecklistStatus.TODO,
                )
            )
        total = len(use_case.workflows)
        items.append(
            ChecklistItem(
                key=use_case.key,
                name=use_case.name,
                domain=use_case.domain,
                use_case_key=use_case.key,
                kind=ChecklistKind.USE_CASE,
                status=_rollup_status(built, total),
                built_count=built,
                total_count=total,
            )
        )

    for effective_key, (use_case, workflow) in target_by_key.items():
        if effective_key not in source_keys:
            items.append(_workflow_item(workflow, use_case, ChecklistStatus.EXTRA))

    items.sort(key=lambda item: (item.domain, item.use_case_key, item.kind.value, item.key))
    coverage = tuple(sorted(set(source.coverage) | set(target.coverage)))
    return MigrationChecklist(
        source_profile=source.profile,
        target_profile=target.profile,
        source_captured_at=source.captured_at,
        target_captured_at=target.captured_at,
        coverage=coverage,
        items=tuple(items),
    )


def _remap(workflow: WorkflowRef, new_to_old: dict[str, str]) -> str:
    """Return the workflow key with a renamed target scope mapped back to source.

    Args:
        workflow: A target-side workflow reference.
        new_to_old: Mapping of renamed (new) scope -> original (old) scope.

    Returns:
        The natural key with its leading scope segment rewritten when the
        workflow's scope was renamed; otherwise the key unchanged.
    """
    old_scope = new_to_old.get(workflow.scope)
    if old_scope is None:
        return workflow.key
    parts = workflow.key.split("|", 2)
    parts[0] = old_scope
    return "|".join(parts)


def _workflow_item(
    workflow: WorkflowRef, use_case: UseCase, status: ChecklistStatus
) -> ChecklistItem:
    """Build a WORKFLOW-kind ChecklistItem for a workflow under a use case."""
    return ChecklistItem(
        key=workflow.key,
        name=workflow.name,
        domain=use_case.domain,
        use_case_key=use_case.key,
        kind=ChecklistKind.WORKFLOW,
        status=status,
    )


def _rollup_status(built: int, total: int) -> ChecklistStatus:
    """Roll a use case up to DONE / TODO / PARTIAL from its built/total counts."""
    if total > 0 and built == total:
        return ChecklistStatus.DONE
    if built == 0:
        return ChecklistStatus.TODO
    return ChecklistStatus.PARTIAL
