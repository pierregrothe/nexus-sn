# src/nexus/capabilities/status_reporter.py
# Rich-based status panels for `nexus status`.
# Author: Pierre Grothe
# Date: 2026-05-08
"""StatusReporter: render the condensed `nexus status` dashboard.

Layout (3 rows, all gradient-bordered panels):
  Row 1: Identity | System          (two equal columns, height-equalized)
  Row 2: Integrations               (full width, only detected MCP servers)
  Row 3: Diagnostics | Auto-update  (two equal columns, height-equalized)

Value text uses a per-character gradient from SN_TEXT_START (teal) to SN_LIME,
so the content palette matches the border gradient.
"""

from rich.console import Console, RenderableType
from rich.table import Table
from rich.text import Text

from nexus.capabilities.feature_flags import FEATURE_MAP
from nexus.capabilities.registry import CapabilitySet
from nexus.capabilities.runtime_info import RuntimeInfo, collect_runtime_info
from nexus.capabilities.tier import TierDetection
from nexus.ui.gradient_panel import GradientPanel, gradient_text
from nexus.ui.theme import SN_BLUE, SN_LIME, SN_TEXT_START

__all__ = ["StatusReporter"]

_KB = 1024
_MB = _KB * 1024
_GB = _MB * 1024


def _val(text: str) -> Text:
    """Color a value string with a gradient from SN_TEXT_START to SN_LIME."""
    return gradient_text(text, start=SN_TEXT_START, end=SN_LIME)


def _panel(renderable: RenderableType, *, title: str, min_height: int = 0) -> GradientPanel:
    """Construct a GradientPanel with the project's ServiceNow gradient."""
    return GradientPanel(renderable, title=title, start=SN_BLUE, end=SN_LIME, min_height=min_height)


def _two_col(left: RenderableType, right: RenderableType) -> Table:
    """Lay out two renderables side by side in equal columns."""
    grid = Table.grid(expand=True)
    grid.add_column(ratio=1)
    grid.add_column(ratio=1)
    grid.add_row(left, right)
    return grid


def _line_count(text: Text) -> int:
    """Count rendered lines in a Text object (newlines + 1)."""
    return text.plain.count("\n") + 1


