# src/nexus/replatform/reporter.py
# Render a MigrationChecklist to the console or a byte-stable markdown file.
# Author: Pierre Grothe
# Date: 2026-06-29

"""Console + markdown rendering for the replatform checklist.

Mirrors nexus.assessment.reporter: a public render function that branches on the
RenderContext profile and reuses existing ui/components primitives, plus a
byte-stable markdown emitter (LF endings). No new UI primitive is introduced.
"""

from pathlib import Path

from rich.console import RenderableType

from nexus.replatform.models import (
    ChecklistItem,
    ChecklistKind,
    ChecklistStatus,
    MigrationChecklist,
)
from nexus.ui.capabilities import RenderProfile
from nexus.ui.components import DataColumn, DataTable, KeyValuePanel, KvRow, Notice, StatusBadge
from nexus.ui.render_context import RenderContext

__all__ = ["EMPTY_SOURCE_NOTICE", "UNNAMED_NOTICE", "render_checklist", "write_markdown"]

EMPTY_SOURCE_NOTICE = (
    "source inventory is empty -- coverage spans the configured table groups "
    "for custom scopes and customer-updated global artifacts; a clean "
    "checklist is not proof that nothing needs migrating"
)

UNNAMED_NOTICE = (
    "{count} unnamed artifact(s) have no stable natural key and cannot be "
    "matched across instances -- they always render as TODO on the source "
    "and EXTRA on the target"
)


def _unnamed_count(checklist: MigrationChecklist) -> int:
    """Count WORKFLOW items whose artifact carries no display name."""
    return sum(
        1 for item in checklist.items if item.kind is ChecklistKind.WORKFLOW and not item.name
    )


def render_checklist(checklist: MigrationChecklist, ctx: RenderContext) -> None:
    """Render a MigrationChecklist to ``ctx.console``.

    Args:
        checklist: The checklist to display.
        ctx: RenderContext carrying the destination console + profile.
    """
    if ctx.profile is RenderProfile.PLAIN:
        _render_plain(checklist, ctx)
        return
    _render_rich(checklist, ctx)


def write_markdown(checklist: MigrationChecklist, path: Path) -> None:
    """Write the checklist as byte-stable GitHub-flavored markdown.

    Args:
        checklist: The checklist to serialize.
        path: Destination file. Always written with LF endings via
            ``write_bytes`` so output is identical across platforms.
    """
    path.write_bytes(_markdown(checklist).encode("utf-8"))


def _source_is_empty(checklist: MigrationChecklist) -> bool:
    """Return True when no source use case contributed to the checklist."""
    return not any(item.kind is ChecklistKind.USE_CASE for item in checklist.items)


def _render_plain(checklist: MigrationChecklist, ctx: RenderContext) -> None:
    """One ASCII line per item for the PLAIN profile."""
    header = (
        f"replatform {checklist.source_profile} -> {checklist.target_profile} "
        f"items={len(checklist.items)}"
    )
    ctx.console.print(header, highlight=False)
    if _source_is_empty(checklist):
        ctx.console.print(EMPTY_SOURCE_NOTICE, highlight=False)
    unnamed = _unnamed_count(checklist)
    if unnamed:
        ctx.console.print(UNNAMED_NOTICE.format(count=unnamed), highlight=False)
    for item in checklist.items:
        ctx.console.print(_plain_line(item), highlight=False)


def _render_rich(checklist: MigrationChecklist, ctx: RenderContext) -> None:
    """RICH / BASIC / LEGACY rendering using ui/components/."""
    if _source_is_empty(checklist):
        ctx.console.print(Notice.warn(EMPTY_SOURCE_NOTICE))
    else:
        header = f"replatform checklist: {checklist.source_profile} -> {checklist.target_profile}"
        ctx.console.print(Notice.info(header))
    unnamed = _unnamed_count(checklist)
    if unnamed:
        ctx.console.print(Notice.warn(UNNAMED_NOTICE.format(count=unnamed)))
    ctx.console.print(_summary_panel(checklist))
    if checklist.items:
        ctx.console.print(_items_table(checklist))


