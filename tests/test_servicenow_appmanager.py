# tests/test_servicenow_appmanager.py
# Tests for the new appmanager + progress methods on ServiceNowClient.
# Author: Pierre Grothe
# Date: 2026-05-14

"""Tests for the SN App Manager extension methods using httpx.MockTransport."""

import httpx
import pytest

from nexus.connectors.servicenow.client import ServiceNowClient

__all__: list[str] = []


@pytest.mark.asyncio
async def test_appmanager_dependencies_posts_scope_version_body() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["body"] = request.content.decode()
        return httpx.Response(
            200,
            json={
                "result": [
                    {
                        "Id": "Sec Common",
                        "orig_string": "sn_sec_cmn:30.3.0",
                        "type": "Application",
                        "minVersion": "30.3.0",
                        "source_app_id": "abc",
                        "installed": True,
                        "hide_on_ui": False,
                        "status": "Will be Updated",
                        "status_value": "will_be_updated",
                        "active": True,
                        "order": 2,
                        "link": "x",
                        "has_license": False,
                        "is_allowed_install": True,
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with ServiceNowClient("test.service-now.com", token="t") as c:
        c._client = httpx.AsyncClient(  # pyright: ignore[reportPrivateUsage]
            base_url=c._base_url,
            headers={
                "Authorization": "Bearer t",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            transport=transport,
        )
        rows = await c.appmanager_dependencies(plugin_id="sn_sec_cmn", version="30.3.0")

    assert captured["method"] == "POST"
    assert captured["path"] == "/api/sn_appclient/appmanager/dependencies"
    assert '"dependencies":"sn_sec_cmn:30.3.0"' in str(captured["body"])
    assert rows[0]["status_value"] == "will_be_updated"


@pytest.mark.asyncio
async def test_submit_install_uses_get_with_query_params() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["query"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={
                "result": {
                    "status": "0",
                    "status_label": "Pending",
                    "status_message": "",
                    "status_detail": "",
                    "error": "",
                    "percent_complete": 0,
                    "update_set": None,
                    "rollback_version": "1.4",
                    "trackerId": "tracker-xyz",
                    "links": {
                        "progress": {
                            "id": "tracker-xyz",
                            "url": "/api/sn_appclient/appmanager/progress/tracker-xyz",
                        }
                    },
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with ServiceNowClient("test.service-now.com", token="t") as c:
        c._client = httpx.AsyncClient(  # pyright: ignore[reportPrivateUsage]
            base_url=c._base_url,
            headers={
                "Authorization": "Bearer t",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            transport=transport,
        )
        result = await c.submit_install(source_app_id="sys123", version="2.0")

    assert captured["method"] == "GET"
    assert captured["path"] == "/api/sn_appclient/appmanager/app/install"
    assert captured["query"] == {"app_id": "sys123", "version": "2.0"}
    assert result["trackerId"] == "tracker-xyz"
    assert result["rollback_version"] == "1.4"


@pytest.mark.asyncio
async def test_submit_upgrade_reuses_install_endpoint() -> None:
    captured_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_paths.append(request.url.path)
        return httpx.Response(
            200,
            json={
                "result": {
                    "trackerId": "t1",
                    "status": "0",
                    "status_label": "Pending",
                    "status_message": "",
                    "status_detail": "",
                    "error": "",
                    "percent_complete": 0,
                    "update_set": None,
                    "rollback_version": "1.0",
                    "links": {"progress": {"id": "t1", "url": "x"}},
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with ServiceNowClient("test.service-now.com", token="t") as c:
        c._client = httpx.AsyncClient(  # pyright: ignore[reportPrivateUsage]
            base_url=c._base_url,
            headers={
                "Authorization": "Bearer t",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            transport=transport,
        )
        await c.submit_upgrade(source_app_id="sys-up", target_version="2.0")

    assert captured_paths == ["/api/sn_appclient/appmanager/app/install"]


@pytest.mark.asyncio
async def test_submit_activate_uses_get_with_app_id() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["query"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={
                "result": {
                    "trackerId": "t-act",
                    "status": "0",
                    "status_label": "Pending",
                    "status_message": "",
                    "status_detail": "",
                    "error": "",
                    "percent_complete": 0,
                    "update_set": None,
                    "rollback_version": None,
                    "links": {"progress": {"id": "t-act", "url": "x"}},
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with ServiceNowClient("test.service-now.com", token="t") as c:
        c._client = httpx.AsyncClient(  # pyright: ignore[reportPrivateUsage]
            base_url=c._base_url,
            headers={
                "Authorization": "Bearer t",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            transport=transport,
        )
        result = await c.submit_activate(source_app_id="sys-act")

    assert captured["method"] == "GET"
    assert captured["path"] == "/api/sn_appclient/appmanager/app/activate"
    assert captured["query"] == {"app_id": "sys-act"}
    assert result["trackerId"] == "t-act"


@pytest.mark.asyncio
async def test_fetch_progress_returns_raw_dict() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(
            200,
            json={
                "result": {
                    "name": "Install from the App Repository",
                    "state": "2",
                    "message": "ok",
                    "sys_id": "tracker-xyz",
                    "percent_complete": "100",
                    "updated_on": 1778775777000,
                    "results": [],
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with ServiceNowClient("test.service-now.com", token="t") as c:
        c._client = httpx.AsyncClient(  # pyright: ignore[reportPrivateUsage]
            base_url=c._base_url,
            headers={
                "Authorization": "Bearer t",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            transport=transport,
        )
        raw = await c.fetch_progress("tracker-xyz")

    assert captured["path"] == "/api/sn_appclient/appmanager/progress/tracker-xyz"
    assert raw["state"] == "2"
    assert raw["sys_id"] == "tracker-xyz"


@pytest.mark.asyncio
async def test_submit_deactivate_uses_get_with_app_id() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["query"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={
                "result": {
                    "trackerId": "t-deact",
                    "status": "0",
                    "status_label": "Pending",
                    "status_message": "",
                    "status_detail": "",
                    "error": "",
                    "percent_complete": 0,
                    "update_set": None,
                    "rollback_version": None,
                    "links": {"progress": {"id": "t-deact", "url": "x"}},
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with ServiceNowClient("test.service-now.com", token="t") as c:
        c._client = httpx.AsyncClient(  # pyright: ignore[reportPrivateUsage]
            base_url=c._base_url,
            headers={
                "Authorization": "Bearer t",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            transport=transport,
        )
        result = await c.submit_deactivate(source_app_id="sys-deact")

    assert captured["method"] == "GET"
    assert captured["path"] == "/api/sn_appclient/appmanager/app/deactivate"
    assert captured["query"] == {"app_id": "sys-deact"}
    assert result["trackerId"] == "t-deact"


@pytest.mark.asyncio
async def test_submit_uninstall_uses_get_with_app_id() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["query"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={
                "result": {
                    "trackerId": "t-uninst",
                    "status": "0",
                    "status_label": "Pending",
                    "status_message": "",
                    "status_detail": "",
                    "error": "",
                    "percent_complete": 0,
                    "update_set": None,
                    "rollback_version": None,
                    "links": {"progress": {"id": "t-uninst", "url": "x"}},
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with ServiceNowClient("test.service-now.com", token="t") as c:
        c._client = httpx.AsyncClient(  # pyright: ignore[reportPrivateUsage]
            base_url=c._base_url,
            headers={
                "Authorization": "Bearer t",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            transport=transport,
        )
        result = await c.submit_uninstall(source_app_id="sys-uninst")

    assert captured["method"] == "GET"
    assert captured["path"] == "/api/sn_appclient/appmanager/app/uninstall"
    assert captured["query"] == {"app_id": "sys-uninst"}
    assert result["trackerId"] == "t-uninst"
