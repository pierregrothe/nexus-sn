# src/nexus/capabilities/status_reporter.py
# Rich-based status panels for `nexus status`.
# Author: Pierre Grothe
# Date: 2026-05-08
"""StatusReporter: render the multi-panel `nexus status` dashboard.

Panels: top summary, system + account columns, MCP server table, runtime
diagnostics + auto-update columns. All borders use the NEXUS theme so the
dashboard reads as a coherent visual identity.
"""

from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from nexus.capabilities.feature_flags import FEATURE_MAP, MCPServer
from nexus.capabilities.registry import CapabilitySet
from nexus.capabilities.runtime_info import RuntimeInfo, collect_runtime_info
from nexus.capabilities.tier import Tier, TierDetection

__all__ = ["StatusReporter"]

_PRIMARY = "primary"
_ACCENT = "accent"
_KB = 1024
_MB = _KB * 1024
_GB = _MB * 1024


class StatusReporter:
    """Render the verbose `nexus status` dashboard.

    Args:
        console: Rich Console used for output. Tests pass a recording console.
    """

    def __init__(self, console: Console) -> None:
        """See class docstring."""
        self._console = console

    def print(self, detection: TierDetection, capabilities: CapabilitySet) -> None:
        """Print summary + system + account + servers + diagnostics + updater."""
        runtime = collect_runtime_info()
        self._console.print(self._summary_panel(detection, capabilities, runtime))
        self._console.print(
            Columns(
                [self._system_panel(runtime), self._account_panel(detection)],
                expand=True,
                equal=True,
            )
        )
        self._console.print(self._server_panel(detection))
        self._console.print(
            Columns(
                [self._diagnostics_panel(runtime), self._update_panel(runtime)],
                expand=True,
                equal=True,
            )
        )
        if detection.needs_reauth_servers:
            self._console.print(self._reauth_footer(detection))

    def _summary_panel(
        self,
        detection: TierDetection,
        capabilities: CapabilitySet,
        runtime: RuntimeInfo,
    ) -> Panel:
        """Top-level snapshot: tier + ready/total counts."""
        servers_total = len(MCPServer)
        servers_ready = len(capabilities.available_servers - detection.needs_reauth_servers)
        body = Text()
        body.append("Tier:    ", style="muted")
        body.append(f"{detection.tier.value.upper()}\n", style=_PRIMARY)
        body.append("Servers: ", style="muted")
        body.append(f"{servers_ready}/{servers_total} ready", style=_ACCENT)
        if detection.needs_reauth_servers:
            body.append(f"  ({len(detection.needs_reauth_servers)} need reauth)", style="warning")
        body.append("\n")
        body.append("Version: ", style="muted")
        body.append(runtime.nexus_version or "unknown", style=_ACCENT)
        return Panel(body, title="NEXUS", title_align="left", border_style=_PRIMARY)

    def _system_panel(self, runtime: RuntimeInfo) -> Panel:
        """Python + platform + install mode."""
        body = Text()
        body.append("Python:   ", style="muted")
        body.append(f"{runtime.python_version}\n", style=_ACCENT)
        body.append("Platform: ", style="muted")
        body.append(f"{runtime.platform_label}\n", style=_ACCENT)
        body.append("Install:  ", style="muted")
        body.append(runtime.install_mode, style=_ACCENT)
        return Panel(body, title="System", title_align="left", border_style=_ACCENT)

    def _account_panel(self, detection: TierDetection) -> Panel:
        """Subscription + OAuth + org MCP count."""
        config = detection.config
        subscription = (config.subscription_type or "anonymous").upper()
        oauth_state = "yes" if config.subscription_type else "no"
        body = Text()
        body.append("Tier:         ", style="muted")
        body.append(f"{detection.tier.value.upper()}\n", style=_PRIMARY)
        body.append("Subscription: ", style="muted")
        body.append(f"{subscription}\n", style=_PRIMARY)
        body.append("OAuth:        ", style="muted")
        body.append(f"{oauth_state}\n", style="ok" if config.subscription_type else "muted")
        body.append("Org MCPs:     ", style="muted")
        body.append(f"{len(config.org_mcp_servers)} configured", style=_PRIMARY)
        if detection.tier == Tier.PRO:
            body.append("\n")
            body.append("Hint: ", style="muted")
            body.append(
                "ENTERPRISE features unlock when org MCP servers are provisioned",
                style="info",
            )
        return Panel(body, title="Account", title_align="left", border_style=_PRIMARY)

    def _server_panel(self, detection: TierDetection) -> Panel:
        """Full MCP server table -- ALL 7, including not-configured."""
        table = Table(show_header=True, expand=True, box=None)
        table.add_column("Server", style="bold")
        table.add_column("Status")
        table.add_column("Features", overflow="fold")

        for server in sorted(MCPServer, key=lambda s: s.value):
            spec = FEATURE_MAP.get(server)
            if spec is None:  # pragma: no cover -- FEATURE_MAP covers every MCPServer value
                continue
            status, status_style = _server_status(server, detection)
            features = ", ".join(f.value for f in spec.features) or "-"
            table.add_row(spec.name, Text(status, style=status_style), features)

        return Panel(table, title="MCP Servers", title_align="left", border_style=_ACCENT)

    def _diagnostics_panel(self, runtime: RuntimeInfo) -> Panel:
        """Filesystem footprint."""
        body = Text()
        body.append("Config root: ", style="muted")
        body.append(f"{runtime.config_root}\n", style=_ACCENT)
        body.append("Cache size:  ", style="muted")
        body.append(_humanize_bytes(runtime.cache_size_bytes), style=_ACCENT)
        return Panel(body, title="Diagnostics", title_align="left", border_style=_ACCENT)

    def _update_panel(self, runtime: RuntimeInfo) -> Panel:
        """Auto-updater state."""
        body = Text()
        body.append("Enabled:    ", style="muted")
        body.append(
            "yes" if runtime.auto_update_enabled else "no (NEXUS_AUTO_UPDATE=0)",
            style="ok" if runtime.auto_update_enabled else "warning",
        )
        body.append("\n")
        body.append("Last check: ", style="muted")
        body.append(_humanize_age(runtime.last_update_check_ago_seconds), style=_ACCENT)
        if runtime.install_mode == "editable":
            body.append("\n")
            body.append("Note: ", style="muted")
            body.append("editable install -- auto-updater always skips", style="info")
        return Panel(body, title="Auto-update", title_align="left", border_style=_PRIMARY)

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


def _server_status(server: MCPServer, detection: TierDetection) -> tuple[str, str]:
    """Return (label, theme-style) for a server."""
    if server in detection.needs_reauth_servers:
        return ("NEEDS REAUTH", "warning")
    if server in detection.detected_servers:
        return ("READY", "ok")
    return ("not configured", "muted")


def _humanize_bytes(n: int) -> str:
    if n < _KB:
        return f"{n} B"
    if n < _MB:
        return f"{n / _KB:.1f} KB"
    if n < _GB:
        return f"{n / _MB:.1f} MB"
    return f"{n / _GB:.2f} GB"


def _humanize_age(seconds: float | None) -> str:
    if seconds is None:
        return "never"
    if seconds < 60:
        return f"{int(seconds)} seconds ago"
    if seconds < 3600:
        return f"{int(seconds / 60)} minutes ago"
    if seconds < 86400:
        return f"{seconds / 3600:.1f} hours ago"
    return f"{seconds / 86400:.1f} days ago"
