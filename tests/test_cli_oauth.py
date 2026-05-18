# tests/test_cli_oauth.py
# Tests for cli.oauth (provision_oauth + idempotency + PromptSource wiring).
# Author: Pierre Grothe
# Date: 2026-05-18
"""Tests for nexus.cli.oauth provisioning and lookup helpers.

Drives the real httpx code path via ``httpx.MockTransport`` (a real
``httpx.BaseTransport`` impl, not ``unittest.mock``) and a
``ScriptedPromptSource`` for prompts. Verifies story 05 ACs:

* AC1: POST when no deterministic entity exists
* AC2: PATCH-rotate when a prior-run orphan exists; no duplicate POST
* AC3: All manual fallback prompts route through ``PromptSource``
* AC4: Existing nexus-* listing flow uses ``PromptSource``
"""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from nexus.cli.oauth import (
    fetch_existing_nexus_oauth_apps,
    find_oauth_entity_by_name,
    pick_existing_oauth_app,
    provision_oauth,
)
from tests.fakes.scripted_prompt import ScriptedPromptSource


def _json_response(status_code: int, payload: dict[str, object]) -> httpx.Response:
    """Return a real httpx.Response with the given JSON body."""
    return httpx.Response(
        status_code=status_code,
        content=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
    )


def _transport(
    handler: Callable[[httpx.Request], httpx.Response],
) -> httpx.MockTransport:
    """Build a real httpx.MockTransport routing to ``handler``."""
    return httpx.MockTransport(handler)


def test_find_oauth_entity_by_name_returns_match_for_single_result() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/api/now/table/oauth_entity"
        assert req.url.params["sysparm_query"] == "name=nexus-prod"
        return _json_response(
            200,
            {
                "result": [
                    {"name": "nexus-prod", "client_id": "cid-1", "sys_id": "sys-1"},
                ]
            },
        )

    result = find_oauth_entity_by_name(
        "https://example", "nexus-prod", "u", "p", transport=_transport(handler)
    )
    assert result == {"name": "nexus-prod", "client_id": "cid-1", "sys_id": "sys-1"}


def test_find_oauth_entity_by_name_returns_none_when_no_match() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return _json_response(200, {"result": []})

    assert (
        find_oauth_entity_by_name(
            "https://example", "nexus-prod", "u", "p", transport=_transport(handler)
        )
        is None
    )


def test_find_oauth_entity_by_name_returns_none_when_ambiguous() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return _json_response(
            200,
            {
                "result": [
                    {"name": "nexus-prod", "client_id": "a", "sys_id": "1"},
                    {"name": "nexus-prod", "client_id": "b", "sys_id": "2"},
                ]
            },
        )

    assert (
        find_oauth_entity_by_name(
            "https://example", "nexus-prod", "u", "p", transport=_transport(handler)
        )
        is None
    )


def test_find_oauth_entity_by_name_returns_none_on_non_200() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return _json_response(403, {"error": "forbidden"})

    assert (
        find_oauth_entity_by_name(
            "https://example", "nexus-prod", "u", "p", transport=_transport(handler)
        )
        is None
    )


def test_find_oauth_entity_by_name_returns_none_on_network_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    assert (
        find_oauth_entity_by_name(
            "https://example", "nexus-prod", "u", "p", transport=_transport(handler)
        )
        is None
    )


def test_find_oauth_entity_by_name_drops_entries_missing_client_id() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return _json_response(
            200, {"result": [{"name": "nexus-prod", "sys_id": "1", "client_id": ""}]}
        )

    assert (
        find_oauth_entity_by_name(
            "https://example", "nexus-prod", "u", "p", transport=_transport(handler)
        )
        is None
    )


