# tests/test_plugins_impact.py
# Tests for the plugin impact analysis layer.
# Author: Pierre Grothe
# Date: 2026-05-12
"""Tests for src/nexus/plugins/impact.py and PluginImpactError."""

import asyncio
from datetime import UTC, datetime

import httpx
import pytest

import nexus.plugins as plugins_pkg
from nexus.plugins.errors import PluginImpactError
from nexus.plugins.impact import (
    ScopeRecordCountError,
    compute_impact,
    fetch_cross_scope_refs,
    fetch_scope_counts_with_client,
    fetch_scope_record_counts,
    reverse_dependencies,
)
from nexus.plugins.models import CrossScopeRef, PluginImpact, PluginInfo, PluginInventory, ScopeRecordCount

__all__: list[str] = []


def test_plugin_impact_error_carries_plugin_id() -> None:
    err = PluginImpactError("com.unknown")
    assert err.plugin_id == "com.unknown"
    assert "com.unknown" in str(err)


def test_plugin_impact_error_is_exception_subclass() -> None:
    assert issubclass(PluginImpactError, Exception)


def _plugin(
    plugin_id: str,
    *,
    depends_on: tuple[str, ...] = (),
    state: str = "active",
) -> PluginInfo:
    return PluginInfo.model_validate(
        {
            "plugin_id": plugin_id,
            "name": plugin_id,
            "version": "1.0",
            "state": state,
            "source": "store",
            "product_family": "Uncategorized",
            "depends_on": depends_on,
            "sys_id": f"sys-{plugin_id}",
            "installed_at": None,
        }
    )


def _inventory(*plugins: PluginInfo) -> PluginInventory:
    return PluginInventory(
        captured_at=datetime(2026, 5, 12, tzinfo=UTC),
        sn_version="Washington",
        plugins=plugins,
    )


def test_reverse_dependencies_returns_empty_when_no_dependents() -> None:
    inv = _inventory(
        _plugin("com.target"),
        _plugin("com.unrelated", depends_on=("com.other",)),
    )
    assert reverse_dependencies(inv, "com.target") == ()


def test_reverse_dependencies_finds_direct_dependents_at_depth_1() -> None:
    inv = _inventory(
        _plugin("com.target"),
        _plugin("com.dependent", depends_on=("com.target",)),
    )
    deps = reverse_dependencies(inv, "com.target")
    assert len(deps) == 1
    assert deps[0].plugin_id == "com.dependent"
    assert deps[0].depth == 1


def test_reverse_dependencies_traverses_transitively() -> None:
    inv = _inventory(
        _plugin("com.target"),
        _plugin("com.mid", depends_on=("com.target",)),
        _plugin("com.outer", depends_on=("com.mid",)),
    )
    deps = reverse_dependencies(inv, "com.target")
    ids_by_depth = {d.plugin_id: d.depth for d in deps}
    assert ids_by_depth == {"com.mid": 1, "com.outer": 2}


def test_reverse_dependencies_sets_via_chain_inclusive_of_endpoints() -> None:
    inv = _inventory(
        _plugin("com.target"),
        _plugin("com.mid", depends_on=("com.target",)),
        _plugin("com.outer", depends_on=("com.mid",)),
    )
    deps = reverse_dependencies(inv, "com.target")
    outer = next(d for d in deps if d.plugin_id == "com.outer")
    assert outer.via == ("com.outer", "com.mid", "com.target")


def test_reverse_dependencies_handles_cycles_without_infinite_loop() -> None:
    inv = _inventory(
        _plugin("com.target", depends_on=("com.cycle",)),
        _plugin("com.cycle", depends_on=("com.target",)),
    )
    deps = reverse_dependencies(inv, "com.target")
    assert len(deps) == 1
    assert deps[0].plugin_id == "com.cycle"


def test_reverse_dependencies_handles_self_dependency_without_loop() -> None:
    inv = _inventory(
        _plugin("com.target", depends_on=("com.target",)),
    )
    assert reverse_dependencies(inv, "com.target") == ()


