# tests/test_replatform_classifier.py
# Tests for the deterministic replatform classifier (Story 02).
# Author: Pierre Grothe
# Date: 2026-06-29

"""Behavioral tests for nexus.replatform.classifier.classify."""

from datetime import UTC, datetime

from nexus.replatform.classifier import classify
from nexus.replatform.models import UseCaseInventory
from tests.fakes.captures import make_capture_result, make_config_record
from tests.fakes.replatform import make_schema_catalog, make_scope_manifest

_TS = datetime(2026, 6, 29, 12, 0, 0, tzinfo=UTC)


def test_classify_maps_catalog_scope_to_product_domain() -> None:
    scopes = make_scope_manifest(scopes={"s1": "sn_hamp"}, captured_at=_TS)
    catalog = make_schema_catalog(scope_to_product={"sn_hamp": "Hardware Asset Management"})
    capture = make_capture_result(
        records=(
            make_config_record(
                sys_id="r1",
                table="sys_hub_flow",
                scope_sys_id="s1",
                scope_name="HAM",
                fields={"name": "Create Incident"},
            ),
        ),
    )
    inv = classify((capture,), scopes, catalog, profile="prod")
    assert isinstance(inv, UseCaseInventory)
    assert inv.profile == "prod"
    assert inv.captured_at == _TS
    assert inv.coverage == ("ai_automation",)
    assert len(inv.use_cases) == 1
    uc = inv.use_cases[0]
    assert uc.domain == "Hardware Asset Management"
    assert uc.evidence == ("sn_hamp",)
    assert uc.workflows[0].key == "sn_hamp|sys_hub_flow|create incident"
    assert uc.workflows[0].name == "Create Incident"
    assert uc.workflows[0].type == "sys_hub_flow"


def test_classify_names_custom_scope_domain_after_app_display_name() -> None:
    scopes = make_scope_manifest(
        scopes={"s1": "x_acme_app"}, names={"s1": "Acme Field Service"}, captured_at=_TS
    )
    catalog = make_schema_catalog(scope_to_product={})
    capture = make_capture_result(
        records=(
            make_config_record(
                sys_id="r1",
                table="ai_skill",
                scope_sys_id="s1",
                scope_name="Acme",
                fields={"name": "Greeting"},
            ),
        ),
    )
    inv = classify((capture,), scopes, catalog, profile="prod")
    assert len(inv.use_cases) == 1
    assert inv.use_cases[0].domain == "Acme Field Service"
    assert inv.use_cases[0].workflows[0].key == "x_acme_app|ai_skill|greeting"


def test_classify_catalog_domain_wins_over_app_display_name() -> None:
    scopes = make_scope_manifest(
        scopes={"s1": "sn_hamp"}, names={"s1": "HAM Store App"}, captured_at=_TS
    )
    catalog = make_schema_catalog(scope_to_product={"sn_hamp": "Hardware Asset Management"})
    capture = make_capture_result(
        records=(
            make_config_record(
                sys_id="r1", table="sys_hub_flow", scope_sys_id="s1", fields={"name": "A"}
            ),
        ),
    )
    inv = classify((capture,), scopes, catalog, profile="prod")
    assert inv.use_cases[0].domain == "Hardware Asset Management"


def test_classify_buckets_unresolvable_scope_as_uncategorized() -> None:
    scopes = make_scope_manifest(scopes={}, captured_at=_TS)
    catalog = make_schema_catalog(scope_to_product={})
    capture = make_capture_result(
        records=(
            make_config_record(
                sys_id="r1",
                table="ai_skill",
                scope_sys_id="ghost",
                scope_name="",
                fields={"name": "Greeting"},
            ),
        ),
    )
    inv = classify((capture,), scopes, catalog, profile="prod")
    assert inv.use_cases[0].domain == "Uncategorized"


def test_classify_extracts_display_value_from_reference_field() -> None:
    scopes = make_scope_manifest(scopes={"s1": "x_acme_app"}, captured_at=_TS)
    catalog = make_schema_catalog(scope_to_product={})
    capture = make_capture_result(
        records=(
            make_config_record(
                sys_id="r1",
                table="sys_hub_flow",
                scope_sys_id="s1",
                fields={"name": {"value": "abc123", "display_value": "Onboard Employee"}},
            ),
        ),
    )
    inv = classify((capture,), scopes, catalog, profile="prod")
    wf = inv.use_cases[0].workflows[0]
    assert wf.name == "Onboard Employee"
    assert wf.key == "x_acme_app|sys_hub_flow|onboard employee"


