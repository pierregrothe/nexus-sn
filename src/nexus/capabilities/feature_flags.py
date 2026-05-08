# nexus/capabilities/feature_flags.py
# Maps ServiceNow enterprise MCP servers to feature flag names.
# Author: Pierre Grothe
# Date: 2026-05-07

"""Feature flag definitions tied to enterprise MCP server availability.

Each entry in FEATURE_MAP declares what features become available when a
specific MCP server responds to the startup probe. Features whose server
is unavailable are hidden from the CLI and silently skipped by agents.
"""

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "CLAUDE_AI_NAME_TO_SERVER",
    "FEATURE_MAP",
    "FeatureFlag",
    "MCPServer",
    "ServerSpec",
    "claude_ai_name_for",
]


class FeatureFlag(StrEnum):
    """Named feature flags controlled by MCP server availability."""

    ROI_ANALYSIS = "roi_analysis"
    VE_PIPELINE = "ve_pipeline"
    CONTENT_SEARCH = "content_search"
    COMPETITIVE_INTEL = "competitive_intel"
    BATTLE_CARDS = "battle_cards"
    WORK_ITEM_LOOKUP = "work_item_lookup"
    PROJECT_TRACKING = "project_tracking"
    ACCOUNT_INSIGHTS = "account_insights"
    CUSTOMER_DATA = "customer_data"
    DEAL_REGISTRATION = "deal_registration"
    PARTNER_DATA = "partner_data"
    EMAIL_CALENDAR = "email_calendar"
    SHAREPOINT_CONTENT = "sharepoint_content"


class MCPServer(StrEnum):
    """Known ServiceNow enterprise MCP server identifiers."""

    VALUE_MELODY = "value_melody"
    SSC = "ssc"
    BT1 = "bt1"
    DATA_ANALYTICS = "data_analytics"
    GTM = "gtm"
    M365 = "m365"
    MARKETING = "marketing"


@dataclass(slots=True, frozen=True)
class ServerSpec:
    """Specification for a known enterprise MCP server.

    Attributes:
        name: Display name for CLI output.
        description: Short description of what this server provides.
        features: Feature flags unlocked when this server is available.
    """

    name: str
    description: str
    features: tuple[FeatureFlag, ...]


FEATURE_MAP: dict[MCPServer, ServerSpec] = {
    MCPServer.VALUE_MELODY: ServerSpec(
        name="Value Melody",
        description="ROI analysis and value engineering pipeline data",
        features=(FeatureFlag.ROI_ANALYSIS, FeatureFlag.VE_PIPELINE),
    ),
    MCPServer.SSC: ServerSpec(
        name="Sales Success Center",
        description="Sales content, competitive intelligence, and battle cards",
        features=(
            FeatureFlag.CONTENT_SEARCH,
            FeatureFlag.COMPETITIVE_INTEL,
            FeatureFlag.BATTLE_CARDS,
        ),
    ),
    MCPServer.BT1: ServerSpec(
        name="BT1",
        description="Internal ServiceNow work item tracking and project data",
        features=(FeatureFlag.WORK_ITEM_LOOKUP, FeatureFlag.PROJECT_TRACKING),
    ),
    MCPServer.DATA_ANALYTICS: ServerSpec(
        name="Data Analytics",
        description="Snowflake-based customer analytics and account insights",
        features=(FeatureFlag.ACCOUNT_INSIGHTS, FeatureFlag.CUSTOMER_DATA),
    ),
    MCPServer.GTM: ServerSpec(
        name="GTM",
        description="Go-to-market tools: deal registration and partner data",
        features=(FeatureFlag.DEAL_REGISTRATION, FeatureFlag.PARTNER_DATA),
    ),
    MCPServer.M365: ServerSpec(
        name="Microsoft 365",
        description="Email, calendar, and SharePoint content",
        features=(FeatureFlag.EMAIL_CALENDAR, FeatureFlag.SHAREPOINT_CONTENT),
    ),
    MCPServer.MARKETING: ServerSpec(
        name="Marketing MCP",
        description="Marketing operations (Marketo, campaign analytics).",
        features=(),
    ),
}

CLAUDE_AI_NAME_TO_SERVER: dict[str, MCPServer] = {
    "claude.ai ValueMelody": MCPServer.VALUE_MELODY,
    "claude.ai Sales Success Center Content Retriever": MCPServer.SSC,
    "claude.ai BT1_MCP": MCPServer.BT1,
    "claude.ai Data_Analytics_Connection": MCPServer.DATA_ANALYTICS,
    "claude.ai GTM MCP": MCPServer.GTM,
    "claude.ai Microsoft 365": MCPServer.M365,
    "claude.ai Marketing MCP": MCPServer.MARKETING,
}

_SERVER_TO_CLAUDE_AI_NAME: dict[MCPServer, str] = {
    server: name for name, server in CLAUDE_AI_NAME_TO_SERVER.items()
}


def claude_ai_name_for(server: MCPServer) -> str:
    """Return the claude.ai-side string for a given MCPServer enum value.

    Used by `nexus reauth` to construct the exact `claude /mcp <NAME>` command.

    Args:
        server: The MCPServer enum member.

    Returns:
        The "claude.ai <Name>" string used by Claude Code.

    Raises:
        KeyError: If the server has no mapping (a new MCPServer was added
            without updating `CLAUDE_AI_NAME_TO_SERVER`).
    """
    return _SERVER_TO_CLAUDE_AI_NAME[server]