def test_reverse_dependencies_sorts_by_depth_then_plugin_id() -> None:
    inv = _inventory(
        _plugin("com.target"),
        _plugin("com.b", depends_on=("com.target",)),
        _plugin("com.a", depends_on=("com.target",)),
        _plugin("com.deep", depends_on=("com.a",)),
    )
    deps = reverse_dependencies(inv, "com.target")
    order = [(d.depth, d.plugin_id) for d in deps]
    assert order == sorted(order)


def test_reverse_dependencies_raises_when_target_not_in_inventory() -> None:
    inv = _inventory(_plugin("com.other"))
    with pytest.raises(PluginImpactError):
        reverse_dependencies(inv, "com.target")


def _stats_response(rows: list[dict[str, object]]) -> dict[str, object]:
    return {"result": rows}


def _row(table: str, count: int) -> dict[str, object]:
    return {
        "stats": {"count": str(count)},
        "groupby_fields": [{"field": "sys_class_name", "value": table}],
    }


def _stats_transport(
    status: int = 200,
    payload: dict[str, object] | None = None,
) -> httpx.MockTransport:
    body: dict[str, object] = payload if payload is not None else {"result": []}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handler)


def _fetch(transport: httpx.MockTransport) -> tuple[ScopeRecordCount, ...]:
    return asyncio.run(
        fetch_scope_record_counts(
            "https://x.example",
            "tok",
            "com.target",
            transport=transport,
        )
    )


def test_fetch_scope_record_counts_parses_aggregate_response() -> None:
    transport = _stats_transport(
        payload=_stats_response([_row("sys_script", 8012)]),
    )
    counts = _fetch(transport)
    assert len(counts) == 1
    assert counts[0].table == "sys_script"
    assert counts[0].count == 8012


def test_fetch_scope_record_counts_returns_empty_tuple_when_result_empty() -> None:
    transport = _stats_transport(payload=_stats_response([]))
    assert _fetch(transport) == ()


def test_fetch_scope_record_counts_sorts_by_count_desc_then_table_asc() -> None:
    transport = _stats_transport(
        payload=_stats_response(
            [
                _row("sys_business_rule", 100),
                _row("sys_script", 500),
                _row("sys_ui_action", 500),
            ]
        ),
    )
    counts = _fetch(transport)
    assert [(c.table, c.count) for c in counts] == [
        ("sys_script", 500),
        ("sys_ui_action", 500),
        ("sys_business_rule", 100),
    ]


def test_fetch_scope_record_counts_raises_on_non_200() -> None:
    transport = _stats_transport(status=403)
    with pytest.raises(ScopeRecordCountError):
        _fetch(transport)


def test_fetch_scope_record_counts_raises_on_malformed_response() -> None:
    transport = _stats_transport(payload={"no_result_key": True})
    with pytest.raises(ScopeRecordCountError):
        _fetch(transport)


def test_compute_impact_aggregates_reverse_deps_and_counts() -> None:
    inv = _inventory(
        _plugin("com.target"),
        _plugin("com.dependent", depends_on=("com.target",)),
    )
    transport = _stats_transport(
        payload=_stats_response([_row("sys_script", 42)]),
    )
    result = asyncio.run(
        compute_impact(
            inv,
            "com.target",
            url="https://x.example",
            token="tok",
            transport=transport,
        )
    )
    assert isinstance(result, PluginImpact)
    assert result.counts_available is True
    assert result.target_plugin_id == "com.target"
    assert len(result.reverse_deps) == 1
    assert len(result.record_counts) == 1
    assert result.record_counts[0].count == 42


def test_compute_impact_marks_counts_unavailable_when_fetch_fails() -> None:
    inv = _inventory(
        _plugin("com.target"),
        _plugin("com.dependent", depends_on=("com.target",)),
    )
    transport = _stats_transport(status=500)
    result = asyncio.run(
        compute_impact(
            inv,
            "com.target",
            url="https://x.example",
            token="tok",
            transport=transport,
        )
    )
    assert result.counts_available is False
    assert result.record_counts == ()
    assert len(result.reverse_deps) == 1


def test_compute_impact_propagates_plugin_not_found() -> None:
    inv = _inventory(_plugin("com.other"))
    transport = _stats_transport()
    with pytest.raises(PluginImpactError):
        asyncio.run(
            compute_impact(
                inv,
                "com.target",
                url="https://x.example",
                token="tok",
                transport=transport,
            )
        )


