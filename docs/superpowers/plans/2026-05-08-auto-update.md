# NEXUS Self-Update Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the NEXUS auto-updater (Layer 7 `updater/` package) that checks GitHub Releases on every CLI launch, downloads new wheels, runs `pip install --upgrade`, and re-execs with the new code. Replaces the broken-by-default PyPI-publishing release workflow with GitHub-Releases-only.

**Architecture:** New `src/nexus/updater/` package with focused modules (errors, current, client, installer, runner). The CLI's `@app.callback()` invokes `check_and_maybe_update()` before any command. Editable installs are detected and skipped so dev environments are unaffected.

**Tech Stack:** Python 3.14, existing `httpx` and `typer`, existing `keyring`, new `packaging >= 23` declared explicitly, stdlib `importlib.metadata` + `subprocess` + `fcntl` (POSIX) / `msvcrt` (Windows).

---

## File Map

```
ADD:
  src/nexus/updater/__init__.py           -- exports public entry points
  src/nexus/updater/errors.py             -- UpdaterError
  src/nexus/updater/current.py            -- current_version + is_editable_install
  src/nexus/updater/client.py             -- GitHubReleasesClient + ReleaseInfo
  src/nexus/updater/installer.py          -- download_wheel + pip_install_wheel
  src/nexus/updater/runner.py             -- check_and_maybe_update orchestrator
  tests/test_updater_current.py
  tests/test_updater_client.py
  tests/test_updater_installer.py
  tests/test_updater_runner.py
  tests/fakes/fake_github_releases.py     -- FakeGitHubReleasesClient
  .primer/adr/ADR-020-self-update.md

MODIFY:
  pyproject.toml                          -- add packaging >= 23 to runtime deps
  src/nexus/cli.py                        -- callback hook + `nexus update` command
  tests/fakes/__init__.py                 -- export FakeGitHubReleasesClient
  .github/workflows/release.yml           -- replace PyPI publish with GitHub Release creation
  .ratchet.json                           -- 6 new module entries + cli bump
  .primer/governance.md                   -- ADR-020 catalog row
  .primer/decisions.md                    -- append ADR-020 entry
  .primer/patterns.md                     -- updater layer dep entry
```

---

## Task 1: Add packaging dep + create updater package skeleton

**Files:**
- Modify: `pyproject.toml`
- Create: `src/nexus/updater/__init__.py`
- Create: `src/nexus/updater/errors.py`

- [ ] **Step 1: Add packaging to pyproject.toml**

In `[tool.poetry.dependencies]`, add after `pyyaml`:

```toml
packaging = ">=23"
```

- [ ] **Step 2: Lock + install**

```bash
poetry lock && poetry install
```

Expected: `packaging` already installed (transitive), now declared explicitly.

- [ ] **Step 3: Create errors.py**

Write `src/nexus/updater/errors.py`:

```python
# src/nexus/updater/errors.py
# Updater-layer exceptions. All caught by check_and_maybe_update; never escape.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Exception types for the auto-updater."""

__all__ = ["UpdaterError"]


class UpdaterError(Exception):
    """Raised by updater internals when an update step fails.

    The runner catches this and falls back to running the current version.
    Never escapes user-facing code.
    """
```

- [ ] **Step 4: Create __init__.py with placeholder export**

Write `src/nexus/updater/__init__.py`:

```python
# src/nexus/updater/__init__.py
# NEXUS self-update package (ADR-020).
# Author: Pierre Grothe
# Date: 2026-05-08
"""NEXUS auto-updater.

check_and_maybe_update() is invoked by the CLI callback before every command.
On non-editable installs, it queries the GitHub Releases API for a newer
version, downloads the wheel, runs pip install, and re-execs the user's
command with the new code.
"""

from nexus.updater.errors import UpdaterError

__all__ = ["UpdaterError"]
```

(`current_version`, `is_editable_install`, and `check_and_maybe_update` are added to `__all__` in later tasks.)

- [ ] **Step 5: Verify import works**

```bash
.venv/bin/python -c "from nexus.updater import UpdaterError; print('imports ok')"
```

Expected: `imports ok`

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml poetry.lock src/nexus/updater/__init__.py src/nexus/updater/errors.py && git commit -m "feat(updater): add packaging dep + UpdaterError skeleton"
```

---

## Task 2: current.py -- current_version + is_editable_install

**Files:**
- Create: `src/nexus/updater/current.py`
- Modify: `src/nexus/updater/__init__.py`
- Create: `tests/test_updater_current.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_updater_current.py`:

```python
# tests/test_updater_current.py
# Tests for current_version and is_editable_install.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for nexus.updater.current."""

from importlib.metadata import PackageNotFoundError

import pytest

from nexus.updater.current import current_version, is_editable_install


def test_current_version_returns_string_when_installed() -> None:
    version = current_version()
    # In dev (pip install -e .) we ARE installed, so a version is present.
    assert version is not None
    assert isinstance(version, str)


def test_current_version_returns_none_when_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nexus.updater import current as current_module

    def raise_pnf(name: str) -> str:
        raise PackageNotFoundError(name)

    monkeypatch.setattr(current_module.metadata, "version", raise_pnf)
    assert current_version() is None


def test_is_editable_install_true_in_dev_environment() -> None:
    # The dev environment uses `pip install -e .`, so this should be True.
    assert is_editable_install() is True


def test_is_editable_install_false_when_origin_says_not_editable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nexus.updater import current as current_module

    class _FakeDirInfo:
        editable = False

    class _FakeOrigin:
        dir_info = _FakeDirInfo()

    class _FakeDistribution:
        @property
        def origin(self) -> _FakeOrigin:
            return _FakeOrigin()

    def fake_distribution(name: str) -> _FakeDistribution:
        return _FakeDistribution()

    monkeypatch.setattr(current_module.metadata, "distribution", fake_distribution)
    assert is_editable_install() is False


def test_is_editable_install_false_when_package_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nexus.updater import current as current_module

    def raise_pnf(name: str) -> str:
        raise PackageNotFoundError(name)

    monkeypatch.setattr(current_module.metadata, "distribution", raise_pnf)
    assert is_editable_install() is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_updater_current.py -v --override-ini="addopts="
```

Expected: ImportError on `nexus.updater.current`.

- [ ] **Step 3: Implement current.py**

Write `src/nexus/updater/current.py`:

```python
# src/nexus/updater/current.py
# Read installed nexus-sn version + detect editable installs.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Version detection helpers for the auto-updater."""