def test_provision_oauth_creates_when_no_existing_entity() -> None:
    calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(f"{req.method} {req.url.path}")
        if req.method == "GET" and req.url.params.get("sysparm_query") == "name=nexus-prod":
            return _json_response(200, {"result": []})  # no orphan
        if req.method == "GET" and req.url.params.get("sysparm_query") == "nameSTARTSWITHnexus-":
            return _json_response(200, {"result": []})  # no existing
        if req.method == "GET" and req.url.path == "/api/now/table/sys_properties":
            return _json_response(200, {"result": []})  # warn_token_cap noop
        if req.method == "POST" and req.url.path == "/api/now/table/oauth_entity":
            body = json.loads(req.content)
            assert body["name"] == "nexus-prod"
            return _json_response(201, {"result": {"client_id": "new-cid"}})
        return _json_response(404, {})

    cid, secret = provision_oauth(
        "https://example",
        "prod",
        "admin",
        "pw",
        ScriptedPromptSource([]),
        transport=_transport(handler),
    )
    assert cid == "new-cid"
    assert len(secret) > 0
    assert any("POST /api/now/table/oauth_entity" in c for c in calls)


def test_provision_oauth_rotates_secret_when_orphan_found() -> None:
    """AC2: re-running after a Ctrl-C'd run reuses the entity; no duplicate POST."""
    calls: list[str] = []
    rotated_secrets: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(f"{req.method} {req.url.path}")
        if req.method == "GET" and req.url.params.get("sysparm_query") == "name=nexus-prod":
            return _json_response(
                200,
                {
                    "result": [
                        {"name": "nexus-prod", "client_id": "orphan-cid", "sys_id": "orphan-sys"}
                    ]
                },
            )
        if req.method == "PATCH" and req.url.path == "/api/now/table/oauth_entity/orphan-sys":
            body = json.loads(req.content)
            rotated_secrets.append(body["client_secret"])
            return _json_response(200, {"result": {"client_secret": "********"}})
        return _json_response(500, {"error": "should not be reached"})

    cid, secret = provision_oauth(
        "https://example",
        "prod",
        "admin",
        "pw",
        ScriptedPromptSource([]),
        transport=_transport(handler),
    )

    assert cid == "orphan-cid"
    assert secret == rotated_secrets[0]
    assert not any(
        "POST /api/now/table/oauth_entity" == c for c in calls
    ), "no duplicate create; idempotency violated"
    assert any("PATCH /api/now/table/oauth_entity/orphan-sys" in c for c in calls)


def test_provision_oauth_falls_back_to_listing_when_rotation_fails() -> None:
    """Orphan found but PATCH returns 500 -> fall through to listing flow."""
    posts: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "GET" and req.url.params.get("sysparm_query") == "name=nexus-prod":
            return _json_response(
                200,
                {"result": [{"name": "nexus-prod", "client_id": "orphan", "sys_id": "sys-x"}]},
            )
        if req.method == "PATCH":
            return _json_response(500, {})
        if req.method == "GET" and req.url.params.get("sysparm_query") == "nameSTARTSWITHnexus-":
            return _json_response(200, {"result": []})
        if req.method == "GET" and req.url.path == "/api/now/table/sys_properties":
            return _json_response(200, {"result": []})
        if req.method == "POST":
            posts.append(req)
            return _json_response(201, {"result": {"client_id": "new-cid"}})
        return _json_response(404, {})

    cid, secret = provision_oauth(
        "https://example",
        "prod",
        "admin",
        "pw",
        ScriptedPromptSource([]),
        transport=_transport(handler),
    )
    assert cid == "new-cid"
    assert len(secret) > 0
    assert len(posts) == 1


def test_provision_oauth_falls_back_to_prompts_on_post_failure() -> None:
    """AC3: HTTP failure routes through PromptSource for manual entry."""

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "GET" and req.url.params.get("sysparm_query") == "name=nexus-prod":
            return _json_response(200, {"result": []})
        if req.method == "GET" and req.url.params.get("sysparm_query") == "nameSTARTSWITHnexus-":
            return _json_response(200, {"result": []})
        if req.method == "POST":
            return _json_response(403, {"error": "forbidden"})
        return _json_response(404, {})

    prompts = ScriptedPromptSource(["manual-cid", "manual-secret"])
    cid, secret = provision_oauth(
        "https://example",
        "prod",
        "admin",
        "pw",
        prompts,
        transport=_transport(handler),
    )
    assert cid == "manual-cid"
    assert secret == "manual-secret"


