# src/nexus/capabilities/status_reporter.py
# Rich-based status panel for nexus status output.
# Author: Pierre Grothe
# Date: 2026-05-08
"""StatusReporter: render a NEXUS status panel + MCP server table.

Used by `nexus status` to print the user's tier, available MCP servers,
and any servers needing re-authentication.
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from nexus.capabilities.feature_flags import FEATURE_MAP, MCPServer
from nexus.capabilities.registry import CapabilitySet
from nexus.capabilities.tier import TierDetection

__all__ = ["StatusReporter"]


class StatusReporter:
    """Render a NEXUS status panel.

    Args:
        console: Rich Console used for output. Tests pass a recording console.
    """

    def __init__(self, console: Console) -> None:
        """See class docstring."""
        self._console = console

    def print(self, detection: TierDetection, capabilities: CapabilitySet) -> None:
        """Print the panel + optional MCP server table + re-auth footer."""
        self._console.print(self._panel(detection, capabilities))
        if detection.detected_servers or detection.needs_reauth_servers:
            self._console.print(self._server_table(detection))
        if detection.needs_reauth_servers:
            self._console.print(self._reauth_footer(detection))

    def _panel(self, detection: TierDetection, capabilities: CapabilitySet) -> Panel:
        """Build the top-level NEXUS Status panel."""
        servers_total = len(MCPServer)
        servers_ready = len(capabilities.available_servers - detection.needs_reauth_servers)
        body = (
            f"Tier: {detection.tier.value.capitalize()}\n"
            f"{servers_ready}/{servers_total} MCP servers ready"
        )
        return Panel(body, title="NEXUS Status", title_align="left")

    def _server_table(self, detection: TierDetection) -> Table:
        """Build the per-server status table."""
        table = Table(title="MCP Servers", show_header=True)
        table.add_column("Server", style="bold")
        table.add_column("Status")
        table.add_column("Features")

        for server in sorted(detection.detected_servers, key=lambda s: s.value):
            spec = FEATURE_MAP.get(server)
            if spec is None:
                continue
            status = "needs re-auth" if server in detection.needs_reauth_servers else "ready"
            features = ", ".join(f.value for f in spec.features) or "-"
            table.add_row(spec.name, status, features)
        return table

    def _reauth_footer(self, detection: TierDetection) -> str:
        """Build the re-auth instruction line."""
        servers = sorted(s.value for s in detection.needs_reauth_servers)
        if len(servers) == 1:
            return f"Run `nexus reauth --server {servers[0]}` to fix."
        names = ", ".join(servers)
        return f"Run `nexus reauth --server <name>` for: {names}"
