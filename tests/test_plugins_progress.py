# tests/test_plugins_progress.py
# Tests for ProgressPoller.
# Author: Pierre Grothe
# Date: 2026-05-14

"""Tests for ProgressPoller polling behaviour."""

import pytest

from nexus.plugins.errors import PluginProgressError, PluginTimeoutError
from nexus.plugins.progress import ProgressPoller
from tests.fakes.fake_sn_client import FakeServiceNowClient

__all__: list[str] = []


def _raw(status: str, pct: int, err: str = "", tracker: str = "t1") -> dict[str, object]:
    return {
        "status": status,
        "status_label": "x",
        "percent_complete": pct,
        "error": err,
        "update_set": None,
        "rollback_version": None,
        "trackerId": tracker,
        "status_message": "",
        "status_detail": "",
    }


@pytest.mark.asyncio
async def test_poller_returns_terminal_success() -> None:
    client = FakeServiceNowClient()
    client.set_progress_sequence("t1", [_raw("1", 50), _raw("2", 100)])
    poller = ProgressPoller(client, poll_interval_s=0.01, timeout_s=2.0)
    final = await poller.poll("t1")
    assert final.is_terminal
    assert final.is_success
    assert final.percent_complete == 100


@pytest.mark.asyncio
async def test_poller_raises_on_failed_status() -> None:
    client = FakeServiceNowClient()
    client.set_progress_sequence("t1", [_raw("1", 30), _raw("3", 30, err="boom")])
    poller = ProgressPoller(client, poll_interval_s=0.01, timeout_s=2.0)
    with pytest.raises(PluginProgressError) as excinfo:
        await poller.poll("t1")
    assert excinfo.value.error_message == "boom"
    assert excinfo.value.sn_status == "3"


@pytest.mark.asyncio
async def test_poller_raises_on_timeout() -> None:
    client = FakeServiceNowClient()
    # Many "still in progress" responses -- exceeds timeout
    client.set_progress_sequence("t1", [_raw("1", 1) for _ in range(50)])
    poller = ProgressPoller(client, poll_interval_s=0.02, timeout_s=0.05)
    with pytest.raises(PluginTimeoutError) as excinfo:
        await poller.poll("t1")
    assert excinfo.value.tracker_id == "t1"
