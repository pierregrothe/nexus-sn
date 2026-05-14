# tests/test_fakes_sn_client_appmanager.py
# Tests for FakeServiceNowClient appmanager + progress canned responses.
# Author: Pierre Grothe
# Date: 2026-05-14

"""Verify FakeServiceNowClient canned responses for the appmanager methods."""

import pytest

from tests.fakes.fake_sn_client import FakeServiceNowClient

__all__: list[str] = []


@pytest.mark.asyncio
async def test_set_dependencies_returns_queued_entries() -> None:
    client = FakeServiceNowClient()
    client.set_dependencies("sn_si", [{"Id": "X", "orig_string": "sn_si:1.0"}])
    rows = await client.appmanager_dependencies("sn_si")
    assert len(rows) == 1
    assert rows[0]["Id"] == "X"


@pytest.mark.asyncio
async def test_queue_install_response_returns_fifo() -> None:
    client = FakeServiceNowClient()
    client.queue_install_response({"trackerId": "t1"})
    client.queue_install_response({"trackerId": "t2"})
    first = await client.submit_install("sys1")
    second = await client.submit_install("sys2")
    assert first["trackerId"] == "t1"
    assert second["trackerId"] == "t2"


@pytest.mark.asyncio
async def test_submit_install_raises_when_unqueued() -> None:
    client = FakeServiceNowClient()
    with pytest.raises(RuntimeError):
        await client.submit_install("sys1")


@pytest.mark.asyncio
async def test_fetch_progress_auto_terminates_when_sequence_empty() -> None:
    client = FakeServiceNowClient()
    raw = await client.fetch_progress("t-unknown")
    assert raw["status"] == "2"  # Success
    assert raw["percent_complete"] == 100


@pytest.mark.asyncio
async def test_set_progress_sequence_yields_in_order() -> None:
    client = FakeServiceNowClient()
    client.set_progress_sequence(
        "t1", [{"status": "1", "percent_complete": 50}, {"status": "2", "percent_complete": 100}]
    )
    a = await client.fetch_progress("t1")
    b = await client.fetch_progress("t1")
    assert a["status"] == "1"
    assert b["status"] == "2"


@pytest.mark.asyncio
async def test_queue_deactivate_response_returns_fifo() -> None:
    client = FakeServiceNowClient()
    client.queue_deactivate_response({"trackerId": "d1"})
    client.queue_deactivate_response({"trackerId": "d2"})
    first = await client.submit_deactivate("sys1")
    second = await client.submit_deactivate("sys2")
    assert first["trackerId"] == "d1"
    assert second["trackerId"] == "d2"


@pytest.mark.asyncio
async def test_submit_deactivate_raises_when_unqueued() -> None:
    client = FakeServiceNowClient()
    with pytest.raises(RuntimeError):
        await client.submit_deactivate("sys1")


@pytest.mark.asyncio
async def test_queue_uninstall_response_returns_fifo() -> None:
    client = FakeServiceNowClient()
    client.queue_uninstall_response({"trackerId": "u1"})
    raw = await client.submit_uninstall("sys-x")
    assert raw["trackerId"] == "u1"


@pytest.mark.asyncio
async def test_submit_uninstall_raises_when_unqueued() -> None:
    client = FakeServiceNowClient()
    with pytest.raises(RuntimeError):
        await client.submit_uninstall("sys1")
