# tests/test_migrate_capture_bridge.py
# Tests for build_capture_for_selection (story 01b).
# Author: Pierre Grothe
# Date: 2026-07-02

"""AC4-AC6: selection-to-capture translation over the capture-layer fake.

Also holds the normalization-parity guard: the bridge mirrors two private
replatform helpers (natural-key normalization must not diverge between the
classifier and the capture bridge), and the parity tests below import those
private helpers directly to assert byte-identical output over tricky inputs.
"""

import logging

import pytest

from nexus.capture.models import SnFieldValue
from nexus.capture.tables import AI_AUTOMATION, DEFAULT_TABLE_GROUPS, DEVELOPER_PLATFORM
from nexus.migrate.capture_bridge import (
    build_capture_for_selection,
    field_display,
    natural_key_segment,
)
from nexus.replatform.classifier import _display_name, _normalize
from tests.fakes.fake_sn_client import FakeServiceNowClient
from tests.fakes.migrate import make_selection, make_selection_item

_ALECTRI_SCOPE_ROW = {
    "sys_id": "scope001",
    "name": "Alectri Core",
    "scope": "x_alectri_core",
    "version": "1.0.0",
    "vendor": "Alectri",
}
_FLOW_APPROVE_PO = {
    "sys_id": "f1",
    "name": "Approve PO",
    "description": "Approves purchase orders over threshold",
    "sys_scope": "scope001",
    "sys_customer_update": "true",
}
_FLOW_REJECT_PO = {
    "sys_id": "f2",
    "name": "Reject PO",
    "sys_scope": "scope001",
    "sys_customer_update": "true",
}
_SKILL_UNSELECTED = {
    "sys_id": "s1",
    "name": "Some Skill",
    "sys_scope": "scope001",
    "sys_customer_update": "true",
}


def _client_with_flows() -> FakeServiceNowClient:
    return FakeServiceNowClient(
        initial_records={
            "sys_scope": [_ALECTRI_SCOPE_ROW],
            "sys_hub_flow": [_FLOW_APPROVE_PO, _FLOW_REJECT_PO],
            "ai_skill": [_SKILL_UNSELECTED],
        }
    )


@pytest.mark.asyncio
async def test_build_capture_for_selection_happy_path_fetches_exact_scope_and_table() -> None:
    client = _client_with_flows()
    selection = make_selection(
        source_profile="alectri",
        items=(
            make_selection_item(
                key="x_alectri_core|sys_hub_flow|approve po", disposition="include"
            ),
        ),
    )
    async with client:
        results = await build_capture_for_selection(client, selection, DEFAULT_TABLE_GROUPS)

    assert len(results) == 1
    result = results[0]
    assert result.instance_id == "alectri"
    assert result.table_group == "ai_automation"
    assert result.scope_ids == ("scope001",)
    assert len(result.records) == 1
    record = result.records[0]
    assert record.sys_id == "f1"
    assert record.table == "sys_hub_flow"
    # Full record, not a name-only listing.
    assert record.fields["description"] == "Approves purchase orders over threshold"


@pytest.mark.asyncio
async def test_build_capture_for_selection_normalizes_dict_shaped_scope_cell() -> None:
    # ConfigFetcher queries with display_value="all", so a real ServiceNow
    # response's sys_scope reference cell arrives as a
    # {"value": ..., "display_value": ...} dict, not a plain string.
    # ConfigFetcher._row_to_record then falls back to stamping the raw scope
    # sys_id into scope_name -- this fixture reproduces that shape directly
    # (FakeServiceNowClient ignores display_value and returns rows verbatim).
    flow_with_dict_scope = {
        "sys_id": "f7",
        "name": "Approve PO",
        "sys_scope": {"value": "scope001", "display_value": "Alectri Core"},
        "sys_customer_update": "true",
    }
    client = FakeServiceNowClient(
        initial_records={
            "sys_scope": [_ALECTRI_SCOPE_ROW],
            "sys_hub_flow": [flow_with_dict_scope],
        }
    )
    selection = make_selection(
        source_profile="alectri",
        items=(
            make_selection_item(
                key="x_alectri_core|sys_hub_flow|approve po", disposition="include"
            ),
        ),
    )
    async with client:
        results = await build_capture_for_selection(client, selection, DEFAULT_TABLE_GROUPS)

    assert len(results) == 1
    record = results[0].records[0]
    assert record.sys_id == "f7"
    # Bridge fix: scope_name is normalized to the technical scope key (not
    # left as the raw "scope001" sys_id) so record_natural_key matches the
    # Selection's key downstream in build_closure.
    assert record.scope_name == "x_alectri_core"