def test_public_api_reexports_impact_symbols() -> None:
    expected = {
        "PluginImpact",
        "PluginImpactError",
        "ReverseDependency",
        "ScopeRecordCount",
        "compute_impact",
        "reverse_dependencies",
    }
    assert expected.issubset(set(plugins_pkg.__all__))
    for name in expected:
        assert hasattr(plugins_pkg, name), f"missing re-export: {name}"


async def _direct(transport: httpx.MockTransport) -> tuple[ScopeRecordCount, ...]:
    async with httpx.AsyncClient(
        base_url="https://x.example",
        headers={"Authorization": "Bearer t"},
        transport=transport,
    ) as client:
        return await fetch_scope_counts_with_client(client, "com.x")


def test_fetch_scope_counts_with_client_returns_typed_buckets() -> None:
    transport = _stats_transport(
        payload=_stats_response([_row("sys_script", 7)]),
    )
    buckets = asyncio.run(_direct(transport))
    assert len(buckets) == 1
    assert buckets[0].table == "sys_script"
    assert buckets[0].count == 7


def _inventory_with_target(
    plugin_id: str,
    *,
    record_count: int | None,
) -> PluginInventory:
    return _inventory(_plugin(plugin_id).model_copy(update={"record_count": record_count}))


def test_compute_impact_serves_empty_tuple_when_record_counts_is_empty() -> None:
    """record_counts=() means scope owns zero records -- serve cache, no stats/sys_metadata call."""
    stats_calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if "/api/now/stats/sys_metadata" in req.url.path:
            stats_calls.append(str(req.url))
        return httpx.Response(200, json={"result": []})

    transport = httpx.MockTransport(handler)

    target = _plugin("com.target").model_copy(update={"record_counts": ()})
    inv = _inventory(target)

    result = asyncio.run(
        compute_impact(
            inv,
            "com.target",
            url="https://x.example",
            token="t",
            transport=transport,
        )
    )

    assert stats_calls == []
    assert result.record_counts == ()
    assert result.counts_available is True


def test_compute_impact_calls_live_when_cached_record_count_is_positive() -> None:
    """Cached > 0 -> live call still made to get per-table breakdown."""
    stats_calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if "/api/now/stats/sys_metadata" in req.url.path:
            stats_calls.append(str(req.url))
            return httpx.Response(
                200,
                json={
                    "result": [
                        {
                            "stats": {"count": "5"},
                            "groupby_fields": [{"field": "sys_class_name", "value": "sys_script"}],
                        }
                    ]
                },
            )
        return httpx.Response(404, json={"result": []})

    transport = httpx.MockTransport(handler)
    inv = _inventory_with_target("com.target", record_count=42)
    result = asyncio.run(
        compute_impact(
            inv,
            "com.target",
            url="https://x.example",
            token="t",
            transport=transport,
        )
    )
    assert len(stats_calls) == 1
    assert result.counts_available is True
    assert len(result.record_counts) == 1


def test_compute_impact_calls_live_when_cached_record_count_is_none() -> None:
    """Cached None (no data) -> live call as before."""
    stats_calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if "/api/now/stats/sys_metadata" in req.url.path:
            stats_calls.append(str(req.url))
            return httpx.Response(200, json={"result": []})
        return httpx.Response(404, json={"result": []})

    transport = httpx.MockTransport(handler)
    inv = _inventory_with_target("com.target", record_count=None)
    result = asyncio.run(
        compute_impact(
            inv,
            "com.target",
            url="https://x.example",
            token="t",
            transport=transport,
        )
    )
    assert len(stats_calls) == 1
    assert result.counts_available is True


def test_compute_impact_serves_from_cache_when_record_counts_populated() -> None:
    """Cached record_counts -> no stats/sys_metadata call, returned directly with counts_available=True."""
    stats_calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if "/api/now/stats/sys_metadata" in req.url.path:
            stats_calls.append(str(req.url))
        return httpx.Response(200, json={"result": []})

    transport = httpx.MockTransport(handler)

    cached = (
        ScopeRecordCount(table="sys_script", count=100),
        ScopeRecordCount(table="sys_business_rule", count=25),
    )
    target = _plugin("com.target").model_copy(update={"record_counts": cached})
    inv = _inventory(target)

    result = asyncio.run(
        compute_impact(
            inv,
            "com.target",
            url="https://x.example",
            token="t",
            transport=transport,
        )
    )

    assert stats_calls == []
    assert result.counts_available is True
    assert result.record_counts == cached


