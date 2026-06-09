# tests/schema/test_table_enricher.py
# Tests for TableEnricher against fakes.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Enricher turns a SchemaGraph + AI JSON into a MindmapCatalog."""

from datetime import UTC, datetime

import pytest

from nexus.api.errors import AnthropicError
from nexus.schema.enricher import TableEnricher
from nexus.schema.models import FieldDef, SchemaGraph, TableDef
from tests.fakes.fake_agent_client import FakeAgentClient
from tests.fakes.fake_sn_client import FakeServiceNowClient

_AI_JSON = (
    '{"sections":[{"name":"Planning","domains":[{"name":"Plan Management","tables":'
    '[{"table":"sn_bcp_plan","description":"Stores BC plans."}]}]}]}'
)


def _graph() -> SchemaGraph:
    return SchemaGraph(
        instance_id="alectri",
        area_key="bcm",
        discovered_at=datetime(2026, 6, 8, tzinfo=UTC),
        scope_keys=("sn_bcp",),
        tables=(
            TableDef(
                name="sn_bcp_plan",
                label="Plan",
                scope="sn_bcp",
                fields=(
                    FieldDef(
                        name="plan_owner",
                        label="Plan owner",
                        type="reference",
                        reference_target="sys_user",
                    ),
                ),
            ),
        ),
        reference_edges=(),
        inheritance_edges=(),
        relationship_edges=(),
    )


def _enricher(sn: FakeServiceNowClient, ai: FakeAgentClient) -> TableEnricher:
    return TableEnricher(sn, ai, clock=lambda: datetime(2026, 6, 8, tzinfo=UTC))


@pytest.mark.asyncio
async def test_enrich_builds_catalog_from_ai_json() -> None:
    enricher = _enricher(FakeServiceNowClient(), FakeAgentClient(canned_response=_AI_JSON))
    catalog = await enricher.enrich(_graph(), display="BCM")
    assert catalog.sections[0].name == "Planning"
    assert catalog.sections[0].domains[0].name == "Plan Management"
    assert catalog.sections[0].domains[0].tables[0].description == "Stores BC plans."


@pytest.mark.asyncio
async def test_enrich_joins_ai_description_to_discovered_label() -> None:
    enricher = _enricher(FakeServiceNowClient(), FakeAgentClient(canned_response=_AI_JSON))
    catalog = await enricher.enrich(_graph(), display="BCM")
    assert catalog.sections[0].domains[0].tables[0].label == "Plan"  # from the graph, not the AI


@pytest.mark.asyncio
async def test_enrich_includes_sys_documentation_hints_in_prompt() -> None:
    sn = FakeServiceNowClient(
        {
            "sys_documentation": [
                {
                    "name": "sn_bcp_plan",
                    "element": "plan_owner",
                    "hint": "The accountable plan owner.",
                }
            ]
        }
    )
    ai = FakeAgentClient(canned_response=_AI_JSON)
    await _enricher(sn, ai).enrich(_graph(), display="BCM")
    assert "The accountable plan owner." in str(ai.calls[0]["prompt"])


@pytest.mark.asyncio
async def test_enrich_falls_back_to_scope_grouping_on_ai_error() -> None:
    ai = FakeAgentClient(side_effect=AnthropicError(0, "boom"))
    catalog = await _enricher(FakeServiceNowClient(), ai).enrich(_graph(), display="BCM")
    assert catalog.sections[0].name == "BCM"  # single fallback section named after the area
    assert catalog.sections[0].domains[0].name == "sn_bcp"
    assert catalog.sections[0].domains[0].tables[0].description == "Plan"  # label fallback


@pytest.mark.asyncio
async def test_enrich_falls_back_on_unparseable_json() -> None:
    ai = FakeAgentClient(canned_response="sorry, no JSON here")
    catalog = await _enricher(FakeServiceNowClient(), ai).enrich(_graph(), display="BCM")
    assert catalog.sections[0].domains[0].name == "sn_bcp"


@pytest.mark.asyncio
async def test_enrich_falls_back_on_valid_json_with_wrong_shape() -> None:
    ai = FakeAgentClient(canned_response='{"foo": 1}')  # valid JSON, no "sections" key
    catalog = await _enricher(FakeServiceNowClient(), ai).enrich(_graph(), display="BCM")
    assert catalog.sections[0].domains[0].name == "sn_bcp"


@pytest.mark.asyncio
async def test_enrich_flattens_three_level_nesting_from_ai() -> None:
    # The model sometimes nests domains-within-domains; the parser flattens it.
    nested = (
        '{"sections":[{"name":"Core","domains":['
        '{"name":"Element Modeling","domains":['
        '{"name":"Elements","tables":[{"table":"sn_bcp_plan","description":"Stores plans."}]}'
        "]}]}]}"
    )
    ai = FakeAgentClient(canned_response=nested)
    catalog = await _enricher(FakeServiceNowClient(), ai).enrich(_graph(), display="BCM")
    assert catalog.sections[0].name == "Core"
    assert catalog.sections[0].domains[0].name == "Elements"  # nested domain flattened up
    assert catalog.sections[0].domains[0].tables[0].table == "sn_bcp_plan"


@pytest.mark.asyncio
async def test_enrich_skips_malformed_entries_and_keeps_good_ones() -> None:
    mixed = (
        '{"sections":['
        '"not a dict",'  # non-dict section -> skipped
        '{"name":"S1","domains":['
        '"not a dict",'  # non-dict domain -> dropped
        '{"name":"D0"},'  # no tables / no domains -> dropped
        '{"name":"D1","tables":"not a list"},'  # tables not a list -> dropped
        '{"name":"D3","domains":"nope"},'  # nested domains not a list -> dropped
        '{"name":"D2","tables":[{"table":"sn_bcp_plan","description":"ok"},{"table":"x"}]}'
        "]},"
        '{"name":"S2","tables":[{"table":"sn_bcp_plan","description":"sec-level"}]}'  # section tables
        "]}"
    )
    ai = FakeAgentClient(canned_response=mixed)
    catalog = await _enricher(FakeServiceNowClient(), ai).enrich(_graph(), display="BCM")
    names = [s.name for s in catalog.sections]
    assert names == ["S1", "S2"]
    s1_domains = [d.name for d in catalog.sections[0].domains]
    assert s1_domains == ["D2"]  # only the valid domain survives
    assert [t.table for t in catalog.sections[0].domains[0].tables] == [
        "sn_bcp_plan"
    ]  # "x" dropped
    assert catalog.sections[1].domains[0].tables[0].description == "sec-level"


@pytest.mark.asyncio
async def test_enrich_wraps_legacy_flat_domains_shape() -> None:
    # Older flat {"domains":[...]} shape (no "sections") is wrapped in one section
    # named after the area; a non-dict table entry is skipped.
    flat = (
        '{"domains":[{"name":"Plans","tables":['
        '"junk",'
        '{"table":"sn_bcp_plan","description":"Stores plans."}]}]}'
    )
    ai = FakeAgentClient(canned_response=flat)
    catalog = await _enricher(FakeServiceNowClient(), ai).enrich(_graph(), display="BCM")
    assert catalog.sections[0].name == "BCM"  # wrapped under the display name
    assert catalog.sections[0].domains[0].name == "Plans"
    assert catalog.sections[0].domains[0].tables[0].table == "sn_bcp_plan"
