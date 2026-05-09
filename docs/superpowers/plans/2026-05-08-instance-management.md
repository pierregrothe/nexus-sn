# Instance Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the `src/nexus/instances/` package -- OAuth2 token lifecycle, per-instance disk registry, artifact snapshot collection, and a `nexus instance` CLI sub-app with register/delete/list/connect/refresh/status/use commands.

**Architecture:** New layer-4 package alongside `connectors/`. `SNOAuthClient` owns token exchange and keychain I/O. `InstanceRegistry` owns the `~/.nexus/instances/<profile>/` directory tree. `InstanceScanner` fires four concurrent async REST calls to collect the artifact inventory. The CLI wires them together; no injection framework required -- `NEXUS_CONFIG_PATH` env var allows test isolation.

**Tech Stack:** httpx (existing), keyring via KeychainClient (existing), Pydantic frozen models (existing), asyncio.gather for parallel REST, typer sub-app for CLI.

---

## File Map

**Create:**
```
src/nexus/instances/__init__.py
src/nexus/instances/errors.py
src/nexus/instances/models.py
src/nexus/instances/oauth.py
src/nexus/instances/registry.py
src/nexus/instances/scanner.py
tests/fakes/fake_http_transport.py
tests/fakes/fake_instance_registry.py
tests/test_instances_models.py
tests/test_instances_oauth.py
tests/test_instances_registry.py
tests/test_instances_scanner.py
tests/test_cli_instance.py
```

**Modify:**
```
src/nexus/config/paths.py        -- add instances_dir + instance_dir()
src/nexus/config/settings.py     -- remove InstanceProfile, simplify InstancesConfig
src/nexus/auth/__init__.py       -- remove SNAuth export
src/nexus/auth/servicenow.py     -- mark deprecated (keep file, add deprecation warning)
src/nexus/cli.py                 -- add instance_app Typer sub-app
tests/fakes/__init__.py          -- add FakeInstanceRegistry + FakeHttpTransport
tests/test_config.py             -- remove InstanceProfile references
.ratchet.json                    -- add new module baselines
```

---

## Task 1: errors.py and models.py

**Files:**
- Create: `src/nexus/instances/errors.py`
- Create: `src/nexus/instances/models.py`
- Test: `tests/test_instances_models.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_instances_models.py
# Tests for nexus.instances.errors and nexus.instances.models.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for instance management data models and errors."""

from datetime import UTC, datetime, timedelta

import pytest

from nexus.instances.errors import (
    InstanceNotFoundError,
    OAuthError,
    SnapshotError,
    TokenExpiredError,
)
from nexus.instances.models import (
    ArtifactRecord,
    InstanceMeta,
    InstanceSnapshot,
    SnapshotCounts,
)


def test_instance_not_found_error_message_contains_profile() -> None:
    err = InstanceNotFoundError("dev12345")
    assert "dev12345" in str(err)
    assert err.profile == "dev12345"


def test_oauth_error_message_contains_description() -> None:
    err = OAuthError("invalid_grant")
    assert "invalid_grant" in str(err)


def test_token_expired_error_message_contains_profile() -> None:
    err = TokenExpiredError("dev12345")
    assert "dev12345" in str(err)
    assert err.profile == "dev12345"


def test_snapshot_error_stores_table_and_status() -> None:
    err = SnapshotError("sys_script", 403)
    assert "sys_script" in str(err)
    assert "403" in str(err)
    assert err.table == "sys_script"
    assert err.status_code == 403


def test_instance_meta_create_sets_timestamps() -> None:
    meta = InstanceMeta.create(
        profile="dev12345",
        url="https://dev12345.service-now.com",
        username="admin",
        client_id="client-123",
        sn_version="Xanadu",
        sn_build="04-01-2025",
        instance_name="dev12345",
        token_expires_in=1800,
    )
    assert meta.profile == "dev12345"
    assert meta.sn_version == "Xanadu"
    delta = meta.token_expires_at - meta.registered_at
    assert abs(delta.total_seconds() - 1800) < 2


def test_instance_meta_create_registered_equals_last_connected() -> None:
    meta = InstanceMeta.create(
        profile="dev12345",
        url="https://dev12345.service-now.com",
        username="admin",
        client_id="client-123",
        sn_version="Xanadu",
        sn_build="04-01-2025",
        instance_name="dev12345",
        token_expires_in=1800,
    )
    assert meta.registered_at == meta.last_connected_at


def test_instance_snapshot_counts_returns_totals() -> None:
    record = ArtifactRecord(
        sys_id="abc",
        name="Test",
        active=True,
        updated_on=datetime.now(UTC),
        is_custom=True,
    )
    snapshot = InstanceSnapshot(
        captured_at=datetime.now(UTC),
        sn_version="Xanadu",
        ai_skills=[record],
        flows=[record, record],
    )
    counts = snapshot.counts
    assert counts.ai_skills == 1
    assert counts.flows == 2
    assert counts.business_rules == 0
    assert counts.script_includes == 0


def test_artifact_record_extra_accepts_mixed_types() -> None:
    record = ArtifactRecord(
        sys_id="abc",
        name="Test",
        active=True,
        updated_on=datetime.now(UTC),
        is_custom=False,
        extra={"skill_type": "now_assist", "client_callable": False, "order": 100},
    )
    assert record.extra["skill_type"] == "now_assist"
    assert record.extra["client_callable"] is False
    assert record.extra["order"] == 100
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_instances_models.py -v --no-cov
```
Expected: `ModuleNotFoundError: No module named 'nexus.instances'`

- [ ] **Step 3: Create errors.py**

```python
# src/nexus/instances/errors.py
# Error hierarchy for instance management.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Instance management errors."""

__all__ = [
    "InstanceError",
    "InstanceNotFoundError",
    "OAuthError",
    "SnapshotError",
    "TokenExpiredError",
]


class InstanceError(Exception):
    """Base class for all instance management errors."""


class InstanceNotFoundError(InstanceError):
    """Raised when a profile directory does not exist in the registry."""

    def __init__(self, profile: str) -> None:
        """Initialize with the missing profile name."""
        super().__init__(
            f"Instance {profile!r} not found. "
            f"Run 'nexus instance register {profile}'."
        )
        self.profile = profile


class OAuthError(InstanceError):
    """Raised when OAuth token exchange or refresh fails."""

    def __init__(self, message: str) -> None:
        """Initialize with the OAuth error description."""
        super().__init__(f"OAuth error: {message}")


class TokenExpiredError(InstanceError):
    """Raised when the refresh token has exceeded its 100-day TTL."""

    def __init__(self, profile: str) -> None:
        """Initialize with the profile whose token expired."""
        super().__init__(
            f"Refresh token for {profile!r} has expired. "
            f"Run 'nexus instance connect {profile}' to re-authenticate."
        )
        self.profile = profile


class SnapshotError(InstanceError):
    """Raised when a REST call fails during instance refresh."""

    def __init__(self, table: str, status_code: int) -> None:
        """Initialize with the failing table and HTTP status code."""
        super().__init__(
            f"Failed to snapshot table {table!r}: HTTP {status_code}"
        )
        self.table = table
        self.status_code = status_code
```

- [ ] **Step 4: Create models.py**