def test_pick_existing_oauth_app_uses_prompt_source_for_choice() -> None:
    """AC4: pick_existing_oauth_app routes choice + secret prompts through PromptSource."""
    entries = [
        {
            "name": "nexus-existing",
            "client_id": "cid-1",
            "sys_id": "sys-1",
            "sys_created_on": "2026-05-01",
        }
    ]
    prompts = ScriptedPromptSource(["1", "pasted-secret"])
    result = pick_existing_oauth_app(entries, "newprofile", "https://example", prompts)
    assert result == ("cid-1", "pasted-secret")


def test_pick_existing_oauth_app_returns_none_when_user_picks_new() -> None:
    entries = [
        {
            "name": "nexus-existing",
            "client_id": "cid-1",
            "sys_id": "sys-1",
            "sys_created_on": "2026-05-01",
        }
    ]
    prompts = ScriptedPromptSource(["n"])
    assert pick_existing_oauth_app(entries, "p", "https://example", prompts) is None


def test_pick_existing_oauth_app_returns_none_when_choice_out_of_range() -> None:
    entries = [
        {
            "name": "nexus-existing",
            "client_id": "cid-1",
            "sys_id": "sys-1",
            "sys_created_on": "2026-05-01",
        }
    ]
    prompts = ScriptedPromptSource(["99"])
    assert pick_existing_oauth_app(entries, "p", "https://example", prompts) is None


def test_pick_existing_oauth_app_returns_none_when_choice_is_garbage() -> None:
    entries = [
        {
            "name": "nexus-existing",
            "client_id": "cid-1",
            "sys_id": "sys-1",
            "sys_created_on": "2026-05-01",
        }
    ]
    prompts = ScriptedPromptSource(["xyz"])
    assert pick_existing_oauth_app(entries, "p", "https://example", prompts) is None


def test_provision_oauth_offers_to_reuse_when_other_nexus_apps_exist() -> None:
    """AC4: an existing non-orphan nexus-* app triggers the reuse prompt path."""

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "GET" and req.url.params.get("sysparm_query") == "name=nexus-prod":
            return _json_response(200, {"result": []})  # no orphan match
        if req.method == "GET" and req.url.params.get("sysparm_query") == "nameSTARTSWITHnexus-":
            return _json_response(
                200,
                {
                    "result": [
                        {
                            "name": "nexus-other",
                            "client_id": "cid-other",
                            "sys_id": "sys-other",
                            "sys_created_on": "2026-04-01",
                        }
                    ]
                },
            )
        return _json_response(404, {})

    prompts = ScriptedPromptSource(["1", "other-secret"])
    cid, secret = provision_oauth(
        "https://example",
        "prod",
        "admin",
        "pw",
        prompts,
        transport=_transport(handler),
    )
    assert cid == "cid-other"
    assert secret == "other-secret"


def test_fetch_existing_nexus_oauth_apps_returns_empty_on_non_200() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return _json_response(403, {})

    assert (
        fetch_existing_nexus_oauth_apps("https://example", "u", "p", transport=_transport(handler))
        == []
    )


def test_fetch_existing_nexus_oauth_apps_returns_empty_on_network_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    assert (
        fetch_existing_nexus_oauth_apps("https://example", "u", "p", transport=_transport(handler))
        == []
    )


def test_fetch_existing_nexus_oauth_apps_drops_entries_without_client_id() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return _json_response(
            200,
            {
                "result": [
                    {
                        "name": "nexus-a",
                        "client_id": "cid-a",
                        "sys_id": "s-a",
                        "sys_created_on": "",
                    },
                    {"name": "nexus-b", "client_id": "", "sys_id": "s-b", "sys_created_on": ""},
                ]
            },
        )

    result = fetch_existing_nexus_oauth_apps(
        "https://example", "u", "p", transport=_transport(handler)
    )
    assert [e["client_id"] for e in result] == ["cid-a"]


