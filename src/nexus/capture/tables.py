# src/nexus/capture/tables.py
# Pluggable table manifest registry for the capture layer.
# Author: Pierre Grothe
# Date: 2026-05-09

"""Table groups and specs defining which SN tables belong to each config domain."""

from dataclasses import dataclass, field

__all__ = [
    "AI_AUTOMATION",
    "CUSTOM_SCOPE_PREFIXES",
    "DEFAULT_TABLE_GROUPS",
    "DEVELOPER_PLATFORM",
    "RelatedTable",
    "TableGroup",
    "TableSpec",
]

CUSTOM_SCOPE_PREFIXES: tuple[str, ...] = ("x_", "u_")
"""Scope-key prefixes that mark a user-developed (custom) scoped app.

Single-sourced here so assess/replatform checklists and migrate baselines
never desynchronize on which scopes count as "custom" -- a prefix change
updating only one copy would cause false drift on every recheck.
"""


@dataclass(slots=True, frozen=True)
class RelatedTable:
    """A child table fetched together with its parent record.

    Args:
        name: Table API name of the child table.
        join_field: Field on the child table that references the parent sys_id.
    """

    name: str
    join_field: str


@dataclass(slots=True, frozen=True)
class TableSpec:
    """One table included in a capture group.

    Args:
        name: Table API name, e.g. "ai_skill".
        display: Human-readable label for CLI output.
        scope_field: Field on this table carrying the application scope ref.
        related: Child tables fetched in the same pass as this table's records.
        key_fields: Fields to include in the archive record summary.
        name_field: Field carrying this table's display name (some tables,
            e.g. sys_ui_policy, have no `name` field and use another instead).
    """

    name: str
    display: str
    scope_field: str = "sys_scope"
    related: tuple[RelatedTable, ...] = field(default_factory=tuple)
    key_fields: tuple[str, ...] = ("sys_id", "name", "sys_scope")
    name_field: str = "name"


@dataclass(slots=True, frozen=True)
class TableGroup:
    """A named collection of TableSpecs forming one config domain.

    Args:
        key: Machine-readable identifier used in CLI and archive manifests.
        display: Human-readable label for CLI output.
        tables: The tables belonging to this group.
    """

    key: str
    display: str
    tables: tuple[TableSpec, ...]


AI_AUTOMATION: TableGroup = TableGroup(
    key="ai_automation",
    display="AI & Automation",
    tables=(
        TableSpec(
            name="ai_skill",
            display="NowAssist Skills",
        ),
        TableSpec(
            name="sys_hub_flow",
            display="Flows & Subflows",
            related=(
                RelatedTable(name="sys_hub_flow_input", join_field="flow"),
                RelatedTable(name="sys_hub_flow_logic", join_field="flow"),
            ),
        ),
        TableSpec(
            name="sys_hub_action_type_definition",
            display="IntegrationHub Actions",
        ),
        TableSpec(
            name="virtual_agent_conversation_topic",
            display="Virtual Agent Topics",
            related=(RelatedTable(name="sn_va_topic_block", join_field="topic"),),
        ),
        TableSpec(
            name="sys_ai_agent",
            display="AI Agents",
            related=(RelatedTable(name="sys_ai_agent_capability", join_field="agent"),),
        ),
    ),
)

# Identity note: sys_security_acl rows share `name` across operations
# (read/write ACLs on one resource). The replatform diff matches keys as a
# multiset, so per-name counts stay honest even without an operation suffix.
DEVELOPER_PLATFORM: TableGroup = TableGroup(
    key="developer_platform",
    display="Developer Platform",
    tables=(
        TableSpec(name="sys_script", display="Business Rules"),
        TableSpec(name="sys_script_include", display="Script Includes"),
        TableSpec(name="sys_script_client", display="Client Scripts"),
        TableSpec(
            name="sys_ui_policy",
            display="UI Policies",
            name_field="short_description",
            key_fields=("sys_id", "short_description", "sys_scope"),
        ),
        TableSpec(name="sys_ui_action", display="UI Actions"),
        TableSpec(name="sys_security_acl", display="Access Controls"),
        TableSpec(name="sysauto_script", display="Scheduled Script Jobs"),
        TableSpec(name="wf_workflow", display="Classic Workflows"),
    ),
)

DEFAULT_TABLE_GROUPS: dict[str, TableGroup] = {
    AI_AUTOMATION.key: AI_AUTOMATION,
    DEVELOPER_PLATFORM.key: DEVELOPER_PLATFORM,
}