```python
# src/nexus/instances/models.py
# Pydantic models for per-instance metadata and snapshots.
# Author: Pierre Grothe
# Date: 2026-05-08
"""InstanceMeta, InstanceSnapshot, ArtifactRecord, SnapshotCounts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["ArtifactRecord", "InstanceMeta", "InstanceSnapshot", "SnapshotCounts"]

_FROZEN = ConfigDict(frozen=True)


class SnapshotCounts(BaseModel):
    """Artifact counts stored in meta.json for quick display."""

    model_config = _FROZEN

    ai_skills: int = 0
    flows: int = 0
    business_rules: int = 0
    script_includes: int = 0


class InstanceMeta(BaseModel):
    """Static metadata and OAuth display fields for a registered SN instance."""

    model_config = _FROZEN

    profile: str
    url: str
    username: str
    client_id: str
    sn_version: str
    sn_build: str
    instance_name: str
    registered_at: datetime
    last_connected_at: datetime
    token_expires_at: datetime
    snapshot_counts: SnapshotCounts = Field(default_factory=SnapshotCounts)

    @classmethod
    def create(
        cls,
        *,
        profile: str,
        url: str,
        username: str,
        client_id: str,
        sn_version: str,
        sn_build: str,
        instance_name: str,
        token_expires_in: int,
    ) -> InstanceMeta:
        """Create a fresh InstanceMeta at registration time.

        Args:
            profile: Profile name (e.g. 'dev12345').
            url: Full instance URL including scheme.
            username: ServiceNow login username.
            client_id: OAuth application client_id (not a secret).
            sn_version: SN version string (e.g. 'Xanadu').
            sn_build: SN build string.
            instance_name: SN instance name.
            token_expires_in: Seconds until the access token expires.

        Returns:
            InstanceMeta with registered_at and last_connected_at set to now.
        """
        now = datetime.now(UTC)
        return cls(
            profile=profile,
            url=url,
            username=username,
            client_id=client_id,
            sn_version=sn_version,
            sn_build=sn_build,
            instance_name=instance_name,
            registered_at=now,
            last_connected_at=now,
            token_expires_at=now + timedelta(seconds=token_expires_in),
        )


class ArtifactRecord(BaseModel):
    """A single artifact entry in the instance snapshot."""

    model_config = _FROZEN

    sys_id: str
    name: str
    active: bool
    updated_on: datetime
    is_custom: bool
    extra: dict[str, str | bool | int] = Field(default_factory=dict)


class InstanceSnapshot(BaseModel):
    """Full artifact inventory captured by InstanceScanner."""

    model_config = _FROZEN

    captured_at: datetime
    sn_version: str
    ai_skills: list[ArtifactRecord] = Field(default_factory=list)
    flows: list[ArtifactRecord] = Field(default_factory=list)
    business_rules: list[ArtifactRecord] = Field(default_factory=list)
    script_includes: list[ArtifactRecord] = Field(default_factory=list)

    @property
    def counts(self) -> SnapshotCounts:
        """Return artifact counts for storing in meta.json.

        Returns:
            SnapshotCounts derived from this snapshot's list lengths.
        """
        return SnapshotCounts(
            ai_skills=len(self.ai_skills),
            flows=len(self.flows),
            business_rules=len(self.business_rules),
            script_includes=len(self.script_includes),
        )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_instances_models.py -v --no-cov
```
Expected: 8 PASSED

- [ ] **Step 6: Commit**

```bash
git add src/nexus/instances/errors.py src/nexus/instances/models.py tests/test_instances_models.py
git commit -m "feat(instances): errors and data models"
```

---

## Task 2: NexusPaths and InstancesConfig updates

**Files:**
- Modify: `src/nexus/config/paths.py:61-102`
- Modify: `src/nexus/config/settings.py:19-56`
- Modify: `tests/test_config.py:17-61`

- [ ] **Step 1: Write failing test for instances_dir**

Add this test to `tests/test_config.py`:

```python
def test_nexus_paths_instances_dir_under_root(nexus_paths: NexusPaths) -> None:
    assert nexus_paths.instances_dir == nexus_paths.root / "instances"


def test_nexus_paths_instance_dir_includes_profile(nexus_paths: NexusPaths) -> None:
    assert nexus_paths.instance_dir("dev12345") == nexus_paths.root / "instances" / "dev12345"


def test_nexus_paths_ensure_dirs_creates_instances_dir(nexus_paths: NexusPaths) -> None:
    nexus_paths.ensure_dirs()
    assert nexus_paths.instances_dir.is_dir()
```

Run: `pytest tests/test_config.py::test_nexus_paths_instances_dir_under_root -v --no-cov`
Expected: FAIL with `AttributeError: 'NexusPaths' object has no attribute 'instances_dir'`

- [ ] **Step 2: Add instances_dir to paths.py**

In `src/nexus/config/paths.py`, add after line 88 (after `cache_dir` property):

```python
    @property
    def instances_dir(self) -> Path:
        """Per-instance metadata and snapshot directories."""
        return self.root / "instances"

    def instance_dir(self, profile: str) -> Path:
        """Directory for a specific instance profile.

        Args:
            profile: Instance profile name.

        Returns:
            Path to the per-instance directory under instances_dir.
        """
        return self.instances_dir / profile
```

Also add `self.instances_dir` to the loop in `ensure_dirs()` (currently at line 93-101). The full updated loop:

```python
    def ensure_dirs(self) -> None:
        """Create all runtime directories if they do not exist."""
        for path in (
            self.root,
            self.templates_dir,
            self.reports_dir,
            self.jobs_dir,
            self.logs_dir,
            self.cache_dir,
            self.instances_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
        log.debug("runtime directories ensured under %s", self.root)
```

- [ ] **Step 3: Run paths tests**

```bash
pytest tests/test_config.py -v --no-cov -k "paths"
```
Expected: all paths tests PASS including the 3 new ones.

- [ ] **Step 4: Update settings.py -- remove InstanceProfile, simplify InstancesConfig**

Remove the `InstanceProfile` class (lines 31-43) entirely. Update `InstancesConfig` to:

```python
class InstancesConfig(BaseModel):
    """ServiceNow instance registry.

    Attributes:
        default: Name of the default profile. The profile directory under
            ~/.nexus/instances/ is the authoritative registry.
    """

    model_config = ConfigDict(frozen=True)

    default: str = ""
```

Update `__all__` -- remove `"InstanceProfile"`:

```python
__all__ = [
    "AuthConfig",
    "CapabilitiesConfig",
    "InstancesConfig",
    "NexusConfig",
    "PreferencesConfig",
]
```

- [ ] **Step 5: Fix test_config.py**

In `tests/test_config.py`:

1. Change the import on line 17 from:
   ```python
   from nexus.config.settings import AuthConfig, InstanceProfile, NexusConfig
   ```
   To:
   ```python
   from nexus.config.settings import AuthConfig, InstancesConfig, NexusConfig
   ```

2. Replace `test_nexus_config_default_has_empty_instances` (lines 41-44):
   ```python
   def test_nexus_config_default_has_empty_instances() -> None:
       config = NexusConfig.default()
       assert config.instances.default == ""
   ```

3. Remove `test_instance_profile_stores_url_and_username` (lines 58-61) entirely.

- [ ] **Step 6: Run all config tests**

```bash
pytest tests/test_config.py -v --no-cov
```
Expected: all PASS (one fewer test than before after removing InstanceProfile test).

- [ ] **Step 7: Commit**

```bash
git add src/nexus/config/paths.py src/nexus/config/settings.py tests/test_config.py
git commit -m "feat(instances): add instances_dir to paths, simplify InstancesConfig"
```

---

## Task 3: SNOAuthClient

