# src/nexus/capture/tables.py
# Pluggable table manifest registry for the capture layer.
# Author: Pierre Grothe
# Date: 2026-05-09

"""Table groups and specs defining which SN tables belong to each config domain."""

from dataclasses import dataclass, field

__all__ = [
    "AI_AUTOMATION",
    "DEFAULT_TABLE_GROUPS",
    "RelatedTable",
    "TableGroup",
    "TableSpec",
]


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
    """

    name: str
    display: str
    scope_field: str = "sys_scope"
    related: tuple[RelatedTable, ...] = field(default_factory=tuple)
    key_fields: tuple[str, ...] = field(default_factory=lambda: ("sys_id", "name", "sys_scope"))


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

DEFAULT_TABLE_GROUPS: dict[str, TableGroup] = {
    AI_AUTOMATION.key: AI_AUTOMATION,
}
