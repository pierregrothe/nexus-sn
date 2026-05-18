# src/nexus/cli/oauth.py
# OAuth provisioning + token-cap helpers extracted from cli.py for ADR-023 sizing.
# Author: Pierre Grothe
# Date: 2026-05-16
"""ServiceNow OAuth provisioning helpers.

Extracted from ``cli.py`` to keep that module marching toward the
800-line cap defined by ADR-023. These helpers run during
``nexus instance register`` and during token recovery to either reuse
or auto-create an ``oauth_entity`` record on the target SN instance.

Every helper either prints user-facing text via the shared :data:`console`
or returns a small data structure. None of them touch global registry /
Typer state.
"""

from __future__ import annotations

import uuid

import httpx

from nexus.cli.console import console
from nexus.cli.prompts import PromptSource
from nexus.ui import Notice

__all__ = [
    "fetch_existing_nexus_oauth_apps",
    "find_oauth_entity_by_name",
    "pick_existing_oauth_app",
    "print_generated_secret",
    "print_oauth_setup",
    "print_secret_recovery_steps",
    "provision_oauth",
    "warn_token_cap",
]

_CAP_PROP = "glide.oauth.access_token.expire_in.system_max_seconds"


def print_oauth_setup(url: str, profile: str) -> None:
    """Print step-by-step manual OAuth setup instructions for ServiceNow.

    Args:
        url: Full instance URL, used to build the direct navigation link.
        profile: Profile alias, used as the suggested OAuth app name.
    """
    console.print("")
    console.print("  Manual OAuth setup (one-time, ~2 minutes):")
    console.print("")
    console.print(f"  1. Open {url} and navigate to:")
    console.print("       System OAuth > Application Registry > New")
    console.print("     Choose 'Create an OAuth API endpoint for external clients'")
    console.print("")
    console.print("  2. Fill in:")
    console.print(f"       Name          nexus-{profile}")
    console.print("       Redirect URL   https://localhost  (placeholder, not used)")
    console.print("     Click Submit.")
    console.print("")
    console.print("  3. Open the record you just created:")
    console.print("       Copy the Client ID  (UUID shown at the top of the form)")
    console.print("       Click the lock icon next to Client Secret to reveal it")
    console.print("     Paste both values below.")
    console.print("")


def _httpx_client(url: str, transport: httpx.BaseTransport | None) -> httpx.Client:
    """Build an httpx.Client honoring an optional injected transport.

    Args:
        url: Base URL for the client.
        transport: Override transport. Tests pass ``httpx.MockTransport``;
            production callers pass ``None`` to use the default.

    Returns:
        A configured ``httpx.Client`` ready for ``with`` use.
    """
    if transport is None:
        return httpx.Client(base_url=url, timeout=10.0)
    return httpx.Client(base_url=url, timeout=10.0, transport=transport)


def warn_token_cap(sn: httpx.Client, username: str, password: str) -> None:
    """Print a warning if the SN system access token cap is below 8 hours.

    The property glide.oauth.access_token.expire_in.system_max_seconds overrides
    the token_lifetime on any OAuth application. When it is set below 28800 (8h),
    access tokens expire sooner, but NEXUS auto-refreshes using the 90-day refresh
    token so this does not interrupt the user. The warning tells an admin how to
    raise the cap if they want longer access tokens.

    Args:
        sn: Open httpx.Client bound to the instance base URL.
        username: SN login for Basic auth.
        password: SN password for Basic auth.
    """
    try:
        r = sn.get(
            "/api/now/table/sys_properties",
            params={
                "sysparm_query": f"name={_CAP_PROP}",
                "sysparm_fields": "value",
                "sysparm_limit": "1",
            },
            auth=(username, password),
        )
        if r.status_code != 200:
            return
        rows = r.json().get("result", [])
        if not rows:
            return
        cap = int(rows[0].get("value", "0"))
        if 0 < cap < 28800:
            console.print(f"  Note: SN system cap limits access tokens to {cap // 60} min.")
            console.print("  NEXUS auto-refreshes silently -- this will not interrupt your work.")
            console.print("  To set 8h tokens, an admin can run in a SN background script:")
            console.print(f"    gs.setProperty('{_CAP_PROP}', '28800');")
    except Exception:  # non-fatal -- registration already succeeded
        pass