**Files:**
- Create: `src/nexus/instances/oauth.py`
- Create: `tests/fakes/fake_http_transport.py`
- Test: `tests/test_instances_oauth.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_instances_oauth.py
# Tests for SNOAuthClient token exchange and refresh.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for nexus.instances.oauth."""

from datetime import UTC, datetime, timedelta

import pytest

from nexus.auth.errors import AuthError
from nexus.instances.errors import OAuthError, TokenExpiredError
from nexus.instances.oauth import SNOAuthClient, TokenResponse
from tests.fakes import FakeKeychainClient
from tests.fakes.fake_http_transport import FakeOAuthTransport


def _client(
    keychain: FakeKeychainClient | None = None,
    transport: FakeOAuthTransport | None = None,
) -> SNOAuthClient:
    return SNOAuthClient(
        profile="dev12345",
        url="https://dev12345.service-now.com",
        client_id="client-123",
        username="admin",
        keychain=keychain or FakeKeychainClient(),
        transport=transport or FakeOAuthTransport(),
    )


def test_sn_oauth_client_exchange_returns_token_response() -> None:
    transport = FakeOAuthTransport(access_token="tok", refresh_token="ref", expires_in=1800)
    response = _client(transport=transport).exchange("secret", "password")
    assert isinstance(response, TokenResponse)
    assert response.access_token == "tok"
    assert response.expires_in == 1800


def test_sn_oauth_client_exchange_stores_all_three_keychain_entries() -> None:
    keychain = FakeKeychainClient()
    transport = FakeOAuthTransport(access_token="tok", refresh_token="ref")
    _client(keychain=keychain, transport=transport).exchange("secret", "password")
    assert keychain.get("sn-dev12345", "access-token") == "tok"
    assert keychain.get("sn-dev12345", "refresh-token") == "ref"
    assert keychain.get("sn-dev12345", "client-secret") == "secret"


def test_sn_oauth_client_exchange_raises_oauth_error_on_failure() -> None:
    transport = FakeOAuthTransport(status_code=400, error_description="bad credentials")
    with pytest.raises(OAuthError, match="bad credentials"):
        _client(transport=transport).exchange("bad-secret", "password")


def test_sn_oauth_client_get_bearer_token_returns_existing_when_valid() -> None:
    keychain = FakeKeychainClient({("sn-dev12345", "access-token"): "existing-token"})
    future = datetime.now(UTC) + timedelta(hours=1)
    token, expiry = _client(keychain=keychain).get_bearer_token(future)
    assert token == "existing-token"
    assert expiry == future


def test_sn_oauth_client_get_bearer_token_refreshes_when_near_expiry() -> None:
    keychain = FakeKeychainClient(
        {
            ("sn-dev12345", "client-secret"): "secret",
            ("sn-dev12345", "refresh-token"): "old-refresh",
        }
    )
    transport = FakeOAuthTransport(access_token="new-tok", refresh_token="new-ref", expires_in=1800)
    near_expiry = datetime.now(UTC) + timedelta(minutes=2)
    token, new_expiry = _client(keychain=keychain, transport=transport).get_bearer_token(near_expiry)
    assert token == "new-tok"
    assert keychain.get("sn-dev12345", "access-token") == "new-tok"
    assert new_expiry > near_expiry


def test_sn_oauth_client_get_bearer_token_raises_token_expired_on_invalid_grant() -> None:
    keychain = FakeKeychainClient(
        {
            ("sn-dev12345", "client-secret"): "secret",
            ("sn-dev12345", "refresh-token"): "expired-ref",
        }
    )
    transport = FakeOAuthTransport(status_code=400, error_description="invalid_grant")
    near_expiry = datetime.now(UTC) + timedelta(minutes=2)
    with pytest.raises(TokenExpiredError):
        _client(keychain=keychain, transport=transport).get_bearer_token(near_expiry)


def test_sn_oauth_client_delete_tokens_removes_all_keychain_entries() -> None:
    keychain = FakeKeychainClient(
        {
            ("sn-dev12345", "client-secret"): "s",
            ("sn-dev12345", "access-token"): "a",
            ("sn-dev12345", "refresh-token"): "r",
        }
    )
    _client(keychain=keychain).delete_tokens()
    with pytest.raises(AuthError):
        keychain.get("sn-dev12345", "access-token")
```

Run: `pytest tests/test_instances_oauth.py -v --no-cov`
Expected: FAIL with `ModuleNotFoundError: No module named 'nexus.instances.oauth'`

- [ ] **Step 2: Create FakeOAuthTransport**

```python
# tests/fakes/fake_http_transport.py
# Fake synchronous httpx transport for OAuth tests.
# Author: Pierre Grothe
# Date: 2026-05-08
"""FakeOAuthTransport: returns canned OAuth token responses without HTTP."""

import httpx

__all__ = ["FakeOAuthTransport"]


class FakeOAuthTransport(httpx.BaseTransport):
    """Returns a canned /oauth_token.do response for SNOAuthClient tests.

    Args:
        access_token: Token to return on success.
        refresh_token: Refresh token to return on success.
        expires_in: Token lifetime in seconds.
        status_code: HTTP status code to return (200 = success, 400 = failure).
        error_description: Error description returned on non-200 responses.
    """

    def __init__(
        self,
        *,
        access_token: str = "test-access-token",
        refresh_token: str = "test-refresh-token",
        expires_in: int = 1800,
        status_code: int = 200,
        error_description: str = "",
    ) -> None:
        """See class docstring."""
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._expires_in = expires_in
        self._status_code = status_code
        self._error_description = error_description

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Return canned OAuth response regardless of request content.

        Args:
            request: Incoming httpx request (not inspected).

        Returns:
            httpx.Response with success or error body.
        """
        if self._status_code == 200:
            return httpx.Response(
                200,
                json={
                    "access_token": self._access_token,
                    "refresh_token": self._refresh_token,
                    "expires_in": self._expires_in,
                    "token_type": "Bearer",
                    "scope": "useraccount",
                },
            )
        return httpx.Response(
            self._status_code,
            json={
                "error": "invalid_grant",
                "error_description": self._error_description or "invalid_grant",
            },
        )
```

- [ ] **Step 3: Create oauth.py**

```python
# src/nexus/instances/oauth.py
# ServiceNow OAuth2 client: token exchange, auto-refresh, keychain I/O.
# Author: Pierre Grothe
# Date: 2026-05-08
"""SNOAuthClient: manages OAuth2 token lifecycle for one SN instance."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

from nexus.auth.keychain import KeychainClient
from nexus.instances.errors import OAuthError, TokenExpiredError

log = logging.getLogger(__name__)

__all__ = ["SNOAuthClient", "TokenResponse"]

_REFRESH_BUFFER = timedelta(minutes=5)
_OAUTH_PATH = "/oauth_token.do"


@dataclass(slots=True, frozen=True)
class TokenResponse:
    """Parsed response from a successful /oauth_token.do POST."""

    access_token: str
    refresh_token: str
    expires_in: int


class SNOAuthClient:
    """Manages OAuth2 token lifecycle for one SN instance.

    Args:
        profile: Instance profile name (used as keychain service key component).
        url: Full instance URL including scheme.
        client_id: OAuth application client_id (not a secret).
        username: SN login username.
        keychain: KeychainClient for token storage. Defaults to a standard client.
        transport: Optional httpx transport for testing. Omit in production.
    """

    def __init__(
        self,
        *,
        profile: str,
        url: str,
        client_id: str,
        username: str,
        keychain: KeychainClient | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """See class docstring."""
        self._profile = profile
        self._url = url
        self._client_id = client_id
        self._username = username
        self._keychain = keychain or KeychainClient()
        self._transport = transport

    def exchange(self, client_secret: str, password: str) -> TokenResponse:
        """POST Password Grant to obtain an initial token pair.

        Stores client_secret, access_token, and refresh_token in the keychain.
        The password is used once for the exchange and never stored.

        Args:
            client_secret: OAuth application client secret.
            password: SN user password. Discarded after the exchange.

        Returns:
            TokenResponse with access_token, refresh_token, expires_in.

        Raises:
            OAuthError: If the token exchange fails.
        """
        response = self._post_grant(
            grant_type="password",
            client_secret=client_secret,
            extra={"username": self._username, "password": password},
        )
        self._store_tokens(client_secret, response.access_token, response.refresh_token)
        return response

    def get_bearer_token(self, token_expires_at: datetime) -> tuple[str, datetime]:
        """Return a valid bearer token, refreshing automatically if near expiry.

        Args:
            token_expires_at: Current token expiry from meta.json (UTC-aware).

        Returns:
            Tuple of (access_token, updated_expiry). updated_expiry equals
            token_expires_at when no refresh was needed, or the new expiry
            after a successful refresh.

        Raises:
            TokenExpiredError: If the refresh token itself has expired (>100 days).
            OAuthError: If the refresh call fails for any other reason.
        """
        now = datetime.now(UTC)
        if now + _REFRESH_BUFFER < token_expires_at:
            return (
                self._keychain.get(f"sn-{self._profile}", "access-token"),
                token_expires_at,
            )

        client_secret = self._keychain.get(f"sn-{self._profile}", "client-secret")
        refresh_token = self._keychain.get(f"sn-{self._profile}", "refresh-token")

        try:
            response = self._post_grant(
                grant_type="refresh_token",
                client_secret=client_secret,
                extra={"refresh_token": refresh_token},
            )
        except OAuthError as exc:
            if "invalid_grant" in str(exc).lower() or "expired" in str(exc).lower():
                raise TokenExpiredError(self._profile) from exc
            raise

        self._store_tokens(client_secret, response.access_token, response.refresh_token)
        return response.access_token, now + timedelta(seconds=response.expires_in)

    def delete_tokens(self) -> None:
        """Remove all keychain entries for this profile."""
        for account in ("client-secret", "access-token", "refresh-token"):
            self._keychain.delete(f"sn-{self._profile}", account)

    def _post_grant(
        self,
        *,
        grant_type: str,
        client_secret: str,
        extra: dict[str, str],
    ) -> TokenResponse:
        data: dict[str, str] = {
            "grant_type": grant_type,
            "client_id": self._client_id,
            "client_secret": client_secret,
            **extra,
        }
        kwargs: dict[str, object] = {"timeout": 30.0}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        with httpx.Client(**kwargs) as client:
            resp = client.post(f"{self._url}{_OAUTH_PATH}", data=data)

        if resp.status_code != 200:
            try:
                desc = resp.json().get("error_description", f"HTTP {resp.status_code}")
            except Exception:
                desc = f"HTTP {resp.status_code}"
            raise OAuthError(str(desc))

        body = resp.json()
        return TokenResponse(
            access_token=str(body["access_token"]),
            refresh_token=str(body["refresh_token"]),
            expires_in=int(body["expires_in"]),
        )

    def _store_tokens(
        self, client_secret: str, access_token: str, refresh_token: str
    ) -> None:
        profile = self._profile
        self._keychain.set(f"sn-{profile}", "client-secret", client_secret)
        self._keychain.set(f"sn-{profile}", "access-token", access_token)
        self._keychain.set(f"sn-{profile}", "refresh-token", refresh_token)
```