def test_classify_normalizes_key_case_and_whitespace() -> None:
    scopes = make_scope_manifest(scopes={"s1": "x_acme_app"}, captured_at=_TS)
    catalog = make_schema_catalog(scope_to_product={})
    capture = make_capture_result(
        records=(
            make_config_record(
                sys_id="r1",
                table="sys_hub_flow",
                scope_sys_id="s1",
                fields={"name": "  Create   Incident  "},
            ),
        ),
    )
    inv = classify((capture,), scopes, catalog, profile="prod")
    assert inv.use_cases[0].workflows[0].key == "x_acme_app|sys_hub_flow|create incident"


def test_classify_merges_multiple_scopes_into_one_domain() -> None:
    scopes = make_scope_manifest(scopes={"s1": "sn_a", "s2": "sn_b"}, captured_at=_TS)
    catalog = make_schema_catalog(scope_to_product={"sn_a": "ITSM", "sn_b": "ITSM"})
    capture = make_capture_result(
        records=(
            make_config_record(
                sys_id="r1", table="sys_hub_flow", scope_sys_id="s1", fields={"name": "A"}
            ),
            make_config_record(
                sys_id="r2", table="ai_skill", scope_sys_id="s2", fields={"name": "B"}
            ),
        ),
    )
    inv = classify((capture,), scopes, catalog, profile="prod")
    assert len(inv.use_cases) == 1
    uc = inv.use_cases[0]
    assert uc.domain == "ITSM"
    assert len(uc.workflows) == 2
    assert uc.evidence == ("sn_a", "sn_b")


def test_classify_empty_captures_returns_no_use_cases() -> None:
    scopes = make_scope_manifest(scopes={}, captured_at=_TS)
    catalog = make_schema_catalog(scope_to_product={})
    inv = classify((), scopes, catalog, profile="prod")
    assert inv.use_cases == ()
    assert inv.coverage == ()
    assert inv.profile == "prod"
    assert inv.captured_at == _TS


def test_classify_unnamed_records_get_distinct_keys() -> None:
    scopes = make_scope_manifest(scopes={"s1": "x_app"}, captured_at=_TS)
    catalog = make_schema_catalog(scope_to_product={})
    capture = make_capture_result(
        records=(
            make_config_record(sys_id="r1", table="sys_hub_flow", scope_sys_id="s1", fields={}),
            make_config_record(sys_id="r2", table="sys_hub_flow", scope_sys_id="s1", fields={}),
        ),
    )
    inv = classify((capture,), scopes, catalog, profile="prod")
    keys = {wf.key for uc in inv.use_cases for wf in uc.workflows}
    assert len(keys) == 2


def test_classify_falls_back_to_scope_name_when_sys_id_unknown() -> None:
    scopes = make_scope_manifest(scopes={}, captured_at=_TS)
    catalog = make_schema_catalog(scope_to_product={})
    capture = make_capture_result(
        records=(
            make_config_record(
                sys_id="r1",
                table="sys_hub_flow",
                scope_sys_id="unknown",
                scope_name="x_fallback",
                fields={"name": "X"},
            ),
        ),
    )
    inv = classify((capture,), scopes, catalog, profile="prod")
    wf = inv.use_cases[0].workflows[0]
    assert wf.scope == "x_fallback"
    assert wf.key == "x_fallback|sys_hub_flow|x"


def test_classify_records_skipped_tables_sorted() -> None:
    scopes = make_scope_manifest(scopes={"s1": "x_acme_app"}, captured_at=_TS)
    catalog = make_schema_catalog(scope_to_product={})
    capture = make_capture_result(records=())
    inv = classify(
        (capture,), scopes, catalog, profile="prod", skipped_tables=("sys_ai_agent", "ai_skill")
    )
    assert inv.skipped_tables == ("ai_skill", "sys_ai_agent")


def test_classify_domain_map_overrides_catalog() -> None:
    scopes = make_scope_manifest(scopes={"s1": "sn_hamp"}, captured_at=_TS)
    catalog = make_schema_catalog(scope_to_product={"sn_hamp": "Hardware Asset Management"})
    capture = make_capture_result(
        records=(
            make_config_record(
                sys_id="r1", table="sys_hub_flow", scope_sys_id="s1", fields={"name": "A"}
            ),
        ),
    )
    inv = classify((capture,), scopes, catalog, profile="prod", overrides={"sn_hamp": "Asset Ops"})
    assert inv.use_cases[0].domain == "Asset Ops"


def test_classify_groups_global_scope_under_its_display_name() -> None:
    scopes = make_scope_manifest(scopes={"g1": "global"}, names={"g1": "Global"}, captured_at=_TS)
    catalog = make_schema_catalog(scope_to_product={})
    capture = make_capture_result(
        records=(
            make_config_record(
                sys_id="r1",
                table="sys_script",
                scope_sys_id="g1",
                fields={"name": "Incident autoclose"},
            ),
        ),
    )
    inv = classify((capture,), scopes, catalog, profile="prod")
    assert inv.use_cases[0].domain == "Global"
    assert inv.use_cases[0].workflows[0].key == "global|sys_script|incident autoclose"
