# Instance Management Design

**Goal:** A per-instance registry with OAuth2 credentials, local metadata/snapshot
files, and a CLI for registering, inspecting, and refreshing ServiceNow instances.
This is the foundation layer for all capture/apply/copy workflows.

**Architecture:** New `src/nexus/instances/` package at layer 4 (alongside
`connectors/`). Owns the registry, OAuth token lifecycle, and artifact snapshot
collection. Higher layers (agents, templates, assessment) obtain a live SN
connection through this package rather than calling `connectors/` directly.

**Tech Stack:** httpx (existing), keyring (existing), Pydantic frozen models
(existing), ServiceNow Table API REST, ServiceNow OAuth2 Password Grant.

---

## 1. On-disk layout

```
~/.nexus/instances/
  <profile>/
    meta.json       -- static metadata + OAuth display fields (no secrets)
    snapshot.json   -- artifact inventory captured on last refresh
```

`InstancesConfig` in `config/settings.py` is simplified to `default: str` only.
The `profiles: dict[str, InstanceProfile]` field and `InstanceProfile` model are
removed -- the directory tree IS the registry. `SNAuth` in `auth/servicenow.py`
is retired; `instances/oauth.py` replaces it.

### meta.json schema

```json
{
  "profile":           "dev12345",
  "url":               "https://dev12345.service-now.com",
  "username":          "admin",
  "client_id":         "abc123...",
  "sn_version":        "Xanadu",
  "sn_build":          "04-01-2025_1200",
  "instance_name":     "dev12345",
  "registered_at":     "2026-05-08T14:00:00Z",
  "last_connected_at": "2026-05-08T14:05:00Z",
  "token_expires_at":  "2026-05-08T14:35:00Z",
  "snapshot_counts": {
    "ai_skills": 5,
    "flows": 23,
    "business_rules": 312,
    "script_includes": 189
  }
}
```

`client_id` is stored here because it is not a secret (it is the public OAuth
application identifier). `token_expires_at` is stored here so `status` can
render token health without reading the keychain.

### snapshot.json schema

```json
{
  "captured_at": "2026-05-08T14:05:00Z",
  "sn_version":  "Xanadu",
  "artifacts": {
    "ai_skills": [
      {
        "sys_id":     "abc...",
        "name":       "IT Support Skill",
        "active":     true,
        "updated_on": "2026-04-15T10:00:00Z",
        "skill_type": "now_assist",
        "is_custom":  true
      }
    ],
    "flows": [
      {
        "sys_id":          "def...",
        "name":            "Incident Auto-Close",
        "active":          true,
        "updated_on":      "2026-03-01T08:00:00Z",
        "accessible_from": "package_private",
        "is_custom":       true
      }
    ],
    "business_rules": [
      {
        "sys_id":     "ghi...",
        "name":       "Set Priority",
        "active":     true,
        "updated_on": "2026-02-10T12:00:00Z",
        "table_name": "incident",
        "when":       "before",
        "is_custom":  true
      }
    ],
    "script_includes": [
      {
        "sys_id":           "jkl...",
        "name":             "IncidentUtils",
        "active":           true,
        "updated_on":       "2026-01-20T09:00:00Z",
        "api_name":         "global.IncidentUtils",
        "client_callable":  false,
        "is_custom":        true
      }
    ]
  }
}
```

`is_custom` is derived at capture time: `sys_created_by != "system"` AND
`sys_scope_name != "global"`. Script bodies are NOT stored in the snapshot --
they are fetched on-demand at copy/capture time.

---

## 2. Source layout

```
src/nexus/instances/
  __init__.py
  errors.py      -- OAuthError, TokenExpiredError, InstanceNotFoundError, SnapshotError
  models.py      -- InstanceMeta, SnapshotCounts, ArtifactRecord, InstanceSnapshot
  oauth.py       -- SNOAuthClient: token exchange, auto-refresh, keychain I/O
  registry.py    -- InstanceRegistry: CRUD on ~/.nexus/instances/
  scanner.py     -- InstanceScanner: four parallel REST calls -> InstanceSnapshot
```

Modified files:
- `src/nexus/config/settings.py` -- simplify InstancesConfig, remove InstanceProfile
- `src/nexus/cli.py` -- add `nexus instance` Typer sub-app
- `src/nexus/auth/servicenow.py` -- retire SNAuth (replaced by oauth.py)

---

## 3. OAuth credential flow

### Prerequisites (one-time admin task per SN instance)

Navigate to *System OAuth > Application Registry*. Create a new OAuth API
endpoint for external clients. Note the `client_id` and `client_secret`.

### Registration sequence