- [ ] **Step 4: Run OAuth tests**

```bash
pytest tests/test_instances_oauth.py -v --no-cov
```
Expected: 7 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/nexus/instances/oauth.py tests/fakes/fake_http_transport.py tests/test_instances_oauth.py
git commit -m "feat(instances): SNOAuthClient with token exchange and auto-refresh"
```

---

## Task 4: InstanceRegistry

**Files:**
- Create: `src/nexus/instances/registry.py`
- Create: `tests/fakes/fake_instance_registry.py`
- Test: `tests/test_instances_registry.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_instances_registry.py
# Tests for InstanceRegistry disk operations.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for nexus.instances.registry."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from nexus.instances.errors import InstanceNotFoundError
from nexus.instances.models import ArtifactRecord, InstanceMeta, InstanceSnapshot
from nexus.instances.registry import InstanceRegistry


def _meta(profile: str = "dev12345") -> InstanceMeta:
    return InstanceMeta.create(
        profile=profile,
        url=f"https://{profile}.service-now.com",
        username="admin",
        client_id="client-123",
        sn_version="Xanadu",
        sn_build="04-01-2025",
        instance_name=profile,
        token_expires_in=1800,
    )


def _snapshot() -> InstanceSnapshot:
    record = ArtifactRecord(
        sys_id="abc",
        name="Test Skill",
        active=True,
        updated_on=datetime.now(UTC),
        is_custom=True,
    )
    return InstanceSnapshot(
        captured_at=datetime.now(UTC),
        sn_version="Xanadu",
        ai_skills=[record],
    )


def test_registry_register_creates_meta_json(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta())
    assert (tmp_path / "dev12345" / "meta.json").exists()