class StatusReporter:
    """Render the condensed `nexus status` dashboard.

    Args:
        console: Rich Console used for output. Tests pass a recording console.
    """

    def __init__(self, console: Console) -> None:
        """See class docstring."""
        self._console = console

    def print(self, detection: TierDetection, capabilities: CapabilitySet) -> None:
        """Print identity + system + integrations + diagnostics + updater."""
        del capabilities  # superseded by detection.detected_servers in this view
        runtime = collect_runtime_info()

        identity_body = self._identity_body(detection, runtime)
        system_body = self._system_body(runtime)
        h1 = max(_line_count(identity_body), _line_count(system_body))
        self._console.print(
            _two_col(
                _panel(identity_body, title="Identity", min_height=h1),
                _panel(system_body, title="System", min_height=h1),
            )
        )

        self._console.print(self._integrations_panel(detection))

        diag_body = self._diagnostics_body(runtime)
        update_body = self._update_body(runtime)
        h2 = max(_line_count(diag_body), _line_count(update_body))
        self._console.print(
            _two_col(
                _panel(diag_body, title="Diagnostics", min_height=h2),
                _panel(update_body, title="Auto-update", min_height=h2),
            )
        )

        if detection.needs_reauth_servers:
            self._console.print(self._reauth_footer(detection))

    def _identity_body(self, detection: TierDetection, runtime: RuntimeInfo) -> Text:
        """User email, org, tier, version, and server readiness."""
        config = detection.config
        reauth_detected = detection.detected_servers & detection.needs_reauth_servers
        total = len(detection.detected_servers)
        ready = total - len(reauth_detected)
        body = Text()
        body.append("User:    ", style="muted")
        body.append_text(
            _val(config.email) if config.email else Text("not authenticated", style="muted")
        )
        body.append("\n")
        body.append("Org:     ", style="muted")
        body.append_text(
            _val(config.organization_name) if config.organization_name else Text("-", style="muted")
        )
        body.append("\n")
        body.append("Tier:    ", style="muted")
        body.append_text(_val(detection.tier.value.upper()))
        body.append("\n")
        body.append("Version: ", style="muted")
        body.append_text(_val(runtime.nexus_version or "unknown"))
        if total:
            body.append("\n")
            body.append("Servers: ", style="muted")
            body.append_text(_val(f"{ready}/{total} ready"))
            if reauth_detected:
                body.append(
                    f"  ({len(reauth_detected)} need reauth)",
                    style="warning",
                )
        return body

    def _system_body(self, runtime: RuntimeInfo) -> Text:
        """Python + platform + install mode."""
        body = Text()
        body.append("Python:   ", style="muted")
        body.append_text(_val(runtime.python_version))
        body.append("\n")
        body.append("Platform: ", style="muted")
        body.append_text(_val(runtime.platform_label))
        body.append("\n")
        body.append("Install:  ", style="muted")
        body.append_text(_val(runtime.install_mode))
        return body

    def _integrations_panel(self, detection: TierDetection) -> GradientPanel:
        """Detected enterprise MCP integrations only."""
        if not detection.detected_servers:
            return _panel(
                Text("No enterprise integrations detected.", style="muted"),
                title="Integrations",
            )
        table = Table(show_header=True, expand=True, box=None)
        table.add_column("Server", style="bold")
        table.add_column("Status")
        for server in sorted(detection.detected_servers, key=lambda s: s.value):
            spec = FEATURE_MAP.get(server)
            name = spec.name if spec else server.value
            if server in detection.needs_reauth_servers:
                table.add_row(name, Text("NEEDS REAUTH", style="warning"))
            else:
                table.add_row(name, Text("READY", style="ok"))
        return _panel(table, title="Integrations")

    def _diagnostics_body(self, runtime: RuntimeInfo) -> Text:
        """Filesystem footprint."""
        body = Text()
        body.append("Config root: ", style="muted")
        body.append_text(_val(str(runtime.config_root)))
        body.append("\n")
        body.append("Cache size:  ", style="muted")
        body.append_text(_val(_humanize_bytes(runtime.cache_size_bytes)))
        return body

    def _update_body(self, runtime: RuntimeInfo) -> Text:
        """Auto-updater state."""
        body = Text()
        body.append("Enabled:    ", style="muted")
        body.append(
            "yes" if runtime.auto_update_enabled else "no (NEXUS_AUTO_UPDATE=0)",
            style="ok" if runtime.auto_update_enabled else "warning",
        )
        body.append("\n")
        body.append("Last check: ", style="muted")
        body.append_text(_val(_humanize_age(runtime.last_update_check_ago_seconds)))
        if runtime.install_mode == "editable":
            body.append("\n")
            body.append("Note: ", style="muted")
            body.append("editable install: auto-update disabled", style="info")
        return body

    def _reauth_footer(self, detection: TierDetection) -> Text:
        """Build the re-auth instruction line."""
        servers = sorted(s.value for s in detection.needs_reauth_servers)
        text = Text()
        if len(servers) == 1:
            text.append(f"Run `nexus reauth --server {servers[0]}` to fix.", style="warning")
            return text
        text.append("Run ", style="warning")
        text.append("`nexus reauth --server <name>`", style="bold warning")
        text.append(f" for: {', '.join(servers)}", style="warning")
        return text


def _humanize_bytes(n: int) -> str:
    """Format byte count as a human-readable string."""
    if n < _KB:
        return f"{n} B"
    if n < _MB:
        return f"{n / _KB:.1f} KB"
    if n < _GB:
        return f"{n / _MB:.1f} MB"
    return f"{n / _GB:.2f} GB"


def _humanize_age(seconds: float | None) -> str:
    """Format elapsed seconds as a human-readable age string."""
    if seconds is None:
        return "never"
    if seconds < 60:
        return f"{int(seconds)} seconds ago"
    if seconds < 3600:
        return f"{int(seconds / 60)} minutes ago"
    if seconds < 86400:
        return f"{seconds / 3600:.1f} hours ago"
    return f"{seconds / 86400:.1f} days ago"