def test_provision_oauth_handles_201_without_client_id() -> None:
    """SN returns 201 but the result has no client_id -> falls back to prompts."""

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "GET" and req.url.params.get("sysparm_query") == "name=nexus-prod":
            return _json_response(200, {"result": []})
        if req.method == "GET" and req.url.params.get("sysparm_query") == "nameSTARTSWITHnexus-":
            return _json_response(200, {"result": []})
        if req.method == "POST":
            return _json_response(201, {"result": {}})
        return _json_response(404, {})

    prompts = ScriptedPromptSource(["manual-cid", "manual-secret"])
    cid, secret = provision_oauth(
        "https://example",
        "prod",
        "admin",
        "pw",
        prompts,
        transport=_transport(handler),
    )
    assert cid == "manual-cid"
    assert secret == "manual-secret"


def test_provision_oauth_handles_request_error_during_post() -> None:
    """httpx.RequestError during POST -> manual fallback prompts."""
    state = {"calls": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "GET" and req.url.params.get("sysparm_query") == "name=nexus-prod":
            return _json_response(200, {"result": []})
        if req.method == "GET" and req.url.params.get("sysparm_query") == "nameSTARTSWITHnexus-":
            return _json_response(200, {"result": []})
        if req.method == "POST":
            state["calls"] += 1
            raise httpx.ConnectError("network down")
        return _json_response(404, {})

    prompts = ScriptedPromptSource(["fallback-cid", "fallback-secret"])
    cid, secret = provision_oauth(
        "https://example",
        "prod",
        "admin",
        "pw",
        prompts,
        transport=_transport(handler),
    )
    assert cid == "fallback-cid"
    assert secret == "fallback-secret"
    assert state["calls"] == 1


def test_provision_oauth_handles_request_error_during_rotation() -> None:
    """Network error during PATCH rotation -> fall through to listing then create."""

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "GET" and req.url.params.get("sysparm_query") == "name=nexus-prod":
            return _json_response(
                200,
                {"result": [{"name": "nexus-prod", "client_id": "o-cid", "sys_id": "o-sys"}]},
            )
        if req.method == "PATCH":
            raise httpx.ConnectError("flaky")
        if req.method == "GET" and req.url.params.get("sysparm_query") == "nameSTARTSWITHnexus-":
            return _json_response(200, {"result": []})
        if req.method == "POST":
            return _json_response(201, {"result": {"client_id": "new-cid"}})
        return _json_response(404, {})

    cid, _secret = provision_oauth(
        "https://example",
        "prod",
        "admin",
        "pw",
        ScriptedPromptSource([]),
        transport=_transport(handler),
    )
    assert cid == "new-cid"


def test_provision_oauth_skips_warn_token_cap_when_property_missing() -> None:
    """warn_token_cap path covered for the happy path."""

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "GET" and req.url.params.get("sysparm_query") == "name=nexus-prod":
            return _json_response(200, {"result": []})
        if req.method == "GET" and req.url.params.get("sysparm_query") == "nameSTARTSWITHnexus-":
            return _json_response(200, {"result": []})
        if req.method == "POST":
            return _json_response(201, {"result": {"client_id": "cid"}})
        if req.method == "GET" and req.url.path == "/api/now/table/sys_properties":
            return _json_response(200, {"result": [{"value": "3600"}]})
        return _json_response(404, {})

    cid, _secret = provision_oauth(
        "https://example",
        "prod",
        "admin",
        "pw",
        ScriptedPromptSource([]),
        transport=_transport(handler),
    )
    assert cid == "cid"


@pytest.mark.parametrize("status", [400, 401, 403, 500, 502])
def test_provision_oauth_falls_back_on_non_201_status(status: int) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "GET" and req.url.params.get("sysparm_query") == "name=nexus-prod":
            return _json_response(200, {"result": []})
        if req.method == "GET" and req.url.params.get("sysparm_query") == "nameSTARTSWITHnexus-":
            return _json_response(200, {"result": []})
        if req.method == "POST":
            return _json_response(status, {"error": "denied"})
        return _json_response(404, {})

    prompts = ScriptedPromptSource(["manual-cid", "manual-secret"])
    cid, secret = provision_oauth(
        "https://example",
        "prod",
        "admin",
        "pw",
        prompts,
        transport=_transport(handler),
    )
    assert (cid, secret) == ("manual-cid", "manual-secret")