def test_registry_load_returns_stored_meta(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    meta = _meta()
    registry.register(meta)
    loaded = registry.load("dev12345")
    assert loaded.profile == "dev12345"
    assert loaded.url == meta.url


def test_registry_load_raises_when_profile_not_found(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    with pytest.raises(InstanceNotFoundError):
        registry.load("missing")


def test_registry_save_updates_meta_json(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    meta = _meta()
    registry.register(meta)
    new_expiry = datetime.now(UTC) + timedelta(hours=2)
    updated = meta.model_copy(update={"token_expires_at": new_expiry})
    registry.save(updated)
    loaded = registry.load("dev12345")
    assert abs((loaded.token_expires_at - new_expiry).total_seconds()) < 1


def test_registry_delete_removes_directory(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta())
    registry.delete("dev12345")
    assert not (tmp_path / "dev12345").exists()


def test_registry_delete_raises_when_not_found(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    with pytest.raises(InstanceNotFoundError):
        registry.delete("missing")


def test_registry_list_all_returns_all_profiles(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta("dev12345"))
    registry.register(_meta("prod99999"))
    profiles = registry.list_all()
    names = {m.profile for m in profiles}
    assert names == {"dev12345", "prod99999"}


def test_registry_list_all_returns_empty_when_no_instances_dir(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path / "instances")
    assert registry.list_all() == []


def test_registry_save_snapshot_writes_snapshot_json(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta())
    registry.save_snapshot("dev12345", _snapshot())
    assert (tmp_path / "dev12345" / "snapshot.json").exists()


def test_registry_load_snapshot_returns_stored_snapshot(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta())
    snap = _snapshot()
    registry.save_snapshot("dev12345", snap)
    loaded = registry.load_snapshot("dev12345")
    assert loaded is not None
    assert len(loaded.ai_skills) == 1
    assert loaded.ai_skills[0].name == "Test Skill"


def test_registry_load_snapshot_returns_none_when_no_snapshot(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta())
    assert registry.load_snapshot("dev12345") is None
```

Run: `pytest tests/test_instances_registry.py -v --no-cov`
Expected: FAIL with `ModuleNotFoundError: No module named 'nexus.instances.registry'`

- [ ] **Step 2: Create registry.py**

```python
# src/nexus/instances/registry.py
# CRUD operations on the per-instance directory tree.
# Author: Pierre Grothe
# Date: 2026-05-08
"""InstanceRegistry: manages ~/.nexus/instances/<profile>/ directories."""

import json
import logging
import shutil
import tempfile
from pathlib import Path

from nexus.instances.errors import InstanceNotFoundError
from nexus.instances.models import InstanceMeta, InstanceSnapshot

log = logging.getLogger(__name__)

__all__ = ["InstanceRegistry"]

_META = "meta.json"
_SNAPSHOT = "snapshot.json"


class InstanceRegistry:
    """Read/write per-instance directories under a given root path.

    Args:
        instances_root: Root directory; typically NexusPaths.instances_dir.
    """

    def __init__(self, instances_root: Path) -> None:
        """See class docstring."""
        self._root = instances_root

    def register(self, meta: InstanceMeta) -> None:
        """Create the profile directory and write meta.json.

        Args:
            meta: Metadata for the new instance.
        """
        profile_dir = self._dir(meta.profile)
        profile_dir.mkdir(parents=True, exist_ok=True)
        (profile_dir / _META).write_text(meta.model_dump_json(indent=2), encoding="utf-8")
        log.info("registered instance profile=%s", meta.profile)

    def load(self, profile: str) -> InstanceMeta:
        """Read meta.json for a profile.

        Args:
            profile: Profile name.

        Returns:
            Validated InstanceMeta.

        Raises:
            InstanceNotFoundError: If the profile directory does not exist.
        """
        meta_file = self._dir(profile) / _META
        if not meta_file.exists():
            raise InstanceNotFoundError(profile)
        return InstanceMeta.model_validate(json.loads(meta_file.read_text(encoding="utf-8")))

    def save(self, meta: InstanceMeta) -> None:
        """Overwrite meta.json for an existing profile.

        Args:
            meta: Updated metadata to persist.

        Raises:
            InstanceNotFoundError: If the profile directory does not exist.
        """
        profile_dir = self._dir(meta.profile)
        if not profile_dir.exists():
            raise InstanceNotFoundError(meta.profile)
        (profile_dir / _META).write_text(meta.model_dump_json(indent=2), encoding="utf-8")

    def delete(self, profile: str) -> None:
        """Remove the profile directory and all its contents.

        Args:
            profile: Profile name to delete.

        Raises:
            InstanceNotFoundError: If the profile does not exist.
        """
        profile_dir = self._dir(profile)
        if not profile_dir.exists():
            raise InstanceNotFoundError(profile)
        shutil.rmtree(profile_dir)
        log.info("deleted instance profile=%s", profile)

    def list_all(self) -> list[InstanceMeta]:
        """Return all registered profiles sorted by name.

        Returns:
            List of InstanceMeta, one per registered profile. Empty if none exist.
        """
        if not self._root.exists():
            return []
        profiles: list[InstanceMeta] = []
        for meta_file in sorted(self._root.glob(f"*/{_META}")):
            try:
                profiles.append(
                    InstanceMeta.model_validate(
                        json.loads(meta_file.read_text(encoding="utf-8"))
                    )
                )
            except Exception:
                log.warning("skipping malformed meta.json: %s", meta_file)
        return profiles

    def load_snapshot(self, profile: str) -> InstanceSnapshot | None:
        """Read snapshot.json for a profile if it exists.

        Args:
            profile: Profile name.

        Returns:
            InstanceSnapshot or None if no snapshot has been captured yet.
        """
        snap_file = self._dir(profile) / _SNAPSHOT
        if not snap_file.exists():
            return None
        return InstanceSnapshot.model_validate(
            json.loads(snap_file.read_text(encoding="utf-8"))
        )

    def save_snapshot(self, profile: str, snapshot: InstanceSnapshot) -> None:
        """Atomically write snapshot.json for a profile.

        Writes to a temp file then renames to avoid partial writes on failure.

        Args:
            profile: Profile name.
            snapshot: Snapshot to persist.

        Raises:
            InstanceNotFoundError: If the profile directory does not exist.
        """
        profile_dir = self._dir(profile)
        if not profile_dir.exists():
            raise InstanceNotFoundError(profile)
        snap_file = profile_dir / _SNAPSHOT
        fd, tmp = tempfile.mkstemp(dir=profile_dir, suffix=".tmp")
        try:
            with open(fd, "w", encoding="utf-8") as f:
                f.write(snapshot.model_dump_json(indent=2))
            Path(tmp).replace(snap_file)
        except Exception:
            Path(tmp).unlink(missing_ok=True)
            raise

    def _dir(self, profile: str) -> Path:
        return self._root / profile
```

- [ ] **Step 3: Create FakeInstanceRegistry**

```python
# tests/fakes/fake_instance_registry.py
# In-memory fake for InstanceRegistry.
# Author: Pierre Grothe
# Date: 2026-05-08
"""FakeInstanceRegistry: in-memory substitute for InstanceRegistry."""

from dataclasses import dataclass, field

from nexus.instances.errors import InstanceNotFoundError
from nexus.instances.models import InstanceMeta, InstanceSnapshot

__all__ = ["FakeInstanceRegistry"]


@dataclass
class FakeInstanceRegistry:
    """In-memory substitute for InstanceRegistry.

    Attributes:
        profiles: Map of profile name to InstanceMeta.
        snapshots: Map of profile name to InstanceSnapshot.
    """

    profiles: dict[str, InstanceMeta] = field(default_factory=dict)
    snapshots: dict[str, InstanceSnapshot] = field(default_factory=dict)

    def register(self, meta: InstanceMeta) -> None:
        """Store meta in memory."""
        self.profiles[meta.profile] = meta

    def load(self, profile: str) -> InstanceMeta:
        """Return stored meta or raise InstanceNotFoundError."""
        if profile not in self.profiles:
            raise InstanceNotFoundError(profile)
        return self.profiles[profile]

    def save(self, meta: InstanceMeta) -> None:
        """Overwrite stored meta or raise InstanceNotFoundError."""
        if meta.profile not in self.profiles:
            raise InstanceNotFoundError(meta.profile)
        self.profiles[meta.profile] = meta

    def delete(self, profile: str) -> None:
        """Remove profile and its snapshot or raise InstanceNotFoundError."""
        if profile not in self.profiles:
            raise InstanceNotFoundError(profile)
        del self.profiles[profile]
        self.snapshots.pop(profile, None)

    def list_all(self) -> list[InstanceMeta]:
        """Return all stored profiles."""
        return list(self.profiles.values())

    def load_snapshot(self, profile: str) -> InstanceSnapshot | None:
        """Return stored snapshot or None."""
        return self.snapshots.get(profile)

    def save_snapshot(self, profile: str, snapshot: InstanceSnapshot) -> None:
        """Store snapshot or raise InstanceNotFoundError."""
        if profile not in self.profiles:
            raise InstanceNotFoundError(profile)
        self.snapshots[profile] = snapshot
```

- [ ] **Step 4: Run registry tests**

```bash
pytest tests/test_instances_registry.py -v --no-cov
```
Expected: 11 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/nexus/instances/registry.py tests/fakes/fake_instance_registry.py tests/test_instances_registry.py
git commit -m "feat(instances): InstanceRegistry with atomic snapshot writes"
```

---

## Task 5: InstanceScanner

**Files:**
- Create: `src/nexus/instances/scanner.py`
- Test: `tests/test_instances_scanner.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_instances_scanner.py
# Tests for InstanceScanner async REST collection.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for nexus.instances.scanner."""

import pytest
import httpx

from nexus.instances.errors import SnapshotError
from nexus.instances.scanner import InstanceScanner, _is_custom


def _sn_response(records: list[dict]) -> dict:
    return {"result": records}


def _record(
    sys_id: str = "abc",
    name: str = "Test",
    created_by: str = "admin",
    scope_value: str = "x_custom",
) -> dict:
    return {
        "sys_id": sys_id,
        "name": name,
        "active": True,
        "sys_updated_on": "2026-05-01 10:00:00",
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

    def __init__(self, responses: dict[str, tuple[int, dict]]) -> None:
        self._responses = responses

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        status, body = self._responses.get(path, (404, {"error": "not found"}))
        return httpx.Response(status, json=body)


def _all_ok(
    ai_skills: list[dict] | None = None,
    flows: list[dict] | None = None,
    brs: list[dict] | None = None,
    sis: list[dict] | None = None,
) -> dict[str, tuple[int, dict]]:
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
    row = {"sys_created_by": "system", "sys_scope": {"value": "global"}}
    assert _is_custom(row) is False


def test_is_custom_returns_true_for_custom_scoped_record() -> None:
    row = {"sys_created_by": "admin", "sys_scope": {"value": "x_custom_app"}}
    assert _is_custom(row) is True


def test_is_custom_returns_false_when_created_by_system_even_in_custom_scope() -> None:
    row = {"sys_created_by": "system", "sys_scope": {"value": "x_custom"}}
    assert _is_custom(row) is False
```

Run: `pytest tests/test_instances_scanner.py -v --no-cov`
Expected: FAIL with `ModuleNotFoundError: No module named 'nexus.instances.scanner'`

- [ ] **Step 2: Create scanner.py**

```python
# src/nexus/instances/scanner.py
# Captures artifact inventory from a live ServiceNow instance.
# Author: Pierre Grothe
# Date: 2026-05-08
"""InstanceScanner: parallel REST calls to collect artifact snapshots."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

import httpx

from nexus.instances.errors import SnapshotError
from nexus.instances.models import ArtifactRecord, InstanceSnapshot

log = logging.getLogger(__name__)

__all__ = ["InstanceScanner"]

_AI_SKILL_FIELDS = "sys_id,name,active,sys_updated_on,skill_type,sys_created_by,sys_scope"
_FLOW_FIELDS = "sys_id,name,active,sys_updated_on,accessible_from,sys_created_by,sys_scope"
_BR_FIELDS = "sys_id,name,active,sys_updated_on,table_name,when,sys_created_by,sys_scope"
_SI_FIELDS = "sys_id,name,active,sys_updated_on,api_name,client_callable,sys_created_by,sys_scope"

_EXTRA_FIELDS: dict[str, list[str]] = {
    "ai_skill": ["skill_type"],
    "sys_hub_flow": ["accessible_from"],
    "sys_script": ["table_name", "when"],
    "sys_script_include": ["api_name", "client_callable"],
}

_TABLE_CONFIG = [
    ("ai_skill", _AI_SKILL_FIELDS, 1000),
    ("sys_hub_flow", _FLOW_FIELDS, 1000),
    ("sys_script", _BR_FIELDS, 2000),
    ("sys_script_include", _SI_FIELDS, 2000),
]


def _is_custom(row: dict[str, object]) -> bool:
    """Return True when the record was created outside the global system scope."""
    created_by = row.get("sys_created_by", "")
    scope = row.get("sys_scope", {})
    scope_value = scope.get("value", "global") if isinstance(scope, dict) else str(scope or "global")
    return created_by != "system" and scope_value != "global"


def _parse_dt(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return datetime.now(UTC)


def _to_record(row: dict[str, object], extra_field_names: list[str]) -> ArtifactRecord:
    extra: dict[str, str | bool | int] = {}
    for key in extra_field_names:
        val = row.get(key)
        if isinstance(val, str | bool | int):
            extra[key] = val
    return ArtifactRecord(
        sys_id=str(row.get("sys_id", "")),
        name=str(row.get("name", "")),
        active=bool(row.get("active", False)),
        updated_on=_parse_dt(str(row.get("sys_updated_on", ""))),
        is_custom=_is_custom(row),
        extra=extra,
    )


class InstanceScanner:
    """Captures artifact inventory from a live ServiceNow instance.

    Args:
        transport: Optional async httpx transport for testing. Omit in production.
    """

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        """See class docstring."""
        self._transport = transport

    async def scan(self, url: str, token: str, sn_version: str) -> InstanceSnapshot:
        """Capture a full artifact snapshot via four concurrent REST calls.

        Args:
            url: Instance base URL (e.g. https://dev12345.service-now.com).
            token: Bearer access token.
            sn_version: SN version string copied verbatim into the snapshot.

        Returns:
            InstanceSnapshot with all four artifact lists populated.

        Raises:
            SnapshotError: If any REST call returns a non-2xx status. The
                previous snapshot on disk is unaffected -- the caller decides
                whether to persist the result.
        """
        kwargs: dict[str, object] = {
            "base_url": url,
            "headers": {"Authorization": f"Bearer {token}", "Accept": "application/json"},
            "timeout": 30.0,
        }
        if self._transport is not None:
            kwargs["transport"] = self._transport

        async with httpx.AsyncClient(**kwargs) as client:
            ai_skills, flows, business_rules, script_includes = await asyncio.gather(
                self._fetch(client, "ai_skill"),
                self._fetch(client, "sys_hub_flow"),
                self._fetch(client, "sys_script"),
                self._fetch(client, "sys_script_include"),
            )

        return InstanceSnapshot(
            captured_at=datetime.now(UTC),
            sn_version=sn_version,
            ai_skills=ai_skills,
            flows=flows,
            business_rules=business_rules,
            script_includes=script_includes,
        )

    async def _fetch(self, client: httpx.AsyncClient, table: str) -> list[ArtifactRecord]:
        config = next(cfg for cfg in _TABLE_CONFIG if cfg[0] == table)
        _, fields, limit = config
        resp = await client.get(
            f"/api/now/table/{table}",
            params={"sysparm_fields": fields, "sysparm_limit": limit},
        )
        if resp.status_code != 200:
            raise SnapshotError(table, resp.status_code)
        return [_to_record(row, _EXTRA_FIELDS[table]) for row in resp.json().get("result", [])]
```

- [ ] **Step 3: Run scanner tests**

```bash
pytest tests/test_instances_scanner.py -v --no-cov
```
Expected: 6 PASSED

- [ ] **Step 4: Commit**

```bash
git add src/nexus/instances/scanner.py tests/test_instances_scanner.py
git commit -m "feat(instances): InstanceScanner with parallel async REST collection"
```

---

## Task 6: Package __init__.py, retire SNAuth, update fakes

**Files:**
- Create: `src/nexus/instances/__init__.py`
- Modify: `src/nexus/auth/__init__.py`
- Modify: `src/nexus/auth/servicenow.py`
- Modify: `tests/fakes/__init__.py`

- [ ] **Step 1: Create instances/__init__.py**

```python
# src/nexus/instances/__init__.py
# Instance management: OAuth, registry, scanner.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Instance management public exports."""

from nexus.instances.errors import (
    InstanceError,
    InstanceNotFoundError,
    OAuthError,
    SnapshotError,
    TokenExpiredError,
)
from nexus.instances.models import (
    ArtifactRecord,
    InstanceMeta,
    InstanceSnapshot,
    SnapshotCounts,
)
from nexus.instances.oauth import SNOAuthClient, TokenResponse
from nexus.instances.registry import InstanceRegistry
from nexus.instances.scanner import InstanceScanner

__all__ = [
    "ArtifactRecord",
    "InstanceError",
    "InstanceMeta",
    "InstanceNotFoundError",
    "InstanceRegistry",
    "InstanceScanner",
    "InstanceSnapshot",
    "OAuthError",
    "SNOAuthClient",
    "SnapshotCounts",
    "SnapshotError",
    "TokenExpiredError",
    "TokenResponse",
]
```

- [ ] **Step 2: Mark SNAuth deprecated in auth/servicenow.py**

Add a deprecation warning to `SNAuth.__init__` so existing callers are alerted. Do NOT delete the class -- it may exist in user config or external scripts. Add at the top of the file, after the imports:

```python
import warnings
```

And update `SNAuth.__init__`:

```python
def __init__(self, keychain: KeychainClient | None = None) -> None:
    """Initialize with optional keychain client."""
    warnings.warn(
        "SNAuth is deprecated. Use nexus.instances.SNOAuthClient instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    self._keychain = keychain or KeychainClient()
```

- [ ] **Step 3: Remove SNAuth from auth/__init__.py**

Update `src/nexus/auth/__init__.py`:

```python
# nexus/auth/__init__.py
# Authentication layer public exports.
# Author: Pierre Grothe
# Date: 2026-05-07
"""Credential storage and retrieval for NEXUS."""

from nexus.auth.claude import ClaudeAuth
from nexus.auth.errors import AuthError
from nexus.auth.external_keychain import ExternalKeychainClient
from nexus.auth.keychain import KeychainClient

__all__ = [
    "AuthError",
    "ClaudeAuth",
    "ExternalKeychainClient",
    "KeychainClient",
]
```

- [ ] **Step 4: Update tests/fakes/__init__.py**

Add `FakeInstanceRegistry` and `FakeOAuthTransport`:

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
from tests.fakes.fake_http_transport import FakeOAuthTransport
from tests.fakes.fake_instance_registry import FakeInstanceRegistry
from tests.fakes.fake_keychain import FakeKeychainClient
from tests.fakes.fake_sn_client import FakeServiceNowClient

__all__ = [
    "FakeAgentClient",
    "FakeCacheBackend",
    "FakeClaudeCodeConfig",
    "FakeClock",
    "FakeGitHubReleasesClient",
    "FakeInstanceRegistry",
    "FakeKeychainClient",
    "FakeOAuthTransport",
    "FakeServiceNowClient",
]
```

- [ ] **Step 5: Run full suite**

```bash
pytest --no-cov -q
```
Expected: all existing tests pass, ~240+ tests.

- [ ] **Step 6: Commit**

```bash
git add src/nexus/instances/__init__.py src/nexus/auth/__init__.py src/nexus/auth/servicenow.py tests/fakes/__init__.py tests/fakes/fake_instance_registry.py
git commit -m "feat(instances): package init, retire SNAuth, update fakes"
```

---

## Task 7: CLI instance sub-app

**Files:**
- Modify: `src/nexus/cli.py`
- Test: `tests/test_cli_instance.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cli_instance.py
# Tests for nexus instance CLI commands.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for the nexus instance sub-app."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nexus.cache import clear_cache
from nexus.cli import app
from nexus.config.paths import NexusPaths
from nexus.instances.models import InstanceMeta, SnapshotCounts


def _meta(profile: str = "dev12345") -> InstanceMeta:
    return InstanceMeta.create(
        profile=profile,
        url=f"https://{profile}.service-now.com",
        username="admin",
        client_id="client-123",
        sn_version="Xanadu",
        sn_build="04-01-2025",
        instance_name=profile,
        token_expires_in=1800,
    )


@pytest.fixture
def runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    monkeypatch.setenv("NEXUS_CONFIG_PATH", str(tmp_path / "config.yaml"))
    clear_cache(NexusPaths.from_env)
    return CliRunner()


def _write_meta(tmp_path: Path, meta: InstanceMeta) -> None:
    profile_dir = tmp_path / "instances" / meta.profile
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "meta.json").write_text(meta.model_dump_json(indent=2), encoding="utf-8")


def test_instance_list_with_no_instances_prints_empty_message(
    runner: CliRunner, tmp_path: Path
) -> None:
    result = runner.invoke(app, ["instance", "list"])
    assert result.exit_code == 0
    assert "No instances registered" in result.output


def test_instance_list_shows_registered_profiles(
    runner: CliRunner, tmp_path: Path
) -> None:
    _write_meta(tmp_path, _meta("dev12345"))
    result = runner.invoke(app, ["instance", "list"])
    assert result.exit_code == 0
    assert "dev12345" in result.output


def test_instance_status_shows_meta_fields(
    runner: CliRunner, tmp_path: Path
) -> None:
    _write_meta(tmp_path, _meta("dev12345"))
    result = runner.invoke(app, ["instance", "status", "dev12345"])
    assert result.exit_code == 0
    assert "dev12345" in result.output
    assert "Xanadu" in result.output


def test_instance_status_without_snapshot_shows_no_snapshot_message(
    runner: CliRunner, tmp_path: Path
) -> None:
    _write_meta(tmp_path, _meta("dev12345"))
    result = runner.invoke(app, ["instance", "status", "dev12345"])
    assert result.exit_code == 0
    assert "No snapshot" in result.output


def test_instance_status_with_unknown_profile_exits_nonzero(
    runner: CliRunner, tmp_path: Path
) -> None:
    result = runner.invoke(app, ["instance", "status", "nonexistent"])
    assert result.exit_code != 0


def test_instance_delete_removes_profile_directory(
    runner: CliRunner, tmp_path: Path
) -> None:
    _write_meta(tmp_path, _meta("dev12345"))
    result = runner.invoke(app, ["instance", "delete", "dev12345", "--force"])
    assert result.exit_code == 0
    assert not (tmp_path / "instances" / "dev12345").exists()


def test_instance_delete_unknown_profile_exits_nonzero(
    runner: CliRunner, tmp_path: Path
) -> None:
    result = runner.invoke(app, ["instance", "delete", "nonexistent", "--force"])
    assert result.exit_code != 0


def test_instance_use_sets_default_in_config(
    runner: CliRunner, tmp_path: Path
) -> None:
    _write_meta(tmp_path, _meta("dev12345"))
    result = runner.invoke(app, ["instance", "use", "dev12345"])
    assert result.exit_code == 0
    config_raw = (tmp_path / "config.yaml").read_text(encoding="utf-8")
    assert "dev12345" in config_raw


def test_instance_use_unknown_profile_exits_nonzero(
    runner: CliRunner, tmp_path: Path
) -> None:
    result = runner.invoke(app, ["instance", "use", "nonexistent"])
    assert result.exit_code != 0
```

Run: `pytest tests/test_cli_instance.py -v --no-cov`
Expected: FAIL with `No such command 'instance'`

- [ ] **Step 2: Add instance sub-app to cli.py**

At the top of `src/nexus/cli.py`, add these imports after the existing imports:

```python
import asyncio
import httpx

from nexus.config.manager import ConfigManager
from nexus.config.settings import InstancesConfig
from nexus.instances.errors import InstanceNotFoundError, SnapshotError, TokenExpiredError
from nexus.instances.models import InstanceMeta
from nexus.instances.oauth import SNOAuthClient
from nexus.instances.registry import InstanceRegistry
from nexus.instances.scanner import InstanceScanner
```

After `app = typer.Typer(...)` and before `console = ...`, add:

```python
instance_app = typer.Typer(name="instance", help="Manage ServiceNow instances.")
app.add_typer(instance_app)
```

Then add all instance commands before the `if __name__ == "__main__":` line:

```python
def _instance_registry() -> InstanceRegistry:
    return InstanceRegistry(NexusPaths.from_env().instances_dir)


def _config_default() -> str:
    return ConfigManager(NexusPaths.from_env()).load().instances.default


@instance_app.command("list")
def instance_list() -> None:
    """Show all registered ServiceNow instances."""
    from datetime import UTC, datetime

    from rich.table import Table

    registry = _instance_registry()
    metas = registry.list_all()
    if not metas:
        console.print("No instances registered. Run 'nexus instance register <profile>'.")
        return

    default = _config_default()
    tbl = Table("Profile", "URL", "Version", "Token", "Last Connected")
    for meta in metas:
        now = datetime.now(UTC)
        if now >= meta.token_expires_at:
            token_str = "EXPIRED"
        else:
            mins = int((meta.token_expires_at - now).total_seconds() / 60)
            token_str = f"{mins} min left"
        prefix = "* " if meta.profile == default else "  "
        tbl.add_row(
            f"{prefix}{meta.profile}",
            meta.url,
            meta.sn_version,
            token_str,
            meta.last_connected_at.strftime("%Y-%m-%d %H:%M UTC"),
        )
    console.print(tbl)


@instance_app.command("status")
def instance_status(profile: str = typer.Argument("")) -> None:
    """Show metadata and snapshot summary for an instance."""
    from datetime import UTC, datetime

    if not profile:
        profile = _config_default()
    if not profile:
        err_console.print("[error]No default instance. Pass a profile or run 'nexus instance use <profile>'.[/error]")
        raise typer.Exit(1)

    registry = _instance_registry()
    try:
        meta = registry.load(profile)
    except InstanceNotFoundError as exc:
        err_console.print(f"[error]{exc}[/error]")
        raise typer.Exit(1) from exc

    now = datetime.now(UTC)
    remaining = (meta.token_expires_at - now).total_seconds() / 60
    token_str = f"valid ({int(remaining)} min remaining)" if remaining > 0 else "EXPIRED"

    console.print(f"Instance:  {meta.profile}")
    console.print(f"URL:       {meta.url}")
    console.print(f"Version:   {meta.sn_version} ({meta.sn_build})")
    console.print(f"Token:     {token_str}")
    console.print(f"Connected: {meta.last_connected_at.strftime('%Y-%m-%d %H:%M UTC')}")

    snapshot = registry.load_snapshot(profile)
    if snapshot is None:
        console.print("\nNo snapshot. Run 'nexus instance refresh' to capture one.")
        return

    c = snapshot.counts
    custom_flows = sum(1 for f in snapshot.flows if f.is_custom)
    custom_brs = sum(1 for r in snapshot.business_rules if r.is_custom)
    custom_sis = sum(1 for s in snapshot.script_includes if s.is_custom)
    console.print(f"\nSnapshot ({snapshot.captured_at.strftime('%Y-%m-%d %H:%M UTC')}):")
    console.print(f"  AI Skills:        {c.ai_skills}")
    console.print(f"  Flows:           {c.flows}  ({custom_flows} custom)")
    console.print(f"  Business Rules:  {c.business_rules}  ({custom_brs} custom)")
    console.print(f"  Script Includes: {c.script_includes}  ({custom_sis} custom)")


@instance_app.command("delete")
def instance_delete(
    profile: str,
    force: Annotated[bool, typer.Option("--force", help="Skip confirmation")] = False,
) -> None:
    """Remove a registered instance and its keychain entries."""
    if not force:
        if not typer.confirm(f"Delete instance {profile!r} and all its data?"):
            raise typer.Abort()

    registry = _instance_registry()
    try:
        meta = registry.load(profile)
    except InstanceNotFoundError as exc:
        err_console.print(f"[error]{exc}[/error]")
        raise typer.Exit(1) from exc

    SNOAuthClient(
        profile=profile, url=meta.url, client_id=meta.client_id, username=meta.username
    ).delete_tokens()
    registry.delete(profile)

    paths = NexusPaths.from_env()
    manager = ConfigManager(paths)
    cfg = manager.load()
    if cfg.instances.default == profile:
        manager.save(cfg.model_copy(update={"instances": InstancesConfig(default="")}))

    console.print(f"Deleted instance {profile!r}.")


@instance_app.command("use")
def instance_use(profile: str) -> None:
    """Set the default instance."""
    registry = _instance_registry()
    try:
        registry.load(profile)
    except InstanceNotFoundError as exc:
        err_console.print(f"[error]{exc}[/error]")
        raise typer.Exit(1) from exc

    paths = NexusPaths.from_env()
    manager = ConfigManager(paths)
    manager.save(
        manager.load().model_copy(update={"instances": InstancesConfig(default=profile)})
    )
    console.print(f"Default instance set to {profile!r}.")


@instance_app.command("connect")
def instance_connect(profile: str = typer.Argument("")) -> None:
    """Verify connectivity and refresh token if near expiry."""
    from datetime import UTC, datetime

    if not profile:
        profile = _config_default()
    if not profile:
        err_console.print("[error]No default instance set.[/error]")
        raise typer.Exit(1)

    registry = _instance_registry()
    try:
        meta = registry.load(profile)
    except InstanceNotFoundError as exc:
        err_console.print(f"[error]{exc}[/error]")
        raise typer.Exit(1) from exc

    oauth = SNOAuthClient(
        profile=profile, url=meta.url, client_id=meta.client_id, username=meta.username
    )
    try:
        token, new_expiry = oauth.get_bearer_token(meta.token_expires_at)
    except TokenExpiredError as exc:
        err_console.print(f"[warning]{exc}[/warning]")
        raise typer.Exit(1) from exc

    try:
        with httpx.Client(
            base_url=meta.url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        ) as client:
            resp = client.get("/api/now/table/sys_properties", params={"sysparm_limit": 1})
        if resp.status_code != 200:
            err_console.print(f"[error]Probe failed: HTTP {resp.status_code}[/error]")
            raise typer.Exit(1)
    except httpx.RequestError as exc:
        err_console.print(f"[error]Cannot reach {meta.url}: {exc}[/error]")
        raise typer.Exit(1) from exc

    now = datetime.now(UTC)
    registry.save(meta.model_copy(update={"last_connected_at": now, "token_expires_at": new_expiry}))
    console.print(f"Connected to {profile!r}. Token valid until {new_expiry.strftime('%H:%M UTC')}.")


@instance_app.command("refresh")
def instance_refresh(profile: str = typer.Argument("")) -> None:
    """Pull a fresh artifact snapshot from the instance."""
    if not profile:
        profile = _config_default()
    if not profile:
        err_console.print("[error]No default instance set.[/error]")
        raise typer.Exit(1)

    registry = _instance_registry()
    try:
        meta = registry.load(profile)
    except InstanceNotFoundError as exc:
        err_console.print(f"[error]{exc}[/error]")
        raise typer.Exit(1) from exc

    oauth = SNOAuthClient(
        profile=profile, url=meta.url, client_id=meta.client_id, username=meta.username
    )
    try:
        token, new_expiry = oauth.get_bearer_token(meta.token_expires_at)
    except TokenExpiredError as exc:
        err_console.print(f"[warning]{exc}[/warning]")
        raise typer.Exit(1) from exc

    console.print(f"Capturing snapshot from {profile!r}...")
    try:
        snapshot = asyncio.run(InstanceScanner().scan(meta.url, token, meta.sn_version))
    except SnapshotError as exc:
        err_console.print(f"[error]{exc}[/error]")
        raise typer.Exit(1) from exc

    registry.save_snapshot(profile, snapshot)
    c = snapshot.counts
    registry.save(meta.model_copy(update={"token_expires_at": new_expiry, "snapshot_counts": c}))
    console.print(
        f"Snapshot captured: {c.ai_skills} AI skills, {c.flows} flows, "
        f"{c.business_rules} business rules, {c.script_includes} script includes."
    )


@instance_app.command("register")
def instance_register(profile: str) -> None:
    """Interactive wizard to register a new ServiceNow instance via OAuth2."""
    paths = NexusPaths.from_env()
    if (paths.instances_dir / profile).exists():
        err_console.print(
            f"[error]Profile {profile!r} already exists. "
            f"Delete it first with 'nexus instance delete {profile}'.[/error]"
        )
        raise typer.Exit(1)

    console.print(f"Registering instance: [bold]{profile}[/bold]")
    raw_url: str = typer.prompt("  Instance URL (e.g. dev12345.service-now.com)")
    url = raw_url if raw_url.startswith("https://") else f"https://{raw_url}"
    username: str = typer.prompt("  Username")
    client_id: str = typer.prompt("  OAuth Client ID")
    client_secret: str = typer.prompt("  OAuth Client Secret", hide_input=True)
    password: str = typer.prompt("  Password", hide_input=True)

    console.print("  Exchanging credentials for OAuth token...")
    oauth = SNOAuthClient(profile=profile, url=url, client_id=client_id, username=username)
    try:
        token_response = oauth.exchange(client_secret, password)
    except Exception as exc:
        err_console.print(f"[error]{exc}[/error]")
        raise typer.Exit(1) from exc

    sn_version = "unknown"
    sn_build = ""
    instance_name = profile
    try:
        with httpx.Client(
            base_url=url,
            headers={"Authorization": f"Bearer {token_response.access_token}"},
            timeout=10.0,
        ) as client:
            resp = client.get(
                "/api/now/table/sys_properties",
                params={
                    "sysparm_query": "nameINglide.buildtag,instance_name",
                    "sysparm_fields": "name,value",
                    "sysparm_limit": 2,
                },
            )
        if resp.status_code == 200:
            for row in resp.json().get("result", []):
                if row.get("name") == "glide.buildtag":
                    sn_build = str(row.get("value", ""))
                    sn_version = sn_build.split("-")[0] if sn_build else "unknown"
                elif row.get("name") == "instance_name":
                    instance_name = str(row.get("value", profile))
    except httpx.RequestError:
        pass

    registry = InstanceRegistry(paths.instances_dir)
    meta = InstanceMeta.create(
        profile=profile,
        url=url,
        username=username,
        client_id=client_id,
        sn_version=sn_version,
        sn_build=sn_build,
        instance_name=instance_name,
        token_expires_in=token_response.expires_in,
    )
    registry.register(meta)
    console.print(f"  Registered [bold]{profile}[/bold] ({sn_version}).")

    manager = ConfigManager(paths)
    if not manager.load().instances.default:
        manager.save(
            manager.load().model_copy(update={"instances": InstancesConfig(default=profile)})
        )
        console.print(f"  Set as default instance.")
```

- [ ] **Step 3: Run CLI tests**

```bash
pytest tests/test_cli_instance.py -v --no-cov
```
Expected: 9 PASSED

- [ ] **Step 4: Run full suite**

```bash
pytest --no-cov -q
```
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/nexus/cli.py tests/test_cli_instance.py
git commit -m "feat(instances): CLI instance sub-app with 7 commands"
```

---

## Task 8: Ratchet baselines and final commit

**Files:**
- Modify: `.ratchet.json`

- [ ] **Step 1: Measure coverage for new modules**

```bash
pytest --cov=nexus.instances --cov=nexus.config.paths --cov=nexus.config.settings --cov=nexus.auth --cov=nexus.cli --cov-report=term-missing -q 2>&1 | grep "nexus\."
```

Note the `Stmts`, `Miss`, and `Cover %` for each module.

- [ ] **Step 2: Update .ratchet.json**

Add entries for all new modules and update existing ones with the measured values. New modules to add:

```json
"nexus.instances": {"covered_lines": <measured>, "total_lines": <measured>},
"nexus.instances.errors": {"covered_lines": <measured>, "total_lines": <measured>},
"nexus.instances.models": {"covered_lines": <measured>, "total_lines": <measured>},
"nexus.instances.oauth": {"covered_lines": <measured>, "total_lines": <measured>},
"nexus.instances.registry": {"covered_lines": <measured>, "total_lines": <measured>},
"nexus.instances.scanner": {"covered_lines": <measured>, "total_lines": <measured>}
```

Also update `nexus.config.paths`, `nexus.config.settings`, `nexus.auth`, and `nexus.cli` with their new measured values.

- [ ] **Step 3: Run full suite one final time**

```bash
pytest -q
```
Expected: all tests pass, no ratchet violations.

- [ ] **Step 4: Final commit**

```bash
git add .ratchet.json
git commit -m "chore: update ratchet baselines for instance management"
```
