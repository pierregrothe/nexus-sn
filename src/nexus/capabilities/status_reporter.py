# src/nexus/capabilities/status_reporter.py
# Rich-based status panels for `nexus status`.
# Author: Pierre Grothe
# Date: 2026-05-11
"""StatusReporter: render the condensed ``nexus status`` dashboard.

Layout (4 rows, all gradient-bordered KeyValuePanels):

- Row 1: Identity | System          (two equal columns)
- Row 2: Integrations               (full width DataTable or empty panel)
- Row 3: Diagnostics | Auto-update  (two equal columns)
- Row 4: Terminal                   (render profile + detection inputs)

Labels render in the brand gradient; values render in the terminal default
foreground style. Status words go through ``StatusBadge``.
"""

from rich.console import Console, RenderableType

from nexus.capabilities.feature_flags import FEATURE_MAP
from nexus.capabilities.registry import CapabilitySet
from nexus.capabilities.runtime_info import RuntimeInfo, collect_runtime_info
from nexus.capabilities.tier import TierDetection
from nexus.ui import (
    DataColumn,
    DataTable,
    KeyValuePanel,
    KvRow,
    Notice,
    StatusBadge,
    two_col,
)
from nexus.ui.render_context import RenderContext

__all__ = ["StatusReporter"]

_KB = 1024
_MB = _KB * 1024
_GB = _MB * 1024