def fetch_existing_nexus_oauth_apps(
    url: str,
    username: str,
    password: str,
    *,
    transport: httpx.BaseTransport | None = None,
) -> list[dict[str, str]]:
    """Return oauth_entity records whose name starts with ``nexus-``.

    Lists OAuth applications already provisioned on the SN instance (e.g. by
    another Nexus install registered against the same instance). Returns ``[]``
    on any failure -- the caller treats that as 'no existing apps'.

    Args:
        url: Full instance URL.
        username: SN login for Basic auth.
        password: SN password for Basic auth.
        transport: Optional injected httpx transport; tests pass a
            MockTransport to drive the response.

    Returns:
        Each entry has keys ``name``, ``client_id``, ``sys_id``, ``sys_created_on``.
        Entries without a ``client_id`` are dropped.
    """
    try:
        with _httpx_client(url, transport) as sn:
            resp = sn.get(
                "/api/now/table/oauth_entity",
                params={
                    "sysparm_query": "nameSTARTSWITHnexus-",
                    "sysparm_fields": "name,client_id,sys_id,sys_created_on",
                    "sysparm_limit": "100",
                },
                auth=(username, password),
            )
        if resp.status_code != 200:
            return []
        rows = resp.json().get("result", [])
        return [
            {
                "name": str(r.get("name", "")),
                "client_id": str(r.get("client_id", "")),
                "sys_id": str(r.get("sys_id", "")),
                "sys_created_on": str(r.get("sys_created_on", "")),
            }
            for r in rows
            if r.get("client_id")
        ]
    except httpx.RequestError, ValueError:
        return []


def find_oauth_entity_by_name(
    url: str,
    name: str,
    username: str,
    password: str,
    *,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, str] | None:
    """Return the oauth_entity record with exact ``name``, or None.

    Used by ``provision_oauth`` to detect an orphan from a prior run that
    was interrupted between OAuth-entity creation and local token
    storage. When found, ``provision_oauth`` PATCHes the entity with a
    fresh secret instead of POSTing a duplicate.

    Args:
        url: Full instance URL.
        name: Exact ``oauth_entity.name`` value to look up (e.g.
            ``"nexus-prod"``).
        username: SN login for Basic auth.
        password: SN password for Basic auth.
        transport: Optional injected httpx transport for tests.

    Returns:
        Dict with keys ``name``, ``client_id``, ``sys_id`` when one
        match exists; ``None`` on no match, ambiguous matches, network
        error, or any non-200 response.
    """
    try:
        with _httpx_client(url, transport) as sn:
            resp = sn.get(
                "/api/now/table/oauth_entity",
                params={
                    "sysparm_query": f"name={name}",
                    "sysparm_fields": "name,client_id,sys_id",
                    "sysparm_limit": "2",
                },
                auth=(username, password),
            )
        if resp.status_code != 200:
            return None
        rows = resp.json().get("result", [])
        if len(rows) != 1:
            return None
        row = rows[0]
        client_id = str(row.get("client_id", ""))
        sys_id = str(row.get("sys_id", ""))
        if not client_id or not sys_id:
            return None
        return {"name": str(row.get("name", name)), "client_id": client_id, "sys_id": sys_id}
    except httpx.RequestError, ValueError:
        return None


def print_generated_secret(secret: str) -> None:
    """Print a freshly-generated OAuth client_secret with save-it instructions.

    ServiceNow stores ``client_secret`` as a ``password2`` field, so the value
    we just POSTed is the last time it will be readable. The user must save it
    somewhere durable (password manager) before continuing; otherwise reusing
    this OAuth app from another machine requires either re-rotating the secret
    or running the background-script recovery recipe.

    Args:
        secret: The cleartext client_secret we just provisioned.
    """
    console.print("")
    console.print(Notice.warn("Save this client secret -- ServiceNow will mask it after now."))
    console.print(f"    Client secret: {secret}")
    console.print(
        "    Store it in your password manager so you can register this same "
        "OAuth app from other machines."
    )
    console.print("")