def test_compute_impact_live_flag_forces_refetch_despite_cache() -> None:
    """live=True ignores cached record_counts and hits the live aggregate API."""
    live_payload = {
        "result": [
            {
                "stats": {"count": "999"},
                "groupby_fields": [{"field": "sys_class_name", "value": "sys_script"}],
            }
        ]
    }
    stats_calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if "/api/now/stats/sys_metadata" in req.url.path:
            stats_calls.append(str(req.url))
            return httpx.Response(200, json=live_payload)
        return httpx.Response(200, json={"result": []})

    transport = httpx.MockTransport(handler)

    cached = (ScopeRecordCount(table="sys_script", count=1),)
    target = _plugin("com.target").model_copy(update={"record_counts": cached})
    inv = _inventory(target)

    result = asyncio.run(
        compute_impact(
            inv,
            "com.target",
            url="https://x.example",
            token="t",
            transport=transport,
            live=True,
        )
    )

    assert len(stats_calls) == 1
    assert result.counts_available is True
    assert result.record_counts == (ScopeRecordCount(table="sys_script", count=999),)


def test_compute_impact_falls_back_to_live_when_record_counts_none() -> None:
    """record_counts=None (uncaptured) triggers a live stats/sys_metadata call."""
    live_payload = {
        "result": [
            {
                "stats": {"count": "7"},
                "groupby_fields": [{"field": "sys_class_name", "value": "sys_script"}],
            }
        ]
    }
    stats_calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if "/api/now/stats/sys_metadata" in req.url.path:
            stats_calls.append(str(req.url))
            return httpx.Response(200, json=live_payload)
        return httpx.Response(200, json={"result": []})

    transport = httpx.MockTransport(handler)

    inv = _inventory(_plugin("com.target"))

    result = asyncio.run(
        compute_impact(
            inv,
            "com.target",
            url="https://x.example",
            token="t",
            transport=transport,
        )
    )

    assert len(stats_calls) == 1
    assert result.counts_available is True
    assert result.record_counts[0].count == 7


def _sys_db_object_response(tables: list[str]) -> dict[str, object]:
    return {"result": [{"name": t} for t in tables]}


def _sys_dictionary_response(
    rows: list[tuple[str, str, str]],
) -> dict[str, object]:
    """Each row: (source_table, field, source_scope)."""
    return {
        "result": [
            {
                "name": src,
                "element": field,
                "sys_scope.scope": scope,
            }
            for src, field, scope in rows
        ]
    }


def _stats_count_response(count: int) -> dict[str, object]:
    return {"result": {"stats": {"count": str(count)}}}


def test_fetch_cross_scope_refs_returns_empty_when_no_target_tables() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if "sys_db_object" in req.url.path:
            return httpx.Response(200, json=_sys_db_object_response([]))
        return httpx.Response(404, json={"result": []})

    transport = httpx.MockTransport(handler)
    result = asyncio.run(
        fetch_cross_scope_refs(
            "https://x.example", "t", "com.x", transport=transport
        )
    )
    assert result == ()


def test_fetch_cross_scope_refs_returns_empty_when_no_inbound_refs() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if "sys_db_object" in req.url.path:
            return httpx.Response(200, json=_sys_db_object_response(["cmdb_ci"]))
        if "sys_dictionary" in req.url.path:
            return httpx.Response(200, json=_sys_dictionary_response([]))
        return httpx.Response(404, json={"result": []})

    transport = httpx.MockTransport(handler)
    result = asyncio.run(
        fetch_cross_scope_refs(
            "https://x.example", "t", "com.x", transport=transport
        )
    )
    assert result == ()


