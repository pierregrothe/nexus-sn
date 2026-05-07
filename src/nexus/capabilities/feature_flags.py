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

__all__ = ["FeatureFlag", "MCPServer", "ServerSpec", "FEATURE_MAP"]


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
}