def print_secret_recovery_steps(url: str, sys_id: str, name: str) -> None:
    """Print copy-paste instructions for retrieving an existing OAuth secret.

    ServiceNow stores ``oauth_entity.client_secret`` as a ``password2`` (encrypted)
    field and the Table API masks it on every GET, by design. The only way to
    read the cleartext is via a server-side script context that can call
    ``GlideElement.getDecryptedValue()`` -- typically a background script.

    Args:
        url: Full instance URL.
        sys_id: ``oauth_entity.sys_id`` of the picked app.
        name: OAuth app name (e.g. ``nexus-prod``), shown for visual context.
    """
    console.print("")
    console.print(
        f"  ServiceNow does not return client secrets via REST. To recover the "
        f"secret for '{name}', run this in your SN instance:"
    )
    console.print("")
    console.print(f"    1. Open  {url}/sys.scripts.do  (System Definition > Scripts - Background).")
    console.print("    2. Paste this script and click Run script:")
    console.print("")
    console.print("       var gr = new GlideRecord('oauth_entity');")
    console.print(f"       gr.get('{sys_id}');")
    console.print("       gs.print(gr.client_secret.getDecryptedValue());")
    console.print("")
    console.print("    3. Copy the line printed below '*** Script:' and paste it here.")
    console.print("")


def pick_existing_oauth_app(
    entries: list[dict[str, str]],
    profile: str,
    url: str,
    prompts: PromptSource,
) -> tuple[str, str] | None:
    """Prompt the user to reuse an existing Nexus OAuth app or create a new one.

    The client_secret is not retrievable from ServiceNow (the Table API masks
    password2 fields), so the user must either paste it from another Nexus
    install or run the background-script recipe printed below the prompt.

    Args:
        entries: Output of ``fetch_existing_nexus_oauth_apps``. Must be non-empty.
        profile: Profile being registered -- shown in the "create new" option.
        url: Full instance URL, used to build the Scripts - Background link.
        prompts: ``PromptSource`` used for the choice prompt and secret entry.

    Returns:
        ``(client_id, client_secret)`` if the user picks an existing entry and
        supplies the secret, or ``None`` if they choose to create a new app.
    """
    console.print("")
    console.print(f"  Found {len(entries)} existing Nexus OAuth app(s) on this instance:")
    for i, entry in enumerate(entries, 1):
        console.print(
            f"    {i}. {entry['name']}  "
            f"(client_id={entry['client_id']}, created {entry['sys_created_on']})"
        )
    console.print(f"    n. Create a new app named 'nexus-{profile}'")
    console.print("")
    raw = prompts.ask(f"  Pick one (1-{len(entries)}) or 'n' for new")
    choice = raw.strip().lower()
    if choice == "n":
        return None
    try:
        idx = int(choice)
    except ValueError:
        console.print(f"  Invalid choice {raw!r}; will create a new app.")
        return None
    if not 1 <= idx <= len(entries):
        console.print(f"  Choice {idx} out of range; will create a new app.")
        return None
    picked = entries[idx - 1]
    console.print(f"  Reusing OAuth app '{picked['name']}' (client_id={picked['client_id']}).")
    print_secret_recovery_steps(url=url, sys_id=picked["sys_id"], name=picked["name"])
    secret = prompts.ask("  OAuth Client Secret", hide=True)
    return picked["client_id"], secret