def test_fetch_cross_scope_refs_returns_single_match() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if "sys_db_object" in req.url.path:
            return httpx.Response(200, json=_sys_db_object_response(["cmdb_ci"]))
        if "sys_dictionary" in req.url.path:
            return httpx.Response(
                200,
                json=_sys_dictionary_response([("incident", "cmdb_ci", "com.snc.incident")]),
            )
        if "/api/now/stats/" in req.url.path:
            return httpx.Response(200, json=_stats_count_response(42))
        return httpx.Response(404, json={"result": []})

    transport = httpx.MockTransport(handler)
    result = asyncio.run(
        fetch_cross_scope_refs(
            "https://x.example", "t", "com.x", transport=transport
        )
    )
    assert len(result) == 1
    assert result[0].source_table == "incident"
    assert result[0].field == "cmdb_ci"
    assert result[0].source_scope == "com.snc.incident"
    assert result[0].target_table == "cmdb_ci"
    assert result[0].record_count == 42


def test_fetch_cross_scope_refs_sorts_by_count_desc() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if "sys_db_object" in req.url.path:
            return httpx.Response(200, json=_sys_db_object_response(["t1"]))
        if "sys_dictionary" in req.url.path:
            return httpx.Response(
                200,
                json=_sys_dictionary_response(
                    [
                        ("low_count_table", "f", "com.a"),
                        ("high_count_table", "f", "com.b"),
                    ]
                ),
            )
        if "low_count_table" in req.url.path:
            return httpx.Response(200, json=_stats_count_response(5))
        if "high_count_table" in req.url.path:
            return httpx.Response(200, json=_stats_count_response(500))
        return httpx.Response(404, json={"result": []})

    transport = httpx.MockTransport(handler)
    result = asyncio.run(
        fetch_cross_scope_refs(
            "https://x.example", "t", "com.x", transport=transport
        )
    )
    assert [r.record_count for r in result] == [500, 5]


def test_fetch_cross_scope_refs_raises_on_phase1_failure() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if "sys_db_object" in req.url.path:
            return httpx.Response(500, json={})
        return httpx.Response(200, json={"result": []})

    transport = httpx.MockTransport(handler)
    with pytest.raises(ScopeRecordCountError):
        asyncio.run(
            fetch_cross_scope_refs(
                "https://x.example", "t", "com.x", transport=transport
            )
        )


def test_compute_impact_includes_cross_scope_when_enabled() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if "sys_db_object" in req.url.path:
            return httpx.Response(200, json=_sys_db_object_response(["target_table"]))
        if "sys_dictionary" in req.url.path:
            return httpx.Response(
                200,
                json=_sys_dictionary_response([("other_table", "ref", "com.other")]),
            )
        if "/api/now/stats/sys_metadata" in req.url.path:
            return httpx.Response(200, json={"result": []})
        if "/api/now/stats/other_table" in req.url.path:
            return httpx.Response(200, json=_stats_count_response(7))
        return httpx.Response(404, json={"result": []})

    transport = httpx.MockTransport(handler)
    inv = _inventory(_plugin("com.target"))
    result = asyncio.run(
        compute_impact(
            inv,
            "com.target",
            url="https://x.example",
            token="t",
            transport=transport,
        )
    )
    assert result.cross_scope_available is True
    assert len(result.cross_scope_refs) == 1
    assert result.cross_scope_refs[0].source_table == "other_table"


def test_compute_impact_skips_cross_scope_when_disabled() -> None:
    call_count = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if "/api/now/stats/sys_metadata" in req.url.path:
            return httpx.Response(200, json={"result": []})
        return httpx.Response(200, json={"result": []})

    transport = httpx.MockTransport(handler)
    inv = _inventory(_plugin("com.target"))
    result = asyncio.run(
        compute_impact(
            inv,
            "com.target",
            url="https://x.example",
            token="t",
            transport=transport,
            cross_scope=False,
        )
    )
    assert result.cross_scope_available is False
    assert result.cross_scope_refs == ()


def test_compute_impact_marks_cross_scope_unavailable_on_failure() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if "sys_db_object" in req.url.path:
            return httpx.Response(500, json={})
        if "/api/now/stats/sys_metadata" in req.url.path:
            return httpx.Response(200, json={"result": []})
        return httpx.Response(404, json={"result": []})

    transport = httpx.MockTransport(handler)
    target_info = _plugin("com.target").model_copy(update={"record_counts": ()})
    inv = _inventory(target_info)
    result = asyncio.run(
        compute_impact(
            inv,
            "com.target",
            url="https://x.example",
            token="t",
            transport=transport,
        )
    )
    assert result.cross_scope_available is False
    assert result.cross_scope_refs == ()
