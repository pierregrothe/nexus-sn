# tests/test_instances_scanner.py
# Tests for InstanceScanner async REST collection.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for nexus.instances.scanner."""

from datetime import UTC

import httpx
import pytest

from nexus.instances.errors import SnapshotError
from nexus.instances.scanner import InstanceScanner, _is_custom, _parse_dt, _to_record


def _sn_response(records: list[dict[str, object]]) -> dict[str, object]:
    return {"result": records}


def _record(
    sys_id: str = "abc",
    name: str = "Test",
    created_by: str = "admin",
    scope_value: str = "x_custom",
    sys_updated_on: str = "2026-05-01 10:00:00",
) -> dict[str, object]:
    return {
        "sys_id": sys_id,
        "name": name,
        "active": True,
        "sys_updated_on": sys_updated_on,
        "sys_created_by": created_by,
        "sys_scope": {"value": scope_value, "display_value": scope_value},
        "skill_type": "now_assist",
        "accessible_from": "package_private",
        "table_name": "incident",
        "when": "before",
        "api_name": "global.MyScript",
        "client_callable": False,
    }


class FakeAsyncTransport(httpx.AsyncBaseTransport):
    """Returns canned responses keyed by URL path."""

    def __init__(self, responses: dict[str, tuple[int, dict[str, object]]]) -> None:
        self._responses = responses

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        status, body = self._responses.get(path, (404, {"error": "not found"}))
        return httpx.Response(status, json=body)


def _all_ok(
    ai_skills: list[dict[str, object]] | None = None,
    flows: list[dict[str, object]] | None = None,
    brs: list[dict[str, object]] | None = None,
    sis: list[dict[str, object]] | None = None,
) -> dict[str, tuple[int, dict[str, object]]]:
    return {
        "/api/now/table/ai_skill": (200, _sn_response(ai_skills or [])),
        "/api/now/table/sys_hub_flow": (200, _sn_response(flows or [])),
        "/api/now/table/sys_script": (200, _sn_response(brs or [])),
        "/api/now/table/sys_script_include": (200, _sn_response(sis or [])),
    }


async def test_instance_scanner_scan_returns_snapshot_with_correct_version() -> None:
    scanner = InstanceScanner(transport=FakeAsyncTransport(_all_ok()))
    snapshot = await scanner.scan("https://dev12345.service-now.com", "tok", "Xanadu")
    assert snapshot.sn_version == "Xanadu"


async def test_instance_scanner_scan_populates_ai_skills() -> None:
    scanner = InstanceScanner(
        transport=FakeAsyncTransport(_all_ok(ai_skills=[_record("s1", "My Skill")]))
    )
    snapshot = await scanner.scan("https://dev12345.service-now.com", "tok", "Xanadu")
    assert len(snapshot.ai_skills) == 1
    assert snapshot.ai_skills[0].name == "My Skill"
    assert snapshot.ai_skills[0].is_custom is True


async def test_instance_scanner_scan_raises_snapshot_error_on_403() -> None:
    responses = _all_ok()
    responses["/api/now/table/ai_skill"] = (403, {"error": "forbidden"})
    scanner = InstanceScanner(transport=FakeAsyncTransport(responses))
    with pytest.raises(SnapshotError) as exc_info:
        await scanner.scan("https://dev12345.service-now.com", "tok", "Xanadu")
    assert exc_info.value.status_code == 403


def test_is_custom_returns_false_for_system_global_record() -> None:
    row: dict[str, object] = {"sys_created_by": "system", "sys_scope": {"value": "global"}}
    assert _is_custom(row) is False


def test_is_custom_returns_true_for_custom_scoped_record() -> None:
    row: dict[str, object] = {"sys_created_by": "admin", "sys_scope": {"value": "x_custom_app"}}
    assert _is_custom(row) is True


def test_is_custom_returns_false_when_created_by_system_even_in_custom_scope() -> None:
    row: dict[str, object] = {"sys_created_by": "system", "sys_scope": {"value": "x_custom"}}
    assert _is_custom(row) is False


def test_is_custom_with_none_scope_falls_back_to_global() -> None:
    # scope is None -> str(None or "global") => "global" -> not custom
    row: dict[str, object] = {"sys_created_by": "admin", "sys_scope": None}
    assert _is_custom(row) is False


def test_is_custom_with_string_scope_uses_string_value() -> None:
    # non-dict scope string is used directly
    row: dict[str, object] = {"sys_created_by": "admin", "sys_scope": "x_sn_something"}
    assert _is_custom(row) is True


def test_parse_dt_returns_fallback_for_invalid_string() -> None:
    result = _parse_dt("not-a-date")
    assert result.tzinfo is not None
    offset = result.utcoffset()
    assert offset is not None
    assert offset.total_seconds() == 0


async def test_instance_scanner_scan_with_invalid_updated_on_uses_fallback() -> None:
    bad_record = _record("s1", "Bad Skill", sys_updated_on="not-a-date")
    scanner = InstanceScanner(transport=FakeAsyncTransport(_all_ok(ai_skills=[bad_record])))
    snapshot = await scanner.scan("https://dev12345.service-now.com", "tok", "Xanadu")
    assert len(snapshot.ai_skills) == 1
    assert snapshot.ai_skills[0].sys_id == "s1"


def test_to_record_skips_none_extra_fields() -> None:
    # skill_type intentionally omitted -> not included in extra
    row: dict[str, object] = {
        "sys_id": "x1",
        "name": "NullExtra",
        "active": True,
        "sys_updated_on": "2026-05-01 10:00:00",
        "sys_created_by": "admin",
        "sys_scope": {"value": "x_custom"},
    }
    record = _to_record(row, ["skill_type"])
    assert "skill_type" not in record.extra


async def test_instance_scanner_scan_populates_all_four_artifact_lists() -> None:
    scanner = InstanceScanner(
        transport=FakeAsyncTransport(
            _all_ok(
                ai_skills=[_record("s1", "Skill")],
                flows=[_record("f1", "Flow")],
                brs=[_record("b1", "BR")],
                sis=[_record("i1", "SI")],
            )
        )
    )
    snapshot = await scanner.scan("https://dev12345.service-now.com", "tok", "Xanadu")
    assert len(snapshot.ai_skills) == 1
    assert len(snapshot.flows) == 1
    assert len(snapshot.business_rules) == 1
    assert len(snapshot.script_includes) == 1


def test_parse_dt_returns_utc_for_valid_string() -> None:
    result = _parse_dt("2026-05-01 10:00:00")
    assert result.tzinfo == UTC
    assert result.year == 2026
    assert result.month == 5
    assert result.day == 1