def provision_oauth(
    url: str,
    profile: str,
    username: str,
    password: str,
    prompts: PromptSource,
    *,
    transport: httpx.BaseTransport | None = None,
) -> tuple[str, str]:
    """Reuse or auto-create an OAuth app in SN; fall back to manual prompts on failure.

    Resilience to interrupted prior runs (story 05 AC1/AC2): before
    attempting to create, looks up the deterministic entity name
    ``nexus-<profile>``. When found (orphan from a Ctrl-C'd run), rotates
    the secret via PATCH and returns the existing ``client_id`` with the
    new secret -- so the SN instance never accumulates duplicate
    ``oauth_entity`` records on retry.

    When no deterministic match exists, queries for any ``nexus-*`` apps
    the user might want to reuse, then falls back to POSTing a new
    record. On any HTTP error the user is shown manual setup
    instructions and prompted to enter the credentials by hand via
    ``prompts``.

    Args:
        url: Full instance URL.
        profile: Profile alias used as the OAuth app name suffix.
        username: SN login for Basic auth.
        password: SN password for Basic auth.
        prompts: ``PromptSource`` for all interactive input (no direct
            ``typer.prompt`` calls remain in this module).
        transport: Optional injected httpx transport; tests pass a
            MockTransport to drive responses.

    Returns:
        Tuple of (client_id, client_secret).
    """
    name = f"nexus-{profile}"
    orphan = find_oauth_entity_by_name(url, name, username, password, transport=transport)
    if orphan is not None:
        rotated = _rotate_oauth_secret(url, orphan["sys_id"], username, password, transport)
        if rotated is not None:
            console.print(f"  Reused OAuth app {name!r} from a prior run (rotated secret).")
            return orphan["client_id"], rotated

    existing = fetch_existing_nexus_oauth_apps(url, username, password, transport=transport)
    if existing:
        picked = pick_existing_oauth_app(existing, profile, url, prompts)
        if picked is not None:
            return picked

    generated_secret = str(uuid.uuid4())
    fail_reason = ""
    try:
        with _httpx_client(url, transport) as sn:
            resp = sn.post(
                "/api/now/table/oauth_entity",
                json={
                    "name": name,
                    "type": "oauth2",
                    "client_secret": generated_secret,
                    "redirect_url": "https://localhost",
                    "token_lifetime": "28800",  # 8h -- may be overridden by SN system cap
                    "refresh_token_lifetime": "7776000",  # 90 days -- survives access token cap
                },
                auth=(username, password),
            )
            if resp.status_code == 201:
                result = resp.json().get("result", {})
                client_id = str(result.get("client_id", ""))
                if client_id:
                    console.print(f"  Created OAuth application {name!r} automatically.")
                    print_generated_secret(generated_secret)
                    warn_token_cap(sn, username, password)
                    return client_id, generated_secret
                fail_reason = "HTTP 201 but no client_id in response"
            else:
                fail_reason = f"HTTP {resp.status_code}"
    except httpx.RequestError as exc:
        fail_reason = str(exc)

    console.print(f"  Could not auto-create OAuth credentials ({fail_reason}).")
    print_oauth_setup(url, profile)
    client_id = prompts.ask("  OAuth Client ID")
    client_secret = prompts.ask("  OAuth Client Secret", hide=True)
    return client_id, client_secret


def _rotate_oauth_secret(
    url: str,
    sys_id: str,
    username: str,
    password: str,
    transport: httpx.BaseTransport | None,
) -> str | None:
    """PATCH the named oauth_entity with a fresh secret; return the new value or None.

    The PATCH request sends a freshly generated UUID as ``client_secret``.
    On success the value we sent is the value we keep -- SN masks the
    field in its echoed response, so the locally generated UUID is the
    new secret.

    Args:
        url: Full instance URL.
        sys_id: ``oauth_entity.sys_id`` of the record to rotate.
        username: SN login for Basic auth.
        password: SN password for Basic auth.
        transport: Optional injected httpx transport for tests.

    Returns:
        The newly assigned ``client_secret`` on PATCH success (HTTP
        200), or ``None`` on any failure (caller treats as 'rotation
        failed; fall back to listing existing apps').
    """
    new_secret = str(uuid.uuid4())
    try:
        with _httpx_client(url, transport) as sn:
            resp = sn.patch(
                f"/api/now/table/oauth_entity/{sys_id}",
                json={"client_secret": new_secret},
                auth=(username, password),
            )
    except httpx.RequestError:
        return None
    if resp.status_code != 200:
        return None
    return new_secret
