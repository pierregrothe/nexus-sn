# tests/capture/test_models.py
# Tests for capture layer data models.
# Author: Pierre Grothe
# Date: 2026-05-09

from datetime import UTC, datetime
from pathlib import Path

from nexus.capture.models import (
    ArchiveManifest,
    CaptureResult,
    ConfigRecord,
    ScopeEntry,
    ScopeManifest,
    SnRefField,
    UpdateSetRef,
)
from nexus.capture.tables import (
    AI_AUTOMATION,
    DEFAULT_TABLE_GROUPS,
)

NOW = datetime.now(UTC)


def test_scope_entry_constructs_with_table_counts() -> None:
    entry = ScopeEntry(
        sys_id="scope001",
        name="NowAssist HRSD",
        scope="x_snc_nowassist_hrsd",
        version="1.0.0",
        vendor="ServiceNow",
        table_counts={"ai_skill": 3, "sys_hub_flow": 8},
    )
    assert entry.table_counts["ai_skill"] == 3


def test_scope_manifest_contains_entries() -> None:
    entry = ScopeEntry(
        sys_id="s1",
        name="App",
        scope="x_app",
        version="1",
        vendor="SN",
        table_counts={},
    )
    manifest = ScopeManifest(instance_id="dev", captured_at=NOW, scopes=(entry,))
    assert len(manifest.scopes) == 1


def test_config_record_plain_string_field() -> None:
    record = ConfigRecord(
        sys_id="r1",
        table="ai_skill",
        scope_sys_id="s1",
        scope_name="x_app",
        captured_at=NOW,
        fields={"name": "My Skill", "active": "true"},
        parent_sys_id=None,
    )
    assert record.fields["name"] == "My Skill"


def test_config_record_ref_field() -> None:
    ref: SnRefField = {"value": "sys_id_abc", "display_value": "Global"}
    record = ConfigRecord(
        sys_id="r1",
        table="ai_skill",
        scope_sys_id="s1",
        scope_name="x_app",
        captured_at=NOW,
        fields={"sys_scope": ref},
        parent_sys_id=None,
    )
    assert record.fields["sys_scope"] == ref


def test_capture_result_by_table_groups_correctly() -> None:
    r1 = ConfigRecord(
        sys_id="r1",
        table="ai_skill",
        scope_sys_id="s1",
        scope_name="x",
        captured_at=NOW,
        fields={},
        parent_sys_id=None,
    )
    r2 = ConfigRecord(
        sys_id="r2",
        table="sys_hub_flow",
        scope_sys_id="s1",
        scope_name="x",
        captured_at=NOW,
        fields={},
        parent_sys_id=None,
    )
    r3 = ConfigRecord(
        sys_id="r3",
        table="ai_skill",
        scope_sys_id="s1",
        scope_name="x",
        captured_at=NOW,
        fields={},
        parent_sys_id=None,
    )
    result = CaptureResult(
        instance_id="dev",
        captured_at=NOW,
        scope_ids=("s1",),
        table_group="ai_automation",
        records=(r1, r2, r3),
    )
    by_table = result.by_table()
    assert len(by_table["ai_skill"]) == 2
    assert len(by_table["sys_hub_flow"]) == 1


def test_ai_automation_group_contains_expected_tables() -> None:
    names = {spec.name for spec in AI_AUTOMATION.tables}
    assert "ai_skill" in names
    assert "sys_hub_flow" in names
    assert "sys_hub_action_type_definition" in names


def test_table_spec_related_table_has_join_field() -> None:
    flow_spec = next(s for s in AI_AUTOMATION.tables if s.name == "sys_hub_flow")
    assert any(r.join_field == "flow" for r in flow_spec.related)


def test_default_table_groups_contains_ai_automation() -> None:
    assert "ai_automation" in DEFAULT_TABLE_GROUPS


def test_archive_manifest_constructs() -> None:
    m = ArchiveManifest(
        format_version="1.0",
        instance_id="dev",
        captured_at=NOW,
        scope_ids=("s1",),
        table_group="ai_automation",
        record_count=5,
        archive_dir=Path("/tmp"),
    )
    assert m.record_count == 5


def test_update_set_ref_constructs() -> None:
    ref = UpdateSetRef(
        sys_id="u1",
        name="NEXUS-Capture",
        state="in progress",
        record_count=3,
        instance_id="dev",
    )
    assert ref.state == "in progress"
