# src/nexus/cli/renderables.py
# Pure renderable / panel builders extracted from cli.py for ADR-023 sizing.
# Author: Pierre Grothe
# Date: 2026-05-16
"""Pure Rich-renderable builders used by the CLI commands.

Extracted from ``cli.py`` to keep that module marching toward the
800-line cap defined by ADR-023. Every helper here is a pure function:
it returns a Rich renderable (Notice / DataTable / KeyValuePanel /
StatusBadge) and never prints to a console -- the calling command in
``cli.py`` owns the actual ``console.print()``.

Keeping these isolated means new view code that just wants "what does
a diff row look like?" can import from this module without dragging in
Typer, OAuth, or async I/O dependencies.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from rich.console import RenderableType
from rich.text import Text

from nexus.capture.models import ScopeEntry
from nexus.plugins.dependencies import DependencyEntry
from nexus.plugins.diff import PluginDiffEntry
from nexus.plugins.drift import PluginDriftEntry
from nexus.plugins.executor_models import OperationResult
from nexus.plugins.models import AdvisoryFinding, PluginInfo, Severity
from nexus.ui import (
    DataColumn,
    DataTable,
    KeyValuePanel,
    KvRow,
    Notice,
    StatusBadge,
)

__all__ = [
    "ADVISORY_COLUMNS",
    "SEVERITY_ORDER",
    "advisory_detail_panel",
    "build_advisory_rows",
    "build_advisory_rows_short",
    "build_advisory_summary",
    "cascade_actionable",
    "cascade_scope",
    "cascade_summary_notice",
    "dependencies_panel",
    "diff_detail_panel",
    "diff_row",
    "diff_status_badge",
    "drift_detail_panel",
    "drift_row",
    "drift_status_badge",
    "plugin_detail_panel",
    "result_panel",
    "scope_detail_panel",
    "severity_at_or_above",
    "status_breakdown",
]


# ---------------------------------------------------------------------------
# Cascade (dependency pre-flight) helpers
# ---------------------------------------------------------------------------


def cascade_actionable(deps: tuple[DependencyEntry, ...]) -> tuple[DependencyEntry, ...]:
    """Filter a raw cascade response to the rows the user can act on.

    Drops rows SN flags as ``hide_on_ui`` (internal helpers) and rows whose
    ``id`` field is empty (degenerate placeholders SN sometimes returns when
    the target itself has nothing to do).
    """
    return tuple(d for d in deps if d.id and not d.hide_on_ui)


def cascade_scope(entry: DependencyEntry) -> str:
    """Return the plugin scope id for a cascade entry.

    SN's ``orig_string`` field is ``"scope:version"``. We split on ``":"`` to
    recover the scope so the stage-tracking heuristic can match against the
    label SN emits during progress polling (which uses scopes, not display
    names).
    """
    if entry.orig_string and ":" in entry.orig_string:
        return entry.orig_string.split(":", 1)[0]
    return entry.id


def cascade_summary_notice(actionable: tuple[DependencyEntry, ...], plugin_id: str) -> Notice:
    """Build a one-line summary of the cascade to print before the confirm prompt.

    Lets the user see at a glance how many additional plugins SN will touch
    and which ones, before they answer the y/N prompt.
    """
    scopes = [cascade_scope(d) for d in actionable]
    listing = ", ".join(scopes)
    return Notice.info(
        f"Cascade for {plugin_id}: SN will also touch {len(scopes)} plugin(s): {listing}"
    )


def dependencies_panel(deps: tuple[DependencyEntry, ...], plugin_id: str) -> RenderableType:
    """Render an SN dependency cascade as a DataTable.

    Filters internal / placeholder rows so the panel only shows entries the
    user can act on. Surfaces the two validation signals that SN exposes
    (License OK, Install allowed) alongside Status / Active / Min Version
    so the user can see at a glance whether the cascade is ready to ship.

    When SN returns nothing actionable (the target plugin's prerequisites
    are already satisfied), returns a single ``Notice.info`` instead of an
    empty / misleading table.

    Args:
        deps: Dependency entries from fetch_dependencies.
        plugin_id: The target plugin id (shown in title).

    Returns:
        Either a :class:`DataTable` of actionable cascade rows or a
        :class:`Notice` when there is nothing to display.
    """
    actionable = cascade_actionable(deps)
    if not actionable:
        return Notice.info(
            f"No prerequisite plugins need to be installed or upgraded for {plugin_id}."
        )
    rows: list[list[RenderableType]] = []
    for d in actionable:
        license_cell = StatusBadge.ok("yes") if d.has_license else StatusBadge.warn("no")
        allowed_cell = StatusBadge.ok("yes") if d.is_allowed_install else StatusBadge.error("no")
        rows.append(
            [
                d.id,
                d.status or "-",
                "yes" if d.active else "no",
                d.min_version or "-",
                license_cell,
                allowed_cell,
            ]
        )
    return DataTable(
        title=f"Dependency cascade for {plugin_id}",
        columns=[
            DataColumn(header="Plugin", width=36),
            DataColumn(header="Status", width=22),
            DataColumn(header="Active", width=7),
            DataColumn(header="Min Version", width=14),
            DataColumn(header="License", width=8),
            DataColumn(header="Install OK", width=11),
        ],
        rows=rows,
    )


# ---------------------------------------------------------------------------
# Result / status renderables
# ---------------------------------------------------------------------------


def result_panel(result: OperationResult) -> KeyValuePanel:
    """Render an OperationResult as a KeyValuePanel.

    Args:
        result: The OperationResult returned by PluginExecutor.

    Returns:
        KeyValuePanel suitable for console.print().
    """
    status_text = "success" if result.success else "failed"
    return KeyValuePanel(
        title=f"{result.action} {result.plugin_id}",
        rows=[
            KvRow(label="Status", value=status_text),
            KvRow(label="Tracker", value=result.tracker_id or "-"),
            KvRow(label="Duration", value=f"{result.duration_s:.1f}s"),
            KvRow(label="Update set", value=result.update_set or "-"),
            KvRow(label="Rollback version", value=result.rollback_version or "-"),
            KvRow(label="Message", value=result.message or "-"),
        ],
    )


def diff_status_badge(status: str) -> StatusBadge:
    """Return a StatusBadge for a PluginDiffEntry.status value.

    Args:
        status: One of ``only_in_a``, ``only_in_b``, ``version_mismatch``,
            or ``state_mismatch``.

    Returns:
        StatusBadge styled per the status category.
    """
    if status == "version_mismatch":
        return StatusBadge.error(status)
    if status == "state_mismatch":
        return StatusBadge.ok(status)
    return StatusBadge.warn(status)


def drift_status_badge(status: str) -> StatusBadge:
    """Return a StatusBadge for a PluginDriftEntry.status value.

    Args:
        status: One of ``added``, ``removed``, ``version_changed``,
            or ``state_changed``.

    Returns:
        StatusBadge styled per the status category.
    """
    if status == "added":
        return StatusBadge.ok(status)
    return StatusBadge.warn(status)


def status_breakdown(statuses: Iterable[str], label: str) -> str:
    """Format a count-by-status summary line for trailing Notice rendering.

    Args:
        statuses: Iterable of status strings (one per entry).
        label: Singular noun for the entry kind (e.g. ``"difference"``).

    Returns:
        ``"N <label>(s): k1 status1, k2 status2, ..."``, omitting zero counts.
    """
    counts: Counter[str] = Counter(statuses)
    total = sum(counts.values())
    breakdown = ", ".join(f"{n} {k}" for k, n in counts.items() if n)
    return f"{total} {label}(s): {breakdown}"


# ---------------------------------------------------------------------------
# Diff / drift row + detail panels
# ---------------------------------------------------------------------------


def diff_row(entry: PluginDiffEntry) -> tuple[RenderableType, ...]:
    """Build the table-row tuple for one cross-instance diff entry."""
    return (
        entry.plugin_id,
        entry.name,
        entry.product_family,
        diff_status_badge(entry.status),
        entry.a_version or "-",
        entry.b_version or "-",
        entry.a_state or "-",
        entry.b_state or "-",
    )


def drift_row(entry: PluginDriftEntry) -> tuple[RenderableType, ...]:
    """Build the table-row tuple for one drift entry."""
    return (
        entry.plugin_id,
        entry.name,
        entry.product_family,
        drift_status_badge(entry.status),
        entry.baseline_version or "-",
        entry.current_version or "-",
        entry.baseline_state or "-",
        entry.current_state or "-",
    )


def diff_detail_panel(entry: PluginDiffEntry, profile_a: str, profile_b: str) -> KeyValuePanel:
    """Build a KeyValuePanel describing one cross-instance diff entry."""
    rows: list[KvRow] = [
        KvRow(label="Plugin ID", value=entry.plugin_id),
        KvRow(label="Name", value=entry.name),
        KvRow(label="Product", value=entry.product_family),
        KvRow(label="Status", value=diff_status_badge(entry.status)),
        KvRow(label=f"{profile_a} version", value=entry.a_version or "-"),
        KvRow(label=f"{profile_b} version", value=entry.b_version or "-"),
        KvRow(label=f"{profile_a} state", value=entry.a_state or "-"),
        KvRow(label=f"{profile_b} state", value=entry.b_state or "-"),
    ]
    return KeyValuePanel(title=entry.name, rows=rows)


def advisory_detail_panel(finding: AdvisoryFinding) -> KeyValuePanel:
    """Build a KeyValuePanel describing one advisory finding."""
    rows: list[KvRow] = [
        KvRow(label="Plugin ID", value=finding.plugin_id),
        KvRow(label="Plugin name", value=finding.plugin_name),
        KvRow(label="Version", value=finding.plugin_version),
        KvRow(label="Type", value=finding.advisory_type.value),
        KvRow(label="Severity", value=finding.severity.value),
        KvRow(label="Details", value=finding.details),
        KvRow(label="Summary", value=finding.summary or "-"),
    ]
    return KeyValuePanel(title=f"{finding.advisory_type.value}: {finding.plugin_id}", rows=rows)


def drift_detail_panel(entry: PluginDriftEntry) -> KeyValuePanel:
    """Build a KeyValuePanel describing one drift entry vs the baseline."""
    rows: list[KvRow] = [
        KvRow(label="Plugin ID", value=entry.plugin_id),
        KvRow(label="Name", value=entry.name),
        KvRow(label="Product", value=entry.product_family),
        KvRow(label="Status", value=drift_status_badge(entry.status)),
        KvRow(label="Baseline version", value=entry.baseline_version or "-"),
        KvRow(label="Current version", value=entry.current_version or "-"),
        KvRow(label="Baseline state", value=entry.baseline_state or "-"),
        KvRow(label="Current state", value=entry.current_state or "-"),
    ]
    return KeyValuePanel(title=entry.name, rows=rows)


def scope_detail_panel(scope: ScopeEntry) -> KeyValuePanel:
    """Build a KeyValuePanel describing one custom scope and its table counts."""
    rows: list[KvRow] = [
        KvRow(label="Scope key", value=scope.scope),
        KvRow(label="Name", value=scope.name),
        KvRow(label="Version", value=scope.version or "-"),
        KvRow(label="Vendor", value=scope.vendor or "-"),
        KvRow(label="Sys ID", value=scope.sys_id or "-"),
    ]
    total = sum(scope.table_counts.values())
    rows.append(KvRow(label="Total records", value=f"{total:,}"))
    for table_name, count in sorted(scope.table_counts.items()):
        rows.append(KvRow(label=table_name, value=f"{count:,}"))
    return KeyValuePanel(title=scope.scope, rows=rows)


def plugin_detail_panel(plugin: PluginInfo) -> KeyValuePanel:
    """Build a KeyValuePanel showing one plugin's full details.

    Used as the modal-popup detail in the framed viewer when the user
    presses Enter on a row.

    Args:
        plugin: The plugin to describe.

    Returns:
        A :class:`KeyValuePanel` with version, state, source, dependencies, etc.
    """
    rows: list[KvRow] = [
        KvRow(label="Plugin ID", value=plugin.plugin_id),
        KvRow(label="Name", value=plugin.name),
        KvRow(label="Version", value=plugin.version),
        KvRow(label="Latest", value=plugin.latest_version or "-"),
        KvRow(
            label="State",
            value=(
                StatusBadge.ok(plugin.state)
                if plugin.state == "active"
                else StatusBadge.warn(plugin.state)
            ),
        ),
        KvRow(label="Source", value=plugin.source),
        KvRow(label="Product", value=plugin.product_family),
        KvRow(label="Vendor", value=plugin.vendor or "-"),
        KvRow(
            label="Dependencies",
            value=", ".join(plugin.depends_on) if plugin.depends_on else "-",
        ),
    ]
    if plugin.record_counts is not None:
        total = sum(c.count for c in plugin.record_counts)
        rows.append(KvRow(label="Records", value=f"{total:,}"))
    return KeyValuePanel(title=plugin.name, rows=rows)


# ---------------------------------------------------------------------------
# Advisory rendering
# ---------------------------------------------------------------------------


SEVERITY_ORDER: tuple[Severity, ...] = (
    Severity.CRITICAL,
    Severity.HIGH,
    Severity.MEDIUM,
    Severity.LOW,
)


def severity_at_or_above(floor: Severity) -> set[Severity]:
    """Return severities at or above ``floor`` in the canonical ordering.

    Args:
        floor: Lower bound (inclusive).

    Returns:
        Set of severities at or above ``floor`` (critical > high > medium > low).
    """
    idx = SEVERITY_ORDER.index(floor)
    return set(SEVERITY_ORDER[: idx + 1])


ADVISORY_COLUMNS: tuple[DataColumn, ...] = (
    DataColumn(header="Plugin ID", width=22),
    DataColumn(header="Type", width=8),
    DataColumn(header="Severity", width=9),
    DataColumn(header="Details", width=22),
    DataColumn(header="Summary", width=20),
)


def build_advisory_rows_short(
    findings: tuple[AdvisoryFinding, ...],
) -> tuple[tuple[RenderableType, ...], ...]:
    """Render findings using only the five short columns (drops name+version)."""
    return tuple(
        (
            f.plugin_id,
            f.advisory_type.value,
            f.severity.value,
            Text(f.details),
            Text(getattr(f, "summary", "") or ""),
        )
        for f in findings
    )


def build_advisory_rows(
    findings: tuple[AdvisoryFinding, ...],
) -> tuple[tuple[RenderableType, ...], ...]:
    """Flatten findings into a unified rowset matching :data:`ADVISORY_COLUMNS`."""
    return build_advisory_rows_short(findings)


def build_advisory_summary(
    findings: tuple[AdvisoryFinding, ...], deferred_count: int = 0
) -> Notice:
    """Build the trailing per-severity count notice.

    Args:
        findings: All rendered findings (after override filtering).
        deferred_count: Number of deferred findings excluded from display.

    Returns:
        A :class:`Notice` summarising counts per severity.
    """
    counts = {s: 0 for s in SEVERITY_ORDER}
    for f in findings:
        counts[f.severity] += 1
    parts = [f"{counts[s]} {s.value}" for s in SEVERITY_ORDER]
    suffix = f"; {deferred_count} deferred" if deferred_count else ""
    return Notice.info(f"{len(findings)} advisory finding(s): {', '.join(parts)}{suffix}.")