def _summary_panel(checklist: MigrationChecklist) -> KeyValuePanel:
    """Build the KeyValuePanel summarizing use-case status counts."""
    use_cases = [i for i in checklist.items if i.kind is ChecklistKind.USE_CASE]
    done = sum(1 for i in use_cases if i.status is ChecklistStatus.DONE)
    partial = sum(1 for i in use_cases if i.status is ChecklistStatus.PARTIAL)
    todo = sum(1 for i in use_cases if i.status is ChecklistStatus.TODO)
    extra = sum(1 for i in checklist.items if i.status is ChecklistStatus.EXTRA)
    rows = [
        KvRow(label="use cases", value=str(len(use_cases))),
        KvRow(label="done", value=str(done)),
        KvRow(label="partial", value=str(partial)),
        KvRow(label="todo", value=str(todo)),
        KvRow(label="extra workflows", value=str(extra)),
    ]
    return KeyValuePanel(title="Replatform Checklist", rows=rows)


def _items_table(checklist: MigrationChecklist) -> DataTable:
    """Build a DataTable of checklist items with per-row status badges."""
    rows: list[list[RenderableType]] = [
        [item.domain, item.use_case_key, _item_label(item), _status_badge(item.status)]
        for item in checklist.items
    ]
    columns = [
        DataColumn(header="domain", min_width=10, no_wrap=True),
        DataColumn(header="use case", min_width=10, no_wrap=True),
        DataColumn(header="item", min_width=20, no_wrap=False),
        DataColumn(header="status", min_width=8, no_wrap=True),
    ]
    return DataTable(title="Items", columns=columns, rows=rows)


def _plain_line(item: ChecklistItem) -> str:
    """Render one checklist item as a single ASCII line."""
    fraction = _fraction(item)
    suffix = f" {fraction}" if fraction else ""
    return f"[{item.status.value}] {item.domain} / {item.use_case_key} / {item.name}{suffix}"


def _item_label(item: ChecklistItem) -> str:
    """Label a checklist item for the table: use cases carry the built/total fraction."""
    if item.kind is ChecklistKind.USE_CASE:
        return f"{item.name} ({_fraction(item)})"
    return f"  {item.name}"


def _fraction(item: ChecklistItem) -> str:
    """Return ``built/total`` for use-case items, else an empty string."""
    if item.built_count is None or item.total_count is None:
        return ""
    return f"{item.built_count}/{item.total_count}"


def _status_badge(status: ChecklistStatus) -> StatusBadge:
    """Map a checklist status onto one of the three StatusBadge variants."""
    match status:
        case ChecklistStatus.DONE:
            return StatusBadge.ok(status.value)
        case ChecklistStatus.PARTIAL | ChecklistStatus.EXTRA:
            return StatusBadge.warn(status.value)
        case ChecklistStatus.TODO:
            return StatusBadge.error(status.value)
        case _:  # pragma: no cover -- exhaustive over ChecklistStatus
            raise AssertionError(f"unreachable status: {status!r}")


def _markdown(checklist: MigrationChecklist) -> str:
    """Render the checklist as a markdown string with GitHub task-list checkboxes."""
    coverage = ", ".join(checklist.coverage) or "(none)"
    lines: list[str] = [
        f"# Replatform Checklist: {checklist.source_profile} -> {checklist.target_profile}",
        "",
        f"Coverage: {coverage}",
        "",
    ]
    if _source_is_empty(checklist):
        lines.extend([f"> WARNING: {EMPTY_SOURCE_NOTICE}", ""])
    unnamed = _unnamed_count(checklist)
    if unnamed:
        lines.extend([f"> WARNING: {UNNAMED_NOTICE.format(count=unnamed)}", ""])
    current_domain: str | None = None
    for item in checklist.items:
        if item.domain != current_domain:
            current_domain = item.domain
            lines.extend([f"## {item.domain}", ""])
        lines.append(_markdown_line(item))
    lines.append("")
    return "\n".join(lines)


def _markdown_line(item: ChecklistItem) -> str:
    """Render one checklist item as a markdown task-list line."""
    checkbox = "x" if item.status is ChecklistStatus.DONE else " "
    if item.kind is ChecklistKind.USE_CASE:
        return f"- [{checkbox}] {item.name} ({item.status.value} {_fraction(item)})"
    return f"  - [{checkbox}] {item.name} ({item.status.value})"
