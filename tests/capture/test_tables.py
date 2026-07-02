# tests/capture/test_tables.py
# Tests for the capture table-group registry.
# Author: Pierre Grothe
# Date: 2026-07-02

"""Registry-shape tests for nexus.capture.tables."""

from nexus.capture.tables import AI_AUTOMATION, DEFAULT_TABLE_GROUPS, DEVELOPER_PLATFORM

__all__: list[str] = []


def test_default_table_groups_registers_both_groups() -> None:
    assert DEFAULT_TABLE_GROUPS == {
        AI_AUTOMATION.key: AI_AUTOMATION,
        DEVELOPER_PLATFORM.key: DEVELOPER_PLATFORM,
    }


def test_developer_platform_covers_core_config_tables() -> None:
    names = {spec.name for spec in DEVELOPER_PLATFORM.tables}
    assert {
        "sys_script",
        "sys_script_include",
        "sys_script_client",
        "sys_ui_policy",
        "sys_ui_action",
        "sys_security_acl",
        "sysauto_script",
        "wf_workflow",
    } <= names


def test_table_spec_name_field_defaults_to_name() -> None:
    assert all(spec.name_field == "name" for spec in AI_AUTOMATION.tables)


def test_ui_policy_spec_names_by_short_description() -> None:
    spec = next(s for s in DEVELOPER_PLATFORM.tables if s.name == "sys_ui_policy")
    assert spec.name_field == "short_description"