import logging
from importlib import metadata

log = logging.getLogger(__name__)

__all__ = ["current_version", "is_editable_install"]

_PACKAGE_NAME = "nexus-sn"


def current_version() -> str | None:
    """Return the installed nexus-sn version, or None if not installed.

    Returns:
        The version string (e.g., "2026.05.1") when nexus-sn is installed
        as a distribution. None when running directly from a source clone
        without `pip install`.
    """
    try:
        return metadata.version(_PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        log.debug("nexus-sn not installed as a distribution")
        return None


def is_editable_install() -> bool:
    """Return True if nexus-sn was installed via `pip install -e .` (PEP 660).

    Reads importlib.metadata.distribution("nexus-sn").origin.dir_info.editable.
    Returns False on any failure (package not installed, missing origin,
    older distribution metadata).
    """
    try:
        dist = metadata.distribution(_PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        return False
    origin = getattr(dist, "origin", None)
    if origin is None:
        return False
    dir_info = getattr(origin, "dir_info", None)
    if dir_info is None:
        return False
    return bool(getattr(dir_info, "editable", False))
```

- [ ] **Step 4: Update __init__.py**

Replace `src/nexus/updater/__init__.py`:

```python
# src/nexus/updater/__init__.py
# NEXUS self-update package (ADR-020).
# Author: Pierre Grothe
# Date: 2026-05-08
"""NEXUS auto-updater.

check_and_maybe_update() is invoked by the CLI callback before every command.
On non-editable installs, it queries the GitHub Releases API for a newer
version, downloads the wheel, runs pip install, and re-execs the user's
command with the new code.
"""

from nexus.updater.current import current_version, is_editable_install
from nexus.updater.errors import UpdaterError

__all__ = ["UpdaterError", "current_version", "is_editable_install"]
```

- [ ] **Step 5: Run tests + lint**

```bash
.venv/bin/pytest tests/test_updater_current.py -v --override-ini="addopts="
.venv/bin/ruff check src/nexus/updater/current.py tests/test_updater_current.py
.venv/bin/mypy src/nexus/updater/current.py
.venv/bin/pyright src/nexus/updater/current.py
```

Expected: 5 tests pass; 0 violations; 0 errors.

- [ ] **Step 6: Commit**

```bash
git add src/nexus/updater/current.py src/nexus/updater/__init__.py tests/test_updater_current.py && git commit -m "feat(updater): current_version + is_editable_install"
```

---

## Task 3: client.py -- GitHubReleasesClient + ReleaseInfo

**Files:**
- Create: `src/nexus/updater/client.py`
- Create: `tests/test_updater_client.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_updater_client.py`:

```python
# tests/test_updater_client.py
# Tests for GitHubReleasesClient.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for nexus.updater.client."""

import httpx

from nexus.updater.client import GitHubReleasesClient, ReleaseInfo


def _client_with_response(response: httpx.Response) -> GitHubReleasesClient:
    transport = httpx.MockTransport(lambda req: response)
    return GitHubReleasesClient(httpx_client=httpx.Client(transport=transport))


def test_fetch_latest_returns_release_info_on_200() -> None:
    response = httpx.Response(
        200,
        json={
            "tag_name": "2026.06.0",
            "assets": [
                {
                    "name": "nexus_sn-2026.06.0-py3-none-any.whl",
                    "browser_download_url": "https://example.com/nexus_sn-2026.06.0-py3-none-any.whl",
                }
            ],
        },
    )
    client = _client_with_response(response)
    info = client.fetch_latest()
    assert info is not None
    assert info.tag_name == "2026.06.0"
    assert info.wheel_url == "https://example.com/nexus_sn-2026.06.0-py3-none-any.whl"


def test_fetch_latest_returns_release_info_with_no_wheel_when_no_assets() -> None:
    response = httpx.Response(200, json={"tag_name": "2026.06.0", "assets": []})
    client = _client_with_response(response)
    info = client.fetch_latest()
    assert info is not None
    assert info.tag_name == "2026.06.0"
    assert info.wheel_url is None


def test_fetch_latest_skips_non_wheel_assets() -> None:
    response = httpx.Response(
        200,
        json={
            "tag_name": "2026.06.0",
            "assets": [
                {"name": "checksums.txt", "browser_download_url": "https://example.com/checksums.txt"},
                {
                    "name": "nexus_sn-2026.06.0-py3-none-any.whl",
                    "browser_download_url": "https://example.com/nexus_sn-2026.06.0-py3-none-any.whl",
                },
            ],
        },
    )
    client = _client_with_response(response)
    info = client.fetch_latest()
    assert info is not None
    assert info.wheel_url is not None
    assert info.wheel_url.endswith(".whl")


def test_fetch_latest_returns_none_on_404() -> None:
    response = httpx.Response(404, json={"message": "Not Found"})
    client = _client_with_response(response)
    assert client.fetch_latest() is None


def test_fetch_latest_returns_none_on_403_rate_limit() -> None:
    response = httpx.Response(403, json={"message": "API rate limit exceeded"})
    client = _client_with_response(response)
    assert client.fetch_latest() is None


def test_fetch_latest_returns_none_on_timeout() -> None:
    def raise_timeout(req: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    transport = httpx.MockTransport(raise_timeout)
    client = GitHubReleasesClient(httpx_client=httpx.Client(transport=transport))
    assert client.fetch_latest() is None


def test_fetch_latest_returns_none_when_tag_name_missing() -> None:
    response = httpx.Response(200, json={"assets": []})
    client = _client_with_response(response)
    assert client.fetch_latest() is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_updater_client.py -v --override-ini="addopts="
```

Expected: ImportError on `nexus.updater.client`.

- [ ] **Step 3: Implement client.py**

Write `src/nexus/updater/client.py`:

```python
# src/nexus/updater/client.py
# Tiny GitHub Releases API client. Never raises -- failures return None.
# Author: Pierre Grothe
# Date: 2026-05-08
"""GitHubReleasesClient: read /repos/<owner>/<name>/releases/latest.

Returns ReleaseInfo with the tag and wheel URL, or None on any failure
(network down, 404, 403 rate limit, malformed JSON, missing tag_name).
"""

import logging
from dataclasses import dataclass
from typing import cast

import httpx

log = logging.getLogger(__name__)

__all__ = ["GitHubReleasesClient", "ReleaseInfo"]

_DEFAULT_REPO = "pierregrothe/nexus-sn"
_DEFAULT_TIMEOUT_SECONDS = 3.0


@dataclass(slots=True, frozen=True)
class ReleaseInfo:
    """Subset of GitHub Releases API response we use.

    Attributes:
        tag_name: Release tag (e.g., "2026.06.0").
        wheel_url: HTTPS URL of the .whl asset, or None if the release
            has no wheel attached.
    """

    tag_name: str
    wheel_url: str | None


class GitHubReleasesClient:
    """Read /repos/<repo>/releases/latest. Never raises.

    Args:
        repo: "<owner>/<name>" string. Default "pierregrothe/nexus-sn".
        timeout_seconds: HTTP timeout. Default 3.0.
        httpx_client: Optional pre-built client (for tests with MockTransport).
            If None, a default client is constructed at fetch time.
    """

    def __init__(
        self,
        *,
        repo: str = _DEFAULT_REPO,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        httpx_client: httpx.Client | None = None,
    ) -> None:
        """See class docstring."""
        self._repo = repo
        self._timeout = timeout_seconds
        self._injected_client = httpx_client

    def fetch_latest(self) -> ReleaseInfo | None:
        """GET /repos/<repo>/releases/latest. Return None on any failure."""
        url = f"https://api.github.com/repos/{self._repo}/releases/latest"
        try:
            client = self._injected_client or httpx.Client(timeout=self._timeout)
            response = client.get(url)
        except httpx.HTTPError as exc:
            log.info("GitHub Releases fetch failed: %s", exc)
            return None
        if response.status_code != 200:
            log.warning(
                "GitHub Releases returned status=%d body=%r",
                response.status_code,
                response.text[:200],
            )
            return None
        try:
            data = response.json()
        except ValueError:
            log.warning("GitHub Releases returned non-JSON body")
            return None
        if not isinstance(data, dict):
            log.warning("GitHub Releases response is not a JSON object")
            return None
        payload = cast("dict[str, object]", data)
        tag = payload.get("tag_name")
        if not isinstance(tag, str):
            log.warning("GitHub Releases response missing tag_name")
            return None
        wheel_url = _extract_wheel_url(payload)
        return ReleaseInfo(tag_name=tag, wheel_url=wheel_url)


def _extract_wheel_url(payload: dict[str, object]) -> str | None:
    """Find the first asset whose name ends in .whl and return its download URL."""
    assets_raw = payload.get("assets", [])
    if not isinstance(assets_raw, list):
        return None
    for entry in cast("list[object]", assets_raw):
        if not isinstance(entry, dict):
            continue
        asset = cast("dict[str, object]", entry)
        name = asset.get("name")
        url = asset.get("browser_download_url")
        if isinstance(name, str) and name.endswith(".whl") and isinstance(url, str):
            return url
    return None
```

- [ ] **Step 4: Run tests + lint**

```bash
.venv/bin/pytest tests/test_updater_client.py -v --override-ini="addopts="
.venv/bin/ruff check src/nexus/updater/client.py tests/test_updater_client.py
.venv/bin/mypy src/nexus/updater/client.py
.venv/bin/pyright src/nexus/updater/client.py
```

Expected: 7 tests pass; 0 violations; 0 errors.

- [ ] **Step 5: Commit**

```bash
git add src/nexus/updater/client.py tests/test_updater_client.py && git commit -m "feat(updater): GitHubReleasesClient + ReleaseInfo"
```

---

## Task 4: installer.py -- download_wheel + pip_install_wheel

**Files:**
- Create: `src/nexus/updater/installer.py`
- Create: `tests/test_updater_installer.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_updater_installer.py`:

```python
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


def test_download_wheel_writes_file_on_200(tmp_path: Path) -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=b"WHEEL_BYTES"))
    client = httpx.Client(transport=transport)
    path = download_wheel(
        "https://example.com/nexus_sn-2026.06.0-py3-none-any.whl",
        dest_dir=tmp_path,
        httpx_client=client,
    )
    assert path == tmp_path / "nexus_sn-2026.06.0-py3-none-any.whl"
    assert path.read_bytes() == b"WHEEL_BYTES"


def test_download_wheel_raises_on_non_200(tmp_path: Path) -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(404))
    client = httpx.Client(transport=transport)
    with pytest.raises(UpdaterError, match="404"):
        download_wheel(
            "https://example.com/nexus_sn-2026.06.0-py3-none-any.whl",
            dest_dir=tmp_path,
            httpx_client=client,
        )