@pytest.mark.asyncio
async def test_build_capture_for_selection_excludes_unselected_artifact_in_same_table() -> None:
    client = _client_with_flows()
    selection = make_selection(
        source_profile="alectri",
        items=(
            make_selection_item(
                key="x_alectri_core|sys_hub_flow|approve po", disposition="include"
            ),
        ),
    )
    async with client:
        results = await build_capture_for_selection(client, selection, DEFAULT_TABLE_GROUPS)

    sys_ids = {r.sys_id for r in results[0].records}
    assert sys_ids == {"f1"}


@pytest.mark.asyncio
async def test_build_capture_for_selection_never_queries_unselected_sibling_tables() -> None:
    client = _client_with_flows()
    selection = make_selection(
        source_profile="alectri",
        items=(
            make_selection_item(
                key="x_alectri_core|sys_hub_flow|approve po", disposition="include"
            ),
        ),
    )
    async with client:
        await build_capture_for_selection(client, selection, DEFAULT_TABLE_GROUPS)

    tables_queried = {table for table, _query in client.calls}
    # ai_skill is another table in the same ai_automation group -- must never
    # be queried since the selection names only sys_hub_flow.
    assert "ai_skill" not in tables_queried
    assert "sys_hub_flow" in tables_queried


@pytest.mark.asyncio
async def test_build_capture_for_selection_empty_selection_issues_no_client_calls() -> None:
    client = _client_with_flows()
    selection = make_selection(source_profile="alectri", items=())
    async with client:
        results = await build_capture_for_selection(client, selection, DEFAULT_TABLE_GROUPS)

    assert results == ()
    assert client.calls == []


@pytest.mark.asyncio
async def test_build_capture_for_selection_unknown_table_returns_empty_without_calls() -> None:
    client = _client_with_flows()
    selection = make_selection(
        source_profile="alectri",
        items=(make_selection_item(key="x_alectri_core|totally_unknown_table|foo"),),
    )
    async with client:
        results = await build_capture_for_selection(client, selection, DEFAULT_TABLE_GROUPS)

    assert results == ()
    assert client.calls == []


