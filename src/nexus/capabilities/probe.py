# nexus/capabilities/probe.py
# Probes ServiceNow enterprise MCP servers at startup to detect availability.
# Author: Pierre Grothe
# Date: 2026-05-07

"""MCPProbe: lightweight availability check for each known MCP server.

Each probe is a non-blocking check that completes within the configured
timeout. Results feed into CapabilitySet to enable or disable features.
"""

import asyncio
import logging
import time
from dataclasses import dataclass

import anthropic

from nexus.capabilities.feature_flags import MCPServer

log = logging.getLogger(__name__)

__all__ = ["ProbeResult", "MCPProbe"]


@dataclass(slots=True, frozen=True)
class ProbeResult:
    """Result of a single MCP server probe.

    Attributes:
        server: The server that was probed.
        available: True when the server responded within the timeout.
        latency_ms: Round-trip time in milliseconds, or None if unavailable.
        error: Error message if the probe failed.
    """

    server: MCPServer
    available: bool
    latency_ms: float | None = None
    error: str | None = None


class MCPProbe:
    """Probe all known enterprise MCP servers and return availability results.

    Args:
        api_key: Claude Enterprise API key.
        timeout_seconds: Per-server probe timeout.
    """

    def __init__(self, api_key: str, timeout_seconds: int = 5) -> None:
        self._api_key = api_key
        self._timeout = timeout_seconds

    async def probe_all(self) -> list[ProbeResult]:
        """Probe every known MCP server concurrently.

        Returns:
            List of ProbeResult, one per MCPServer entry.
        """
        log.info("probing %d enterprise MCP servers (timeout=%ds)", len(MCPServer), self._timeout)
        tasks = [self._probe_one(server) for server in MCPServer]
        results = await asyncio.gather(*tasks)
        available = sum(1 for r in results if r.available)
        log.info("MCP probe complete: %d/%d servers available", available, len(results))
        return list(results)

    async def _probe_one(self, server: MCPServer) -> ProbeResult:
        """Probe a single MCP server.

        Args:
            server: The server to probe.

        Returns:
            ProbeResult indicating availability and latency.
        """
        start = time.monotonic()
        try:
            async with asyncio.timeout(self._timeout):
                available = await self._check_server(server)
            latency_ms = (time.monotonic() - start) * 1000
            log.debug("server=%s available=%s latency=%.0fms", server, available, latency_ms)
            return ProbeResult(server=server, available=available, latency_ms=latency_ms)
        except TimeoutError:
            log.debug("server=%s timed out after %ds", server, self._timeout)
            return ProbeResult(server=server, available=False, error="timeout")
        except Exception as exc:
            log.debug("server=%s probe error: %s", server, exc)
            return ProbeResult(server=server, available=False, error=str(exc))

    async def _check_server(self, server: MCPServer) -> bool:
        """Perform a lightweight availability check against a server.

        The check uses the Anthropic API's MCP tool-list capability.
        Returns True if the server responds, False otherwise.

        Args:
            server: The MCP server to check.

        Returns:
            True if the server is reachable and responds.
        """
        # Stub: real implementation will call the Anthropic API with
        # the MCP server config and check if tools are returned.
        # Returns False until the enterprise MCP server endpoints are known.
        _ = server
        _ = anthropic  # imported for future use
        return False  # pragma: no cover