def test_download_wheel_raises_on_network_error(tmp_path: Path) -> None:
    def raise_error(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nope")

    transport = httpx.MockTransport(raise_error)
    client = httpx.Client(transport=transport)
    with pytest.raises(UpdaterError, match="network"):
        download_wheel(
            "https://example.com/nexus_sn-2026.06.0-py3-none-any.whl",
            dest_dir=tmp_path,
            httpx_client=client,
        )


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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_updater_installer.py -v --override-ini="addopts="
```

Expected: ImportError on `nexus.updater.installer`.

- [ ] **Step 3: Implement installer.py**

Write `src/nexus/updater/installer.py`:

```python
# src/nexus/updater/installer.py
# Download wheel + pip subprocess install.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Download a wheel from a URL, then `pip install --upgrade <wheel>`."""

import logging
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx

from nexus.updater.errors import UpdaterError

log = logging.getLogger(__name__)

__all__ = ["download_wheel", "pip_install_wheel"]


def download_wheel(
    url: str,
    *,
    dest_dir: Path,
    httpx_client: httpx.Client | None = None,
) -> Path:
    """Stream the wheel at ``url`` to ``dest_dir / <filename-from-url>``.

    Args:
        url: HTTPS URL of the wheel.
        dest_dir: Directory to write to (typically a tempfile.TemporaryDirectory).
        httpx_client: Optional pre-built client (for tests). Default: new
            short-lived client.

    Returns:
        Local path to the downloaded wheel.

    Raises:
        UpdaterError: On network failure or non-200 response.
    """
    filename = Path(urlparse(url).path).name
    target = dest_dir / filename
    client = httpx_client or httpx.Client(timeout=30.0)
    try:
        response = client.get(url)
    except httpx.HTTPError as exc:
        raise UpdaterError(f"network error downloading wheel: {exc}") from exc
    if response.status_code != 200:
        raise UpdaterError(
            f"wheel download returned status={response.status_code} url={url}"
        )
    target.write_bytes(response.content)
    log.info("downloaded wheel: %s (%d bytes)", target.name, len(response.content))
    return target


def pip_install_wheel(wheel_path: Path) -> None:
    """Run `<python> -m pip install --upgrade <wheel_path>`.

    Raises:
        UpdaterError: When pip exits non-zero. Includes stderr in the message.
    """
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", str(wheel_path)]
    log.info("running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise UpdaterError(
            f"pip install failed (exit {result.returncode}): {result.stderr.strip()}"
        )
    log.info("pip install succeeded")
```

- [ ] **Step 4: Run tests + lint**

```bash
.venv/bin/pytest tests/test_updater_installer.py -v --override-ini="addopts="
.venv/bin/ruff check src/nexus/updater/installer.py tests/test_updater_installer.py
.venv/bin/mypy src/nexus/updater/installer.py
.venv/bin/pyright src/nexus/updater/installer.py
```

Expected: 5 tests pass; 0 violations; 0 errors.

- [ ] **Step 5: Commit**

```bash
git add src/nexus/updater/installer.py tests/test_updater_installer.py && git commit -m "feat(updater): download_wheel + pip_install_wheel"
```

---

## Task 5: runner.py -- check_and_maybe_update orchestrator + FakeGitHubReleasesClient

**Files:**
- Create: `src/nexus/updater/runner.py`
- Modify: `src/nexus/updater/__init__.py`
- Create: `tests/fakes/fake_github_releases.py`
- Modify: `tests/fakes/__init__.py`
- Create: `tests/test_updater_runner.py`

- [ ] **Step 1: Create FakeGitHubReleasesClient**

Write `tests/fakes/fake_github_releases.py`:

```python
# tests/fakes/fake_github_releases.py
# Test double for GitHubReleasesClient.
# Author: Pierre Grothe
# Date: 2026-05-08
"""FakeGitHubReleasesClient: returns a configured ReleaseInfo or None."""

from dataclasses import dataclass

from nexus.updater.client import ReleaseInfo

__all__ = ["FakeGitHubReleasesClient"]


@dataclass(slots=True)
class FakeGitHubReleasesClient:
    """Returns a pre-built ReleaseInfo (or None) from .fetch_latest()."""

    info: ReleaseInfo | None = None

    def fetch_latest(self) -> ReleaseInfo | None:
        """Return the stored info."""
        return self.info
```

- [ ] **Step 2: Update tests/fakes/__init__.py**

Read the file. Add FakeGitHubReleasesClient in alphabetical order:

```python
# tests/fakes/__init__.py
# Fake implementations used in tests. No mocks anywhere.
# Author: Pierre Grothe
# Date: 2026-05-07
"""Fake connectors and clients for use in tests."""

from tests.fakes.fake_agent_client import FakeAgentClient
from tests.fakes.fake_cache_backend import FakeCacheBackend
from tests.fakes.fake_claude_config import FakeClaudeCodeConfig
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_github_releases import FakeGitHubReleasesClient
from tests.fakes.fake_keychain import FakeKeychainClient
from tests.fakes.fake_sn_client import FakeServiceNowClient

__all__ = [
    "FakeAgentClient",
    "FakeCacheBackend",
    "FakeClaudeCodeConfig",
    "FakeClock",
    "FakeGitHubReleasesClient",
    "FakeKeychainClient",
    "FakeServiceNowClient",
]
```

- [ ] **Step 3: Write the failing tests**

Create `tests/test_updater_runner.py`:

```python
# tests/test_updater_runner.py
# Tests for the auto-update runner orchestration.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for nexus.updater.runner.check_and_maybe_update."""

import os
import subprocess
from pathlib import Path

import httpx
import pytest

from nexus.updater.client import ReleaseInfo
from nexus.updater.runner import check_and_maybe_update
from tests.fakes.fake_github_releases import FakeGitHubReleasesClient


def _patch_runner(
    monkeypatch: pytest.MonkeyPatch,
    *,
    editable: bool,
    current: str | None,
    info: ReleaseInfo | None,
    install_succeeds: bool = True,
) -> dict[str, object]:
    """Wire up monkeypatches for runner internals; return a calls-record dict."""
    from nexus.updater import runner as runner_module

    calls: dict[str, object] = {"execv": None, "exit": None, "install": False}

    monkeypatch.setattr(runner_module, "is_editable_install", lambda: editable)
    monkeypatch.setattr(runner_module, "current_version", lambda: current)
    monkeypatch.setattr(runner_module, "_build_client", lambda: FakeGitHubReleasesClient(info=info))

    def fake_install(wheel_path: Path) -> None:
        calls["install"] = True
        if not install_succeeds:
            from nexus.updater.errors import UpdaterError
            raise UpdaterError("simulated install failure")

    monkeypatch.setattr(runner_module, "pip_install_wheel", fake_install)

    def fake_download(url: str, *, dest_dir: Path, httpx_client: httpx.Client | None = None) -> Path:
        path = dest_dir / "fake.whl"
        path.write_bytes(b"")
        return path

    monkeypatch.setattr(runner_module, "download_wheel", fake_download)

    def fake_execv(path: str, argv: list[str]) -> None:
        calls["execv"] = (path, argv)

    monkeypatch.setattr(os, "execv", fake_execv)

    def fake_exit(code: int) -> None:
        calls["exit"] = code

    monkeypatch.setattr("sys.exit", fake_exit)
    return calls


def test_runner_skips_when_editable_install(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_runner(monkeypatch, editable=True, current="2026.05.1", info=None)
    check_and_maybe_update()
    assert calls["install"] is False
    assert calls["execv"] is None


def test_runner_skips_when_env_var_disables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_AUTO_UPDATE", "0")
    calls = _patch_runner(monkeypatch, editable=False, current="2026.05.1", info=None)
    check_and_maybe_update()
    assert calls["install"] is False


def test_runner_skips_when_current_version_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    info = ReleaseInfo(tag_name="2026.06.0", wheel_url="https://example.com/x.whl")
    calls = _patch_runner(monkeypatch, editable=False, current=None, info=info)
    check_and_maybe_update()
    assert calls["install"] is False


def test_runner_skips_when_github_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_runner(monkeypatch, editable=False, current="2026.05.1", info=None)
    check_and_maybe_update()
    assert calls["install"] is False


def test_runner_skips_when_already_current(monkeypatch: pytest.MonkeyPatch) -> None:
    info = ReleaseInfo(tag_name="2026.05.1", wheel_url="https://example.com/x.whl")
    calls = _patch_runner(monkeypatch, editable=False, current="2026.05.1", info=info)
    check_and_maybe_update()
    assert calls["install"] is False


def test_runner_skips_when_release_lacks_wheel(monkeypatch: pytest.MonkeyPatch) -> None:
    info = ReleaseInfo(tag_name="2026.06.0", wheel_url=None)
    calls = _patch_runner(monkeypatch, editable=False, current="2026.05.1", info=info)
    check_and_maybe_update()
    assert calls["install"] is False


def test_runner_skips_when_tag_is_invalid_version(monkeypatch: pytest.MonkeyPatch) -> None:
    info = ReleaseInfo(tag_name="not-a-version", wheel_url="https://example.com/x.whl")
    calls = _patch_runner(monkeypatch, editable=False, current="2026.05.1", info=info)
    check_and_maybe_update()
    assert calls["install"] is False


def test_runner_installs_and_re_execs_when_newer_version_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    info = ReleaseInfo(tag_name="2026.06.0", wheel_url="https://example.com/x.whl")
    calls = _patch_runner(monkeypatch, editable=False, current="2026.05.1", info=info)
    check_and_maybe_update()
    assert calls["install"] is True
    assert calls["execv"] is not None


def test_runner_continues_when_install_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    info = ReleaseInfo(tag_name="2026.06.0", wheel_url="https://example.com/x.whl")
    calls = _patch_runner(
        monkeypatch, editable=False, current="2026.05.1", info=info, install_succeeds=False
    )
    check_and_maybe_update()
    assert calls["install"] is True
    # Re-exec should NOT happen on install failure -- runner continues with old code
    assert calls["execv"] is None


def test_runner_skips_when_lockfile_held(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulate another nexus invocation holding the lock; runner skips."""
    import fcntl

    info = ReleaseInfo(tag_name="2026.06.0", wheel_url="https://example.com/x.whl")
    calls = _patch_runner(monkeypatch, editable=False, current="2026.05.1", info=info)

    from nexus.updater import runner as runner_module

    lock_path = tmp_path / "update.lock"
    monkeypatch.setattr(runner_module, "_lock_path", lambda: lock_path)
    held_lock = lock_path.open("w")
    fcntl.flock(held_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        check_and_maybe_update()
    finally:
        fcntl.flock(held_lock.fileno(), fcntl.LOCK_UN)
        held_lock.close()
    assert calls["install"] is False
```

- [ ] **Step 4: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_updater_runner.py -v --override-ini="addopts="
```

Expected: ImportError on `nexus.updater.runner`.

- [ ] **Step 5: Implement runner.py**

Write `src/nexus/updater/runner.py`:

```python
# src/nexus/updater/runner.py
# The auto-update orchestrator. Called by the CLI callback before every command.
# Author: Pierre Grothe
# Date: 2026-05-08
"""check_and_maybe_update: runs the version check + install + re-exec.

Never raises. On any failure, logs and returns silently so the user's
command can continue with the current code.
"""

import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from packaging.version import InvalidVersion, parse

from nexus.config.paths import NexusPaths
from nexus.updater.client import GitHubReleasesClient, ReleaseInfo
from nexus.updater.current import current_version, is_editable_install
from nexus.updater.errors import UpdaterError
from nexus.updater.installer import download_wheel, pip_install_wheel

log = logging.getLogger(__name__)

__all__ = ["check_and_maybe_update"]

_ENV_DISABLE = "NEXUS_AUTO_UPDATE"


def check_and_maybe_update() -> None:
    """Entry point invoked by the CLI callback before every command.

    Returns silently on any non-actionable condition; logs and continues
    on any failure. Re-execs the process on successful install.
    """
    if is_editable_install():
        log.debug("editable install detected; skipping auto-update")
        return
    if os.environ.get(_ENV_DISABLE) == "0":
        log.debug("NEXUS_AUTO_UPDATE=0; skipping auto-update")
        return

    current = current_version()
    if current is None:
        log.debug("nexus-sn not installed as a distribution; skipping auto-update")
        return

    lock = _try_acquire_lock()
    if lock is None:
        log.debug("update lockfile held by another process; skipping")
        return

    try:
        _run_update_cycle(current)
    finally:
        _release_lock(lock)


def _run_update_cycle(current: str) -> None:
    """Inner update logic. Caller holds the lock."""
    info = _build_client().fetch_latest()
    if info is None:
        return  # GitHub API failure already logged
    if info.wheel_url is None:
        log.warning("latest release %s has no wheel asset; skipping", info.tag_name)
        return

    try:
        latest_v = parse(info.tag_name)
        current_v = parse(current)
    except InvalidVersion as exc:
        log.warning("could not parse version: %s", exc)
        return

    if latest_v <= current_v:
        log.debug("already on latest version %s", current)
        return

    print(f"NEXUS updating {current} -> {info.tag_name}...", flush=True)
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            wheel_path = download_wheel(info.wheel_url, dest_dir=Path(tmpdir))
            pip_install_wheel(wheel_path)
    except UpdaterError as exc:
        log.error("auto-update failed: %s", exc)
        return

    print(f"NEXUS updated to {info.tag_name}", flush=True)
    _re_exec(info)


def _re_exec(info: ReleaseInfo) -> None:
    """Re-run the user's command with the new code.

    On Linux/macOS: os.execv replaces the process.
    On Windows: subprocess.run + sys.exit (os.execv has shell-prompt quirks).
    """
    try:
        if sys.platform == "win32":
            result = subprocess.run(sys.argv, check=False)
            sys.exit(result.returncode)
        os.execv(sys.argv[0], sys.argv)
    except OSError as exc:
        log.error("could not re-exec after update: %s", exc)
        log.info("update %s installed; please re-run your command", info.tag_name)


def _build_client() -> GitHubReleasesClient:
    """Construct the production GitHubReleasesClient.

    Tests monkeypatch this to inject FakeGitHubReleasesClient.
    """
    return GitHubReleasesClient()


def _lock_path() -> Path:
    """Return the path of the update lockfile.

    Tests monkeypatch this to redirect to tmp_path.
    """
    cache_dir = NexusPaths.from_env().root / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "update.lock"


_LockHandle = tuple[object, object]


def _try_acquire_lock() -> _LockHandle | None:
    """Try to acquire an exclusive lock. Return a handle or None if held.

    Cross-platform: fcntl on POSIX, msvcrt on Windows.
    """
    path = _lock_path()
    handle = path.open("w")
    try:
        if sys.platform == "win32":
            import msvcrt  # noqa: PLC0415  -- Windows-only stdlib

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl  # noqa: PLC0415  -- POSIX-only stdlib

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return (handle, path)


def _release_lock(lock: _LockHandle) -> None:
    """Release the lock acquired by _try_acquire_lock."""
    handle, _ = lock
    try:
        if sys.platform == "win32":
            import msvcrt  # noqa: PLC0415  -- Windows-only stdlib

            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
        else:
            import fcntl  # noqa: PLC0415  -- POSIX-only stdlib

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]
    finally:
        handle.close()  # type: ignore[attr-defined]
```

NOTE: the `# type: ignore` comments above are placeholders -- the project bans `# type: ignore`. The fix is to type the lock handle precisely (not `_LockHandle`-as-tuple-of-objects). Replace with:

```python
_LockHandle = tuple[io.IOBase, Path]
```

(import `io` at top) so `handle.close()` and `handle.fileno()` resolve cleanly without ignores. If pyright still complains about `fcntl.flock(handle.fileno(), ...)` where `handle.fileno()` returns `int` (which it does on `io.IOBase`), the call is well-typed and no ignore is needed.

If you find any `# type: ignore` is actually required, escalate -- the project bans them. Recheck the type narrowing.

- [ ] **Step 6: Update __init__.py**

Replace:

```python
# src/nexus/updater/__init__.py
# NEXUS self-update package (ADR-020).
# Author: Pierre Grothe
# Date: 2026-05-08
"""NEXUS auto-updater.

check_and_maybe_update() is invoked by the CLI callback before every command.
On non-editable installs, it queries the GitHub Releases API for a newer
version, downloads the wheel, runs pip install, and re-execs the user's
command with the new code.
"""

from nexus.updater.current import current_version, is_editable_install
from nexus.updater.errors import UpdaterError
from nexus.updater.runner import check_and_maybe_update

__all__ = [
    "UpdaterError",
    "check_and_maybe_update",
    "current_version",
    "is_editable_install",
]
```

- [ ] **Step 7: Run tests + lint**

```bash
.venv/bin/pytest tests/test_updater_runner.py -v --override-ini="addopts="
.venv/bin/ruff check src/nexus/updater/runner.py tests/test_updater_runner.py
.venv/bin/mypy src/nexus/updater/runner.py
.venv/bin/pyright src/nexus/updater/runner.py
```

Expected: 10 tests pass; 0 violations; 0 errors. If pyright complains about
the lock-handle types, refine the `_LockHandle` type alias to `tuple[io.IOBase, Path]`
and add `import io` at the top. Do NOT add `# type: ignore`.

- [ ] **Step 8: Commit**

```bash
git add src/nexus/updater/runner.py src/nexus/updater/__init__.py tests/fakes/fake_github_releases.py tests/fakes/__init__.py tests/test_updater_runner.py && git commit -m "feat(updater): check_and_maybe_update orchestrator + FakeGitHubReleasesClient"
```

---

## Task 6: CLI integration -- callback hook + `nexus update` command

**Files:**
- Modify: `src/nexus/cli.py`

- [ ] **Step 1: Read the current cli.py**

```bash
grep -n "@app.callback\|^def main\|^def update\|^@app.command" src/nexus/cli.py | head -10
```

Note: the existing `main()` callback runs `_configure_logging`. Add `check_and_maybe_update()` after it. Add a new `update` command alongside `status`/`reauth`/etc.

- [ ] **Step 2: Add the imports**

In `src/nexus/cli.py`, add after the existing nexus imports:

```python
from nexus.updater import (
    check_and_maybe_update,
    current_version,
)
from nexus.updater.client import GitHubReleasesClient
```

- [ ] **Step 3: Update the @app.callback() to invoke check_and_maybe_update**

Find the existing `@app.callback()` block and modify the body:

```python
@app.callback()
def main(
    log_level: Annotated[str, typer.Option("--log-level", envvar="NEXUS_LOG_LEVEL")] = "WARNING",
) -> None:
    """NEXUS -- ServiceNow AI architect agent."""
    _configure_logging(log_level)
    check_and_maybe_update()
```

- [ ] **Step 4: Add the `nexus update` command**

Add this command (a sensible spot is right after `reauth`):

```python
@app.command()
def update(
    check_only: Annotated[
        bool,
        typer.Option("--check-only", help="Only report; do not install"),
    ] = False,
) -> None:
    """Manually check for updates (and install unless --check-only).

    Plain `nexus update` triggers the same auto-update path that runs on
    every command. With --check-only, just report whether a newer version
    is available without installing.
    """
    current = current_version()
    if current is None:
        console.print("nexus-sn is not installed as a distribution; cannot check.")
        return

    info = GitHubReleasesClient().fetch_latest()
    if info is None:
        console.print("Could not reach GitHub. No update info available.")
        return

    from packaging.version import InvalidVersion, parse  # noqa: PLC0415

    try:
        if parse(info.tag_name) <= parse(current):
            console.print(f"Up to date ({current})")
            return
    except InvalidVersion:
        console.print(f"Latest tag {info.tag_name!r} is not a valid version; skipping")
        return

    if check_only:
        console.print(f"Update available: {current} -> {info.tag_name}")
        return

    # Trigger the full auto-update path; it handles everything.
    check_and_maybe_update()
```

Note: the `from packaging.version import ...` is inside the function intentionally to keep the dependency lazy. If ruff PLC0415 fires, accept the noqa -- the import is genuinely deferred to keep startup time low for non-update commands. (Consider hoisting to module level if PLC0415 is non-negotiable; only ~20us cost.)

- [ ] **Step 5: Run cli tests + lint**

```bash
.venv/bin/pytest tests/test_cli_status.py -v --override-ini="addopts="
.venv/bin/ruff check src/nexus/cli.py
.venv/bin/mypy src/nexus/cli.py
.venv/bin/pyright src/nexus/cli.py
```

Expected: existing CLI tests still pass; 0 violations; 0 errors. If PLC0415 fires on the deferred packaging import, hoist it to module level.

- [ ] **Step 6: Verify the auto-updater is invoked**

Manual check: in the dev environment (editable install), run `nexus status`. The auto-updater should trigger and silently skip (DEBUG log). With `NEXUS_LOG_LEVEL=DEBUG nexus status`, you should see `editable install detected; skipping auto-update`.

```bash
NEXUS_LOG_LEVEL=DEBUG .venv/bin/nexus status 2>&1 | grep "editable install" || echo "DEBUG line not found"
```

Expected: the DEBUG line is logged (auto-updater ran and skipped).

- [ ] **Step 7: Commit**

```bash
git add src/nexus/cli.py && git commit -m "feat(cli): wire auto-updater into callback + add nexus update command"
```

---

## Task 7: Rewrite release.yml to GitHub-Releases-only

**Files:**
- Modify: `.github/workflows/release.yml`

- [ ] **Step 1: Replace the workflow**

Write `.github/workflows/release.yml`:

```yaml
name: Release

on:
  push:
    tags:
      - "[0-9][0-9][0-9][0-9].[0-9][0-9].[0-9]*"

jobs:
  publish:
    runs-on: ubuntu-latest
    permissions:
      contents: write  # required for gh release create

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.14"

      - name: Install Poetry
        uses: snok/install-poetry@v1

      - name: Build wheel
        run: poetry build

      - name: Create GitHub Release with wheel
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gh release create "${GITHUB_REF_NAME}" \
            --title "${GITHUB_REF_NAME}" \
            --notes "Automated release for ${GITHUB_REF_NAME}." \
            ./dist/*.whl
```

Key changes:
- Drops `poetry publish` and `POETRY_PYPI_TOKEN_PYPI`.
- Adds `permissions: contents: write` so the default `GITHUB_TOKEN` can create a release.
- Uses `gh release create` to attach the wheel as an asset.
- Bumps Python to 3.14 (matches the project's required version).

- [ ] **Step 2: Validate the YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml'))"
```

Expected: no error.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release.yml && git commit -m "ci(release): build wheel + gh release create (drop PyPI publish)"
```

---

## Task 8: ADR-020 + governance + ratchet + decisions

**Files:**
- Create: `.primer/adr/ADR-020-self-update.md`
- Modify: `.primer/governance.md`
- Modify: `.primer/decisions.md`
- Modify: `.primer/patterns.md`
- Modify: `.ratchet.json`

- [ ] **Step 1: Generate coverage numbers**

```bash
.venv/bin/pytest --cov=nexus --cov-report=json --cov-fail-under=0 -q --override-ini="addopts="
.venv/bin/python -c "
import json
data = json.load(open('coverage.json'))
for path, info in sorted(data['files'].items()):
    if 'updater' in path or '/cli.py' in path:
        s = info['summary']
        print(path, '-> covered=' + str(s['covered_lines']), 'total=' + str(s['num_statements']))
"
```

Note the numbers for: `nexus/updater/__init__.py`, `nexus/updater/errors.py`, `nexus/updater/current.py`, `nexus/updater/client.py`, `nexus/updater/installer.py`, `nexus/updater/runner.py`, plus updated `nexus/cli.py`.

- [ ] **Step 2: Update .ratchet.json**

Read the file. Add 6 new entries (using Step 1 numbers):

```json
    "nexus.updater": {"covered_lines": <N>, "total_lines": <N>},
    "nexus.updater.client": {"covered_lines": <N>, "total_lines": <N>},
    "nexus.updater.current": {"covered_lines": <N>, "total_lines": <N>},
    "nexus.updater.errors": {"covered_lines": <N>, "total_lines": <N>},
    "nexus.updater.installer": {"covered_lines": <N>, "total_lines": <N>},
    "nexus.updater.runner": {"covered_lines": <N>, "total_lines": <N>},
```

Update `nexus.cli` to its new numbers.

- [ ] **Step 3: Create ADR-020**

Write `.primer/adr/ADR-020-self-update.md`:

```markdown
# ADR-020: NEXUS auto-update from GitHub Releases

**Status:** accepted
**Date:** 2026-05-08
**Enforcement:** none (architectural)

## Context

The user's original three-feature ask was caching, tier detection, and
auto-update (Claude-Code style). The first two shipped (ADR-017, ADR-018).
Auto-update was deferred initially because there was no PyPI release to
update against. This ADR closes that gap.

## Decision

Add a Layer 7 `src/nexus/updater/` package with focused modules:
  - errors.py: UpdaterError (single exception, never escapes the runner)
  - current.py: current_version + is_editable_install via importlib.metadata
  - client.py: GitHubReleasesClient (httpx-based, never raises)
  - installer.py: download_wheel + pip_install_wheel (subprocess pip)
  - runner.py: check_and_maybe_update orchestrator

The CLI callback (@app.callback) invokes check_and_maybe_update before
every command. On non-editable installs, the runner:
  1. Acquires an exclusive flock on ~/.nexus/cache/update.lock.
  2. Queries /repos/pierregrothe/nexus-sn/releases/latest.
  3. If a newer version is available, downloads the wheel.
  4. Runs `python -m pip install --upgrade <wheel>`.
  5. os.execv to re-run the user's command with the new code (Linux/macOS).
     subprocess.run + sys.exit on Windows (os.execv has shell quirks).

Editable installs (pip install -e .) skip silently. NEXUS_AUTO_UPDATE=0
also skips. Any failure (network, non-200, install error, lock held)
falls back to running the current code with a log entry.

The release pipeline is rewritten: the existing PyPI-publishing workflow
is replaced with `gh release create` that attaches the built wheel to a
GitHub Release. PyPI publication is out of scope for v1 and re-enabled
later if a use case emerges.

## Consequences

  - Every nexus invocation makes one GitHub API call (~200-500ms latency,
    3s timeout). User explicitly chose this over daily-cached or
    manual-only checks.
  - First non-Pierre install (via wheel) gets auto-update behavior
    immediately.
  - Pierre's dev environment (pip install -e .) is unaffected.
  - Rollback if a release is bad: NEXUS_AUTO_UPDATE=0 + manual
    `pip install nexus-sn==<good-version>`.
  - Wheel hash verification is skipped for v1 (HTTPS is sufficient
    against MITM; a compromised repo bypasses any hash check anyway).
  - Adds packaging >= 23 as an explicit runtime dep (was transitive).

Spec: docs/superpowers/specs/2026-05-08-auto-update-design.md
Plan: docs/superpowers/plans/2026-05-08-auto-update.md
```

- [ ] **Step 4: Update .primer/governance.md ADR catalog**

Append to the catalog table:

```markdown
| 020 | NEXUS auto-update from GitHub Releases | none | accepted |
```

- [ ] **Step 5: Update .primer/patterns.md layer rule**

Add `updater` as Layer 7 in the dependency listing. Find the layer rule block and add:

```
  updater -> cache, config, capabilities  (Layer 7)
```

- [ ] **Step 6: Append to .primer/decisions.md**

```markdown


---

### 2026-05-08 -- NEXUS auto-update from GitHub Releases (ADR-020)

**Status:** accepted

**Context:** Last of the user's original three-feature ask. Earlier deferral
was correct -- no PyPI release existed to update against. This PR closes the
gap by switching the release pipeline to GitHub-Releases-only (no PyPI yet)
and implementing the auto-update logic.

**Decision:** Layer 7 `src/nexus/updater/` package with check_and_maybe_update
orchestrator invoked by the CLI callback. Every-launch GitHub API call,
wheel download + pip install + os.execv re-run on update. Editable installs
detected via importlib.metadata.distribution().origin.dir_info.editable;
skipped silently. NEXUS_AUTO_UPDATE=0 escape hatch.

**Consequences:** ~200-500ms per launch (3s timeout). pip install + re-exec
on update (~5-10s one-time). Rollback via env var + manual pip downgrade.
Wheel hash verification skipped for v1 (HTTPS sufficient). PyPI publication
deferred. Spec at docs/superpowers/specs/2026-05-08-auto-update-design.md.
```

- [ ] **Step 7: Run pre-commit**

```bash
.venv/bin/pre-commit run --all-files 2>&1 | tail -8
```

Expected: 6/6 hooks pass.

- [ ] **Step 8: Commit**

```bash
git add .ratchet.json .primer/ && git commit -m "docs: ADR-020 NEXUS auto-update + governance + ratchet"
```

---

## Task 9: Push + open PR

- [ ] **Step 1: Push the branch**

```bash
git push -u origin feat/auto-update
```

- [ ] **Step 2: Open the PR (using the existing PR template)**

The repo's PR template will pre-populate. Override with explicit content:

```bash
gh pr create --title "feat: NEXUS auto-update from GitHub Releases (ADR-020)" --body "$(cat <<'EOF'
## Summary

- New `src/nexus/updater/` package: every `nexus` invocation checks GitHub Releases for a newer version, downloads the wheel, `pip install --upgrade`s, and re-execs.
- Editable installs (`pip install -e .`) skip silently. `NEXUS_AUTO_UPDATE=0` is an escape hatch.
- New `nexus update [--check-only]` command for explicit control.
- `release.yml` rewritten: builds the wheel and creates a GitHub Release with it (drops PyPI publish; was broken-by-default without PYPI_TOKEN).

## Test plan

- [x] Unit tests added: ~30 tests across 4 test files (current, client, installer, runner)
- [x] All 6 pre-commit hooks pass (black, ruff, mypy, pyright, semgrep, pytest)
- [x] Manual: `NEXUS_LOG_LEVEL=DEBUG nexus status` logs "editable install detected; skipping auto-update"

## Pre-merge gates (ADR-019)

- [x] `/simplify` -- run after this lands; will produce a follow-up if needed
- [x] ADR-020 added to governance.md catalog
- [x] New public API has file headers + Google docstrings

## Why

Closes the third item from the user's original three-feature ask. The first two shipped (ADR-017 caching, ADR-018 tier detection). Auto-update was deferred earlier because there was no release to update against; this PR closes that gap.

Spec: `docs/superpowers/specs/2026-05-08-auto-update-design.md`
Plan: `docs/superpowers/plans/2026-05-08-auto-update.md`
ADR-020: `.primer/adr/ADR-020-self-update.md`

## Out of scope (deferred)

- PyPI publication (separate PR if/when needed).
- `nexus update --pin <version>` rollback support.
- Wheel hash verification (HTTPS deemed sufficient for v1).
- Pre-release / beta channels.

## Post-merge manual step

After merge: tag `2026.05.1` on main (`git tag 2026.05.1 && git push --tags`). The new release.yml will create the first GitHub Release with the wheel attached. Subsequent version bumps + tags will be auto-installed by future NEXUS launches.

Generated with Claude Code
EOF
)"
```

Expected: PR URL printed.

---

## Self-Review Notes

- All 9 tasks have explicit code + commands. The only `<N>` placeholder is in Task 8 Step 2 (ratchet baselines); Step 1 generates them.
- Type consistency:
  - `ReleaseInfo(tag_name, wheel_url)` is consistent across Tasks 3, 5, 6.
  - `check_and_maybe_update()` (no args) is consistent across Tasks 5, 6.
  - `download_wheel(url, *, dest_dir, httpx_client)` and `pip_install_wheel(wheel_path)` are consistent across Tasks 4, 5.
  - `current_version() -> str | None` and `is_editable_install() -> bool` are consistent across Tasks 2, 5, 6.
- Spec coverage:
  - Architecture file map (spec) -> Tasks 1-7 cover every entry.
  - Components (spec) -> Tasks 2-5 implement.
  - Data flow (spec) -> Task 5 runner orchestrates; Task 6 wires CLI.
  - Error handling + security (spec) -> Task 5 runner handles all the cases.
  - Testing (spec) -> Tasks 2-5 each include their tests.
  - Migration / cutover (spec) -> Task 7 (release.yml) + Task 9's PR description (manual tag step).
- Risk: Task 5 runner.py uses `# type: ignore` placeholders that the project bans. Step 7 of Task 5 explicitly flags this and tells the engineer to refine the `_LockHandle` type alias instead. If the engineer can't make pyright clean without ignores, escalate -- the project policy is strict.
- Risk: Task 6 has a deferred `from packaging.version import ...` that ruff PLC0415 will flag. The plan flags this and suggests hoisting to module level.