class StatusReporter:
    """Render the condensed ``nexus status`` dashboard.

    Args:
        console: Rich Console used for output. Tests pass a recording console.
    """

    def __init__(self, console: Console) -> None:
        """See class docstring."""
        self._console = console

    def print(
        self,
        detection: TierDetection,
        capabilities: CapabilitySet,
        render_context: RenderContext | None = None,
    ) -> None:
        """Print Identity + System + Integrations + Diagnostics + Auto-update + Terminal.

        Args:
            detection: Tier detection result with config + detected servers.
            capabilities: Resolved capability set (unused; the view uses
                ``detection.detected_servers`` directly).
            render_context: Optional render context used to populate the
                Terminal panel. When ``None``, the panel is omitted (preserved
                behaviour for callers that have not yet adopted the context).
        """
        del capabilities
        runtime = collect_runtime_info()

        self._console.print(
            two_col(self._identity_panel(detection, runtime), self._system_panel(runtime))
        )
        self._console.print(self._integrations_panel(detection))
        self._console.print(two_col(self._diagnostics_panel(runtime), self._update_panel(runtime)))
        if render_context is not None:
            self._console.print(self._terminal_panel(render_context))
        if detection.needs_reauth_servers:
            servers = sorted(s.value for s in detection.needs_reauth_servers)
            if len(servers) == 1:
                msg = f"Run `nexus reauth --server {servers[0]}` to fix."
            else:
                msg = f"Run `nexus reauth --server <name>` for: {', '.join(servers)}"
            self._console.print(Notice.warn(msg))

    def _terminal_panel(self, render_context: RenderContext) -> KeyValuePanel:
        """Build the Terminal panel reporting the detected render profile.

        Args:
            render_context: The render context built at process startup.

        Returns:
            ``KeyValuePanel`` titled ``Terminal``.
        """
        caps = render_context.caps
        pager = "pypager" if render_context.profile.value in {"rich", "basic"} else "inline"
        terminal = caps.term_program or ("Windows" if caps.legacy_windows else "default")
        rows: list[KvRow] = [
            KvRow(label="Profile", value=render_context.profile.value.upper()),
            KvRow(label="TTY", value="yes" if caps.is_tty else "no"),
            KvRow(label="Color", value=caps.color_depth.value.upper()),
            KvRow(label="Size", value=f"{caps.cols}x{caps.rows}"),
            KvRow(label="Terminal", value=terminal),
            KvRow(label="Pager", value=pager),
        ]
        return KeyValuePanel(title="Terminal", rows=rows)

    def _identity_panel(self, detection: TierDetection, runtime: RuntimeInfo) -> KeyValuePanel:
        """Build the Identity panel.

        Args:
            detection: Tier detection providing config + server sets.
            runtime: Collected runtime information.

        Returns:
            ``KeyValuePanel`` titled ``Identity``.
        """
        config = detection.config
        reauth_detected = detection.detected_servers & detection.needs_reauth_servers
        total = len(detection.detected_servers)
        ready = total - len(reauth_detected)
        rows: list[KvRow] = [
            KvRow(label="User", value=config.email or "-"),
            KvRow(label="Org", value=config.organization_name or "-"),
            KvRow(label="Tier", value=detection.tier.value.upper()),
            KvRow(label="Version", value=runtime.nexus_version or "unknown"),
        ]
        if total:
            suffix: RenderableType | None = (
                StatusBadge.warn(f"{len(reauth_detected)} need reauth") if reauth_detected else None
            )
            rows.append(KvRow(label="Servers", value=f"{ready}/{total} ready", suffix=suffix))
        return KeyValuePanel(title="Identity", rows=rows)

    def _system_panel(self, runtime: RuntimeInfo) -> KeyValuePanel:
        """Build the System panel.

        Args:
            runtime: Collected runtime information.

        Returns:
            ``KeyValuePanel`` titled ``System``.
        """
        return KeyValuePanel(
            title="System",
            rows=[
                KvRow(label="Python", value=runtime.python_version),
                KvRow(label="Platform", value=runtime.platform_label),
                KvRow(label="Install", value=runtime.install_mode),
            ],
        )

    def _integrations_panel(self, detection: TierDetection) -> KeyValuePanel | DataTable:
        """Build the Integrations panel.

        Args:
            detection: Tier detection providing the detected/reauth server sets.

        Returns:
            A ``DataTable`` listing each detected server with a ``StatusBadge``,
            or an empty ``KeyValuePanel`` placeholder when no servers are
            detected.
        """
        if not detection.detected_servers:
            return KeyValuePanel(
                title="Integrations",
                rows=[KvRow(label="Status", value="No enterprise integrations detected.")],
            )
        rows: list[list[RenderableType]] = []
        for server in sorted(detection.detected_servers, key=lambda s: s.value):
            spec = FEATURE_MAP.get(server)
            name = spec.name if spec else server.value
            badge = (
                StatusBadge.warn("NEEDS REAUTH")
                if server in detection.needs_reauth_servers
                else StatusBadge.ok("READY")
            )
            rows.append([name, badge])
        return DataTable(
            title="Integrations",
            columns=[DataColumn(header="Server"), DataColumn(header="Status")],
            rows=rows,
        )

    def _diagnostics_panel(self, runtime: RuntimeInfo) -> KeyValuePanel:
        """Build the Diagnostics panel.

        Args:
            runtime: Collected runtime information.

        Returns:
            ``KeyValuePanel`` titled ``Diagnostics``.
        """
        return KeyValuePanel(
            title="Diagnostics",
            rows=[
                KvRow(label="Config root", value=str(runtime.config_root)),
                KvRow(label="Cache size", value=_humanize_bytes(runtime.cache_size_bytes)),
            ],
        )

    def _update_panel(self, runtime: RuntimeInfo) -> KeyValuePanel:
        """Build the Auto-update panel.

        Args:
            runtime: Collected runtime information.

        Returns:
            ``KeyValuePanel`` titled ``Auto-update``.
        """
        enabled_value: RenderableType = (
            StatusBadge.ok("yes")
            if runtime.auto_update_enabled
            else StatusBadge.warn("no (NEXUS_AUTO_UPDATE=0)")
        )
        rows: list[KvRow] = [
            KvRow(label="Enabled", value=enabled_value),
            KvRow(
                label="Last check",
                value=_humanize_age(runtime.last_update_check_ago_seconds),
            ),
        ]
        if runtime.install_mode == "editable":
            rows.append(KvRow(label="Note", value="editable install: auto-update disabled"))
        return KeyValuePanel(title="Auto-update", rows=rows)


def _humanize_bytes(n: int) -> str:
    """Format a byte count as a human-readable string.

    Args:
        n: Byte count.

    Returns:
        Human-readable byte count using the largest unit that yields a value
        below 1024 (``B``, ``KB``, ``MB``, ``GB``).
    """
    if n < _KB:
        return f"{n} B"
    if n < _MB:
        return f"{n / _KB:.1f} KB"
    if n < _GB:
        return f"{n / _MB:.1f} MB"
    return f"{n / _GB:.2f} GB"


def _humanize_age(seconds: float | None) -> str:
    """Format elapsed seconds as a human-readable age string.

    Args:
        seconds: Number of seconds elapsed, or ``None`` if no event occurred.

    Returns:
        Human-readable duration using the largest unit that yields a value
        below the next boundary (``seconds``, ``minutes``, ``hours``, ``days``).
        Returns ``"never"`` when ``seconds`` is ``None``.
    """
    if seconds is None:
        return "never"
    if seconds < 60:
        return f"{int(seconds)} seconds ago"
    if seconds < 3600:
        return f"{int(seconds / 60)} minutes ago"
    if seconds < 86400:
        return f"{seconds / 3600:.1f} hours ago"
    return f"{seconds / 86400:.1f} days ago"