`nexus instance register <profile>` runs an interactive wizard:

```
Instance URL:         dev12345.service-now.com
Username:             admin
OAuth Client ID:      <from app registry>
OAuth Client Secret:  [hidden input]
Password:             [hidden input -- used once, then discarded]
```

NEXUS POSTs a Password Grant to `/oauth_token.do`:

```
POST https://<url>/oauth_token.do
Content-Type: application/x-www-form-urlencoded

grant_type=password
&client_id=<client_id>
&client_secret=<client_secret>
&username=<username>
&password=<password>
```

On success (HTTP 200, JSON body with `access_token`):
1. Store `client_secret`, `access_token`, `refresh_token` in keychain.
2. Write `meta.json` with `client_id` and `token_expires_at`.
3. Discard password -- it is never written anywhere.

On failure: raise `OAuthError` with the SN error description. No files written.

### Keychain layout

All entries use `keyring.set_password(service, username, value)`:

| service | username | value |
|---|---|---|
| `nexus-sn-<profile>` | `client-secret` | OAuth client_secret |
| `nexus-sn-<profile>` | `access-token` | current access_token |
| `nexus-sn-<profile>` | `refresh-token` | current refresh_token |

### Auto-refresh

`SNOAuthClient.get_client() -> httpx.AsyncClient` is the single entry point
for obtaining an authenticated HTTP client. Before returning:

1. Read `token_expires_at` from `meta.json`.
2. If `utcnow + 5 min >= token_expires_at`, POST a Refresh Grant:
   ```
   grant_type=refresh_token
   &client_id=<client_id from meta.json>
   &client_secret=<from keychain>
   &refresh_token=<from keychain>
   ```
3. SN issues a new token pair (refresh tokens are single-use). Update both
   `access-token` and `refresh-token` in keychain. Update `token_expires_at`
   in `meta.json`.
4. If refresh fails (token expired after 100 days): raise `TokenExpiredError`
   with message: "Run `nexus instance connect <profile>` to re-authenticate."

The caller receives a ready `httpx.AsyncClient` with `Authorization: Bearer
<access_token>` set. It never reads tokens directly.

---

## 4. CLI commands

All instance commands live under a `nexus instance` Typer sub-app.

### register

```
nexus instance register <profile>
```

Interactive wizard (Section 3). Prompts for URL, username, client_id,
client_secret (hidden), password (hidden). Calls `/oauth_token.do`. On
success writes `meta.json`, stores tokens in keychain. Optionally prompts
"Set as default? [y/N]" and updates `config.yaml` if yes.

### delete

```
nexus instance delete <profile>
```

Removes all three keychain entries for the profile. Deletes
`~/.nexus/instances/<profile>/` directory. If the deleted profile was the
configured default, clears `instances.default` in `config.yaml`.

### list

```
nexus instance list
```

Reads all `~/.nexus/instances/*/meta.json` files. Renders a Rich table:

```
Profile     URL                                  Version   Token        Last Connected
dev12345    https://dev12345.service-now.com     Xanadu    28 min left  2026-05-08 14:05
prod99999   https://prod99999.service-now.com    Xanadu    EXPIRED      2026-05-07 09:10
```

No network calls. Default profile is marked with `*`.

### connect

```
nexus instance connect <profile>
```

Calls `SNOAuthClient.get_client()` (triggers auto-refresh if needed). Makes a
lightweight probe (`GET /api/now/table/sys_properties?sysparm_limit=1`). On
success updates `last_connected_at` in `meta.json` and prints confirmation.
On `TokenExpiredError` prints re-auth instructions.

### refresh

```
nexus instance refresh [<profile>]
```

Calls `InstanceScanner.scan(profile)`. Makes four parallel REST calls to
capture the artifact inventory. On success atomically writes `snapshot.json`
and updates `snapshot_counts` in `meta.json`. If any call fails, raises
`SnapshotError` and preserves the previous snapshot unchanged.

### status

```
nexus instance status [<profile>]
```

No network call. Reads `meta.json` and `snapshot.json` and renders:

```
Instance:  dev12345
URL:       https://dev12345.service-now.com
Version:   Xanadu (04-01-2025)
Token:     valid (28 min remaining)
Connected: 2026-05-08 14:05 UTC

Snapshot (2026-05-08 14:05 UTC):
  AI Skills:         5
  Flows:            23  (18 custom)
  Business Rules:  312  (47 custom)
  Script Includes: 189  (31 custom)
```

### use

```
nexus instance use <profile>
```

Writes `instances.default = <profile>` to `config.yaml`. Prints confirmation.

---

## 5. Artifact snapshot collection

