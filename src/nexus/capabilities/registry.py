# nexus/capabilities/registry.py
# CapabilitySet: immutable snapshot of what MCP features are live this session.
# Author: Pierre Grothe
# Date: 2026-05-07

"""CapabilitySet: session-scoped capability snapshot built from probe results."""

import logging
from dataclasses import dataclass

from nexus.capabilities.feature_flags import FEATURE_MAP, FeatureFlag, MCPServer
from nexus.capabilities.probe import ProbeResult
from nexus.capabilities.tier import Tier, TierDetection

log = logging.getLogger(__name__)

__all__ = ["CapabilitySet"]


@dataclass(slots=True, frozen=True)
class CapabilitySet:
    """Immutable snapshot of available MCP features for this session.

    Built from a TierDetection (config-only path) or probe results (live-probe
    path). Passed to LLM clients so they can inject available MCP tool configs.

    Attributes:
        available_servers: Servers that responded to the probe (or were detected).
        unavailable_servers: Servers that timed out, errored, or were not detected.
        enabled_features: Feature flags that are active.
        tier: User Tier resolved from authentication + org MCP presence.
        needs_reauth: Servers currently flagged for re-authentication.
    """

    available_servers: frozenset[MCPServer]
    unavailable_servers: frozenset[MCPServer]
    enabled_features: frozenset[FeatureFlag]
    tier: Tier
    needs_reauth: frozenset[MCPServer]

    @classmethod
    def from_probe_results(cls, results: list[ProbeResult]) -> CapabilitySet:
        """Build a CapabilitySet from a list of probe results.

        Args:
            results: Results from MCPProbe.probe_all().

        Returns:
            CapabilitySet reflecting the current session's capabilities. tier
            defaults to Tier.PRO and needs_reauth to empty -- callers using
            the live-probe path should populate these from a separate
            TierDetection if needed.
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
            tier=Tier.PRO,
            needs_reauth=frozenset(),
        )

    @classmethod
    def from_detection(cls, detection: TierDetection) -> CapabilitySet:
        """Build a CapabilitySet from a TierDetection (no live probe).

        All detected servers are considered available; remaining MCPServer
        members are unavailable. Features are unioned from FEATURE_MAP for
        each available server.

        Args:
            detection: TierDetection from TierDetector.detect().

        Returns:
            CapabilitySet with tier and needs_reauth populated from the detection.
        """
        all_servers = frozenset(MCPServer)
        unavailable = all_servers - detection.detected_servers
        features: set[FeatureFlag] = set()
        for server in detection.detected_servers:
            spec = FEATURE_MAP.get(server)
            if spec:
                features.update(spec.features)
        log.info(
            "capability set from detection: tier=%s; %d servers; %d features",
            detection.tier,
            len(detection.detected_servers),
            len(features),
        )
        return cls(
            available_servers=detection.detected_servers,
            unavailable_servers=unavailable,
            enabled_features=frozenset(features),
            tier=detection.tier,
            needs_reauth=detection.needs_reauth_servers,
        )

    @classmethod
    def none(cls) -> CapabilitySet:
        """Return an empty CapabilitySet (no MCP servers available).

        Returns:
            CapabilitySet with all servers marked unavailable, tier=ANONYMOUS.
        """
        all_servers = frozenset(MCPServer)
        return cls(
            available_servers=frozenset(),
            unavailable_servers=all_servers,
            enabled_features=frozenset(),
            tier=Tier.ANONYMOUS,
            needs_reauth=frozenset(),
        )

    def has_feature(self, flag: FeatureFlag) -> bool:
        """Return True if the given feature flag is enabled.

        Args:
            flag: The feature to check.

        Returns:
            True when the feature's MCP server was available.
        """
        return flag in self.enabled_features
