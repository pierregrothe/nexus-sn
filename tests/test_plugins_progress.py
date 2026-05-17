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
async def test_poll_invokes_on_progress_for_every_snapshot() -> None:
    """The on_progress callback fires once per poll (intermediate and terminal)."""
    client = FakeServiceNowClient()
    client.set_progress_sequence("t1", [_raw("1", 25), _raw("1", 60), _raw("2", 100)])
    poller = ProgressPoller(client, poll_interval_s=0.01, timeout_s=2.0)
    snapshots: list[tuple[int, str]] = []

    def _cb(state: object) -> None:
        from nexus.plugins.progress import ProgressState  # noqa: PLC0415

        assert isinstance(state, ProgressState)
        snapshots.append((state.percent_complete, state.status))

    await poller.poll("t1", on_progress=_cb)
    assert snapshots == [(25, "1"), (60, "1"), (100, "2")]


@pytest.mark.asyncio
async def test_poll_without_on_progress_still_succeeds() -> None:
    """Omitting the callback is a no-op -- poller behaves as before."""
    client = FakeServiceNowClient()
    client.set_progress_sequence("t1", [_raw("1", 50), _raw("2", 100)])
    poller = ProgressPoller(client, poll_interval_s=0.01, timeout_s=2.0)
    final = await poller.poll("t1")
    assert final.is_success


@pytest.mark.asyncio
async def test_poll_invokes_on_progress_before_raising_on_failure() -> None:
    """on_progress sees the failed snapshot before PluginProgressError is raised."""
    client = FakeServiceNowClient()
    client.set_progress_sequence("t1", [_raw("1", 30), _raw("3", 30, err="boom")])
    poller = ProgressPoller(client, poll_interval_s=0.01, timeout_s=2.0)
    seen: list[str] = []

    def _cb(state: object) -> None:
        from nexus.plugins.progress import ProgressState  # noqa: PLC0415

        assert isinstance(state, ProgressState)
        seen.append(state.status)

    with pytest.raises(PluginProgressError):
        await poller.poll("t1", on_progress=_cb)
    assert seen == ["1", "3"]


@pytest.mark.asyncio
async def test_poller_raises_on_timeout() -> None:
    client = FakeServiceNowClient()
    # Many "still in progress" responses -- exceeds timeout
    client.set_progress_sequence("t1", [_raw("1", 1) for _ in range(50)])
    poller = ProgressPoller(client, poll_interval_s=0.02, timeout_s=0.05)
    with pytest.raises(PluginTimeoutError) as excinfo:
        await poller.poll("t1")
    assert excinfo.value.tracker_id == "t1"
