# nexus/capabilities/registry.py
# CapabilitySet: immutable snapshot of what MCP features are live this session.
# Author: Pierre Grothe
# Date: 2026-05-07

"""CapabilitySet: session-scoped capability snapshot built from probe results."""

import logging
from dataclasses import dataclass, field
from functools import cache

from nexus.capabilities.feature_flags import FEATURE_MAP, FeatureFlag, MCPServer
from nexus.capabilities.probe import ProbeResult

log = logging.getLogger(__name__)

__all__ = ["CapabilitySet"]


@dataclass(slots=True, frozen=True)
class CapabilitySet:
    """Immutable snapshot of available MCP features for this session.

    Built from probe results at startup. Passed to the Anthropic client
    so it can inject available MCP tool configurations.

    Attributes:
        available_servers: Servers that responded to the probe.
        unavailable_servers: Servers that timed out or errored.
        enabled_features: Feature flags that are active.
    """

    available_servers: frozenset[MCPServer]
    unavailable_servers: frozenset[MCPServer]
    enabled_features: frozenset[FeatureFlag]

    @classmethod
    def from_probe_results(cls, results: list[ProbeResult]) -> "CapabilitySet":
        """Build a CapabilitySet from a list of probe results.

        Args:
            results: Results from MCPProbe.probe_all().

        Returns:
            CapabilitySet reflecting the current session's capabilities.
        """
        available: set[MCPServer] = set()
        unavailable: set[MCPServer] = set()
        features: set[FeatureFlag] = set()

        for result in results:
            if result.available:
                available.add(result.server)
                spec = FEATURE_MAP.get(result.server)
                if spec:
                    features.update(spec.features)
            else:
                unavailable.add(result.server)

        log.info(
            "capability set built: %d servers available, %d features enabled",
            len(available),
            len(features),
        )
        return cls(
            available_servers=frozenset(available),
            unavailable_servers=frozenset(unavailable),
            enabled_features=frozenset(features),
        )

    @classmethod
    def none(cls) -> "CapabilitySet":
        """Return an empty CapabilitySet (no MCP servers available).

        Returns:
            CapabilitySet with all servers marked unavailable.
        """
        all_servers = frozenset(MCPServer)
        return cls(
            available_servers=frozenset(),
            unavailable_servers=all_servers,
            enabled_features=frozenset(),
        )

    def has_feature(self, flag: FeatureFlag) -> bool:
        """Return True if the given feature flag is enabled.

        Args:
            flag: The feature to check.

        Returns:
            True when the feature's MCP server was available.
        """
        return flag in self.enabled_features
