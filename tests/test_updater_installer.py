# tests/test_updater_installer.py
# Tests for download_wheel + pip_install_wheel.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for nexus.updater.installer."""

import subprocess
from pathlib import Path

import httpx
import pytest

from nexus.updater.errors import UpdaterError
from nexus.updater.installer import download_wheel, pip_install_wheel
from tests.conftest import transport_raising, transport_returning


def test_download_wheel_writes_file_on_200(tmp_path: Path) -> None:
    response = httpx.Response(200, content=b"WHEEL_BYTES")
    with httpx.Client(transport=transport_returning(response)) as client:
        path = download_wheel(
            "https://example.com/nexus_sn-2026.06.0-py3-none-any.whl",
            dest_dir=tmp_path,
            httpx_client=client,
        )
    assert path == tmp_path / "nexus_sn-2026.06.0-py3-none-any.whl"
    assert path.read_bytes() == b"WHEEL_BYTES"


def test_download_wheel_raises_on_non_200(tmp_path: Path) -> None:
    response = httpx.Response(404)
    with httpx.Client(transport=transport_returning(response)) as client:
        with pytest.raises(UpdaterError, match="404"):
            download_wheel(
                "https://example.com/nexus_sn-2026.06.0-py3-none-any.whl",
                dest_dir=tmp_path,
                httpx_client=client,
            )


def test_download_wheel_raises_on_network_error(tmp_path: Path) -> None:
    transport = transport_raising(httpx.ConnectError("nope"))
    with httpx.Client(transport=transport) as client:
        with pytest.raises(UpdaterError, match="network"):
            download_wheel(
                "https://example.com/nexus_sn-2026.06.0-py3-none-any.whl",
                dest_dir=tmp_path,
                httpx_client=client,
            )


def test_download_wheel_constructs_default_client_when_none_injected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = httpx.Response(200, content=b"WHEEL_BYTES")
    real_client = httpx.Client

    def fake_client_factory(timeout: float) -> httpx.Client:
        return real_client(transport=transport_returning(response), timeout=timeout)

    monkeypatch.setattr(httpx, "Client", fake_client_factory)
    path = download_wheel(
        "https://example.com/nexus_sn-2026.06.0-py3-none-any.whl",
        dest_dir=tmp_path,
    )
    assert path.read_bytes() == b"WHEEL_BYTES"


def test_download_wheel_follows_github_redirect(tmp_path: Path) -> None:
    """GitHub asset URLs return 302 to objects.githubusercontent.com; follow it."""
    primary_url = "https://example.com/nexus_sn-2026.06.0-py3-none-any.whl"
    redirect_url = "https://cdn.example.com/nexus_sn-2026.06.0-py3-none-any.whl"

    def handler(req: httpx.Request) -> httpx.Response:
        if str(req.url) == primary_url:
            return httpx.Response(302, headers={"Location": redirect_url})
        return httpx.Response(200, content=b"WHEEL_BYTES")

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        path = download_wheel(primary_url, dest_dir=tmp_path, httpx_client=client)
    assert path.read_bytes() == b"WHEEL_BYTES"


def test_pip_install_wheel_runs_subprocess_and_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wheel = tmp_path / "fake.whl"
    wheel.write_bytes(b"")
    captured: list[list[str]] = []

    def fake_run(cmd: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        captured.append(cmd)
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    pip_install_wheel(wheel)
    assert len(captured) == 1
    assert captured[0][1:4] == ["-m", "pip", "install"]
    assert "--upgrade" in captured[0]
    assert str(wheel) in captured[0]


def test_pip_install_wheel_raises_on_non_zero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wheel = tmp_path / "fake.whl"
    wheel.write_bytes(b"")

    def fake_run(cmd: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=cmd, returncode=1, stdout="", stderr="permission denied"
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(UpdaterError, match="permission denied"):
        pip_install_wheel(wheel)