@pytest.mark.asyncio
async def test_build_capture_for_selection_absent_scope_warns_and_continues(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = _client_with_flows()
    selection = make_selection(
        source_profile="alectri",
        items=(
            make_selection_item(
                key="x_alectri_core|sys_hub_flow|approve po", disposition="include"
            ),
            make_selection_item(
                key="x_ghost_scope|sys_hub_flow|phantom flow", disposition="include"
            ),
        ),
    )
    with caplog.at_level(logging.WARNING, logger="nexus.migrate.capture_bridge"):
        async with client:
            results = await build_capture_for_selection(client, selection, DEFAULT_TABLE_GROUPS)

    assert "x_ghost_scope" in caplog.text
    assert "not found" in caplog.text
    # The resolvable scope's artifact is still captured (warn-and-continue).
    sys_ids = {r.sys_id for r in results[0].records}
    assert sys_ids == {"f1"}


@pytest.mark.asyncio
async def test_build_capture_for_selection_all_scopes_absent_returns_empty(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = _client_with_flows()
    selection = make_selection(
        source_profile="alectri",
        items=(make_selection_item(key="x_ghost_scope|sys_hub_flow|phantom flow"),),
    )
    with caplog.at_level(logging.WARNING, logger="nexus.migrate.capture_bridge"):
        async with client:
            results = await build_capture_for_selection(client, selection, DEFAULT_TABLE_GROUPS)

    assert results == ()
    assert "x_ghost_scope" in caplog.text


@pytest.mark.asyncio
async def test_build_capture_for_selection_captures_excluded_item_disposition_blind() -> None:
    client = _client_with_flows()
    selection = make_selection(
        source_profile="alectri",
        items=(
            make_selection_item(
                key="x_alectri_core|sys_hub_flow|approve po", disposition="exclude"
            ),
        ),
    )
    async with client:
        results = await build_capture_for_selection(client, selection, DEFAULT_TABLE_GROUPS)

    sys_ids = {r.sys_id for r in results[0].records}
    assert sys_ids == {"f1"}


@pytest.mark.asyncio
async def test_build_capture_for_selection_uses_table_specific_name_field() -> None:
    policy_row = {
        "sys_id": "p1",
        "short_description": "Block Edit For Contractors",
        "sys_scope": "scope001",
        "sys_customer_update": "true",
    }
    client = FakeServiceNowClient(
        initial_records={
            "sys_scope": [_ALECTRI_SCOPE_ROW],
            "sys_ui_policy": [policy_row],
        }
    )
    selection = make_selection(
        source_profile="alectri",
        items=(
            make_selection_item(
                key="x_alectri_core|sys_ui_policy|block edit for contractors",
                disposition="include",
            ),
        ),
    )
    async with client:
        results = await build_capture_for_selection(client, selection, DEFAULT_TABLE_GROUPS)

    assert len(results) == 1
    assert results[0].table_group == DEVELOPER_PLATFORM.key
    record = results[0].records[0]
    assert record.sys_id == "p1"
    assert record.fields["short_description"] == "Block Edit For Contractors"


@pytest.mark.asyncio
async def test_build_capture_for_selection_keeps_related_children_of_matched_root() -> None:
    logic_row = {
        "sys_id": "l1",
        "flow": "f1",
        "action": "Send Approval Notification",
        "sys_scope": "scope001",
        "sys_customer_update": "true",
    }
    client = FakeServiceNowClient(
        initial_records={
            "sys_scope": [_ALECTRI_SCOPE_ROW],
            "sys_hub_flow": [_FLOW_APPROVE_PO, _FLOW_REJECT_PO],
            "sys_hub_flow_logic": [logic_row],
        }
    )
    selection = make_selection(
        source_profile="alectri",
        items=(
            make_selection_item(
                key="x_alectri_core|sys_hub_flow|approve po", disposition="include"
            ),
        ),
    )
    async with client:
        results = await build_capture_for_selection(client, selection, DEFAULT_TABLE_GROUPS)

    assert results[0].table_group == AI_AUTOMATION.key
    logic_records = [r for r in results[0].records if r.table == "sys_hub_flow_logic"]
    assert len(logic_records) == 1
    assert logic_records[0].parent_sys_id == "f1"


@pytest.mark.asyncio
async def test_build_capture_for_selection_matches_reference_dict_name_field() -> None:
    flow_with_ref_name = {
        "sys_id": "f3",
        "name": {"value": "abc123", "display_value": "Approve PO"},
        "sys_scope": "scope001",
        "sys_customer_update": "true",
    }
    client = FakeServiceNowClient(
        initial_records={
            "sys_scope": [_ALECTRI_SCOPE_ROW],
            "sys_hub_flow": [flow_with_ref_name],
        }
    )
    selection = make_selection(
        source_profile="alectri",
        items=(
            make_selection_item(
                key="x_alectri_core|sys_hub_flow|approve po", disposition="include"
            ),
        ),
    )
    async with client:
        results = await build_capture_for_selection(client, selection, DEFAULT_TABLE_GROUPS)

    sys_ids = {r.sys_id for r in results[0].records}
    assert sys_ids == {"f3"}


@pytest.mark.asyncio
async def test_build_capture_for_selection_matches_none_name_field_via_sys_id_fallback() -> None:
    flow_unnamed = {
        "sys_id": "f9",
        "name": None,
        "sys_scope": "scope001",
        "sys_customer_update": "true",
    }
    client = FakeServiceNowClient(
        initial_records={
            "sys_scope": [_ALECTRI_SCOPE_ROW],
            "sys_hub_flow": [flow_unnamed],
        }
    )
    selection = make_selection(
        source_profile="alectri",
        items=(make_selection_item(key="x_alectri_core|sys_hub_flow|f9", disposition="include"),),
    )
    async with client:
        results = await build_capture_for_selection(client, selection, DEFAULT_TABLE_GROUPS)

    sys_ids = {r.sys_id for r in results[0].records}
    assert sys_ids == {"f9"}


# --- Normalization-parity guard: bridge mirrors vs. replatform originals ---
# The bridge intentionally duplicates nexus.replatform.classifier._normalize
# and ._display_name (they are module-private; the story forbids touching
# replatform to export them). These tests are the mechanical guard that the
# mirrors never drift from the originals. chr(0xDF) is German sharp-s
# (built via chr() to keep this file ASCII-only): str.casefold expands it
# to "ss", unlike str.lower -- a divergence lower()-based drift would fail on.


@pytest.mark.parametrize(
    "name",
    [
        "MiXeD CaSe Flow",
        "  leading and trailing  ",
        "multiple   internal    spaces",
        "tab\tand\nnewline\tseparated",
        "",
        "name|with|separator chars",
        "STRASSE",
        "Stra" + chr(0xDF) + "e",  # German sharp-s, casefold-expands to "ss"
    ],
)
def test_natural_key_segment_matches_replatform_normalization(name: str) -> None:
    assert natural_key_segment(name) == _normalize(name)


@pytest.mark.parametrize(
    "raw",
    [
        "Plain String",
        {"value": "abc123", "display_value": "Display Label"},
        None,
        True,
        False,
        0,
        100,
        2.5,
    ],
)
def test_field_display_matches_replatform_display_name(raw: SnFieldValue) -> None:
    assert field_display(raw) == _display_name(raw)