`InstanceScanner.scan(profile)` fires four concurrent `httpx` calls via
`asyncio.gather`. Each call targets the SN Table API with `sysparm_fields`
limited to inventory columns only (no script bodies).

### Endpoints and fields

**AI Skills** -- `GET /api/now/table/ai_skill`
```
sysparm_fields=sys_id,name,active,sys_updated_on,skill_type,sys_created_by,sys_scope
sysparm_limit=1000
```

**Flows** -- `GET /api/now/table/sys_hub_flow`
```
sysparm_fields=sys_id,name,active,sys_updated_on,accessible_from,sys_created_by,sys_scope
sysparm_limit=1000
```

**Business Rules** -- `GET /api/now/table/sys_script`
```
sysparm_fields=sys_id,name,active,sys_updated_on,table_name,when,sys_created_by,sys_scope
sysparm_limit=2000
```

**Script Includes** -- `GET /api/now/table/sys_script_include`
```
sysparm_fields=sys_id,name,active,sys_updated_on,api_name,client_callable,sys_created_by,sys_scope
sysparm_limit=2000
```

`is_custom` derivation (applied to every record):
```python
is_custom = (
    record["sys_created_by"] != "system"
    and record.get("sys_scope", {}).get("value", "global") != "global"
)
```

### Failure handling

If any single call returns a non-2xx response, `SnapshotError` is raised with
the failing table name. The previous `snapshot.json` is not modified. The
caller (CLI) prints the error and exits non-zero.

---

## 6. Pydantic models

All models: `frozen=True, strict=True, extra="forbid"`.

```python
class SnapshotCounts(BaseModel):
    ai_skills: int = 0
    flows: int = 0
    business_rules: int = 0
    script_includes: int = 0

class InstanceMeta(BaseModel):
    profile: str
    url: str
    username: str
    client_id: str
    sn_version: str
    sn_build: str
    instance_name: str
    registered_at: datetime        # UTC
    last_connected_at: datetime    # UTC
    token_expires_at: datetime     # UTC
    snapshot_counts: SnapshotCounts = Field(default_factory=SnapshotCounts)

class ArtifactRecord(BaseModel):
    sys_id: str
    name: str
    active: bool
    updated_on: datetime           # UTC
    is_custom: bool
    extra: dict[str, str | bool | int] = Field(default_factory=dict)  # type-specific fields

class InstanceSnapshot(BaseModel):
    captured_at: datetime          # UTC
    sn_version: str
    ai_skills: list[ArtifactRecord] = Field(default_factory=list)
    flows: list[ArtifactRecord] = Field(default_factory=list)
    business_rules: list[ArtifactRecord] = Field(default_factory=list)
    script_includes: list[ArtifactRecord] = Field(default_factory=list)
```

Type-specific fields (skill_type, table_name, etc.) go in `extra` to keep
`ArtifactRecord` uniform across all four types while still preserving the
data for copy/capture operations.

---

## 7. Error hierarchy

```
InstanceError (base)
  InstanceNotFoundError    -- profile directory does not exist
  OAuthError               -- token exchange failed (bad creds, unreachable)
  TokenExpiredError        -- refresh token exceeded 100-day TTL
  SnapshotError            -- REST call failed during refresh
```

---

## 8. Testing

No network calls in tests. Two fakes:

**FakeSNOAuthClient:** returns a pre-configured `httpx.AsyncClient` backed by
`httpx.MockTransport`. Constructor accepts `token_expires_at` to test the
auto-refresh path.

**FakeInstanceRegistry:** in-memory dict of `InstanceMeta` objects. Satisfies
the `InstanceRegistryProtocol` structural interface so CLI commands can be
tested without touching `~/.nexus/instances/`.

Coverage targets: 100% on `models.py`, `registry.py`, `scanner.py`, `oauth.py`.
`errors.py` is excluded from the ratchet (bare exception classes).

CLI tests use `typer.testing.CliRunner` with `FakeInstanceRegistry` injected
via constructor (no monkeypatching).

---

## 9. What this enables next

With the instance registry in place, the subsequent roadmap items become
straightforward:

- **`nexus instance capture <profile> --type ai-skill --name "...":`** fetches
  the full record body from SN and writes it as a YAML template. Uses the
  snapshot sys_id as the lookup key.
- **`nexus copy <src> <dst> --type flow --name "...":`** fetches from source,
  POSTs to target. No template written.
- **Assessment gates:** Gate 1 (readiness) and Gate 2 (validation) both receive
  an `InstanceMeta` to know which instance to probe.
- **`nexus setup`:** calls `nexus instance register` as its first step.
