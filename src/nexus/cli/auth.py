# src/nexus/cli/auth.py
# Auth + profile resolution helpers extracted from cli/__init__.py for ADR-023 sizing.
# Author: Pierre Grothe
# Date: 2026-05-16
"""Profile resolution, token acquisition, and SN version detection.

Extracted from ``cli/__init__.py`` to keep that module marching toward
the 800-line cap defined by ADR-023. Every helper either resolves a
profile to an :class:`InstanceRegistry` + :class:`InstanceMeta` pair,
acquires / refreshes an OAuth bearer token, or probes the SN instance
for build tag / version metadata.

The helpers print user-facing prompts via the shared ``console`` and
exit with ``typer.Exit`` on unrecoverable errors, matching the
existing CLI surface.
"""

from __future__ import annotations

import logging
from datetime import datetime

import httpx
import typer

from nexus.auth.external_keychain import ExternalKeychainClient
from nexus.capabilities.claude_config import FilesystemClaudeCodeConfigReader
from nexus.capabilities.tier import TierDetection, TierDetector
from nexus.cli.console import console, err_console
from nexus.config.manager import ConfigManager
from nexus.config.paths import NexusPaths
from nexus.config.settings import InstancesConfig
from nexus.instances.errors import InstanceNotFoundError, OAuthError, TokenExpiredError
from nexus.instances.models import InstanceMeta
from nexus.instances.oauth import SNOAuthClient
from nexus.instances.registry import InstanceRegistry

__all__ = [
    "acquire_token",
    "config_default",
    "detect_sn_version",
    "detect_tier",
    "instance_registry",
    "oauth_for",
    "parse_buildtag_version",
    "parse_stats_do",
    "resolve_profile",
    "set_default_profile",
]

log = logging.getLogger(__name__)


def detect_tier() -> TierDetection:
    """Run tier detection using a Claude-Code-aware keychain reader."""
    reader = FilesystemClaudeCodeConfigReader(keychain=ExternalKeychainClient())
    return TierDetector(reader=reader).detect()


def instance_registry() -> InstanceRegistry:
    """Return an InstanceRegistry rooted at the current config path.

    Returns:
        InstanceRegistry for NexusPaths.from_env().instances_dir.
    """
    return InstanceRegistry(NexusPaths.from_env().instances_dir)


def config_default() -> str:
    """Return the default instance profile from config.

    Returns:
        Profile name string, or empty string if not set.
    """
    return ConfigManager(NexusPaths.from_env()).load().instances.default


def resolve_profile(profile: str) -> tuple[InstanceRegistry, InstanceMeta]:
    """Resolve an optional profile to a registry and loaded meta.

    Args:
        profile: Profile name, or empty string to use the config default.

    Returns:
        Tuple of (registry, meta) for the resolved profile.

    Raises:
        SystemExit: Via typer.Exit if no default is set or the profile is not found.
    """
    if not profile:
        profile = config_default()
    if not profile:
        err_console.print("No default instance set.")
        err_console.print("  Register one : nexus instance register <profile>")
        err_console.print("  Set default  : nexus instance use <profile>")
        err_console.print("  List all     : nexus instance")
        raise typer.Exit(1)
    registry = instance_registry()
    try:
        return registry, registry.load(profile)
    except InstanceNotFoundError as exc:
        err_console.print(str(exc))
        raise typer.Exit(1) from exc


def oauth_for(profile: str, meta: InstanceMeta) -> SNOAuthClient:
    """Build an SNOAuthClient for a profile and its stored meta.

    Args:
        profile: Instance profile name.
        meta: InstanceMeta loaded from the registry.

    Returns:
        Configured SNOAuthClient.
    """
    return SNOAuthClient(
        profile=profile, url=meta.url, client_id=meta.client_id, username=meta.username
    )


def set_default_profile(paths: NexusPaths, profile: str) -> None:
    """Persist profile as the default instance in config.

    Args:
        paths: NexusPaths for the current config root.
        profile: Profile name to set as default (empty string to clear).
    """
    manager = ConfigManager(paths)
    manager.save(manager.load().model_copy(update={"instances": InstancesConfig(default=profile)}))


def parse_buildtag_version(value: str) -> str:
    """Extract the human-readable SN release name from a glide.buildtag value.

    Args:
        value: Raw property value, e.g. ``"glide-xanadu-..."`` or ``"xanadu-..."``.

    Returns:
        Capitalised release name (e.g. ``"Xanadu"``), or the first dash-separated
        token when the value does not start with ``glide-``.
    """
    parts = value.split("-")
    word = parts[1] if parts[0].lower() == "glide" and len(parts) > 1 else parts[0]
    return word.capitalize()


def parse_stats_do(text: str) -> tuple[str, str]:
    """Extract build tag + version from a /stats.do response body.

    ``/stats.do`` returns plain text or HTML with lines like::

        Build tag: glide-yokohama-09-04-2025__patch4-01-22-2026
        Build name: Yokohama

    Args:
        text: Raw response body.

    Returns:
        ``(build_tag, version)`` -- ``("", "unknown")`` when no match found.
    """
    for raw_line in text.splitlines():
        line = raw_line.strip()
        # Match "Build tag:" or "<br/>Build tag:" in HTML-formatted responses.
        if "Build tag:" not in line:
            continue
        val = line.split("Build tag:", 1)[1].strip()
        # Strip trailing HTML breaks / tags
        for sep in ("<br", "</", "&nbsp;"):
            if sep in val:
                val = val.split(sep, 1)[0].strip()
        if val:
            return val, parse_buildtag_version(val)
    return "", "unknown"


def detect_sn_version(url: str, token: str, profile: str) -> tuple[str, str, str]:
    """Query sys_properties to detect the SN version, build tag, and instance name.

    Tries glide.buildtag first; falls back to a LIKE search across all
    properties whose name contains 'buildtag' in case the exact key is absent.

    Args:
        url: Full instance URL.
        token: Valid Bearer token.
        profile: Fallback value for instance_name if the property is not found.

    Returns:
        Tuple of (sn_version, sn_build, instance_name). sn_version is
        'unknown' when the buildtag property is missing or unreadable.
    """
    sn_version = "unknown"
    sn_build = ""
    instance_name = profile
    try:
        with httpx.Client(
            base_url=url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        ) as client:
            _BUILDTAG_PROPS = ("glide.buildtag", "glide.buildtag.last")
            for prop in (*_BUILDTAG_PROPS, "instance_name"):
                if prop in _BUILDTAG_PROPS and sn_version != "unknown":
                    continue
                r = client.get(
                    "/api/now/table/sys_properties",
                    params={
                        "sysparm_query": f"name={prop}",
                        "sysparm_fields": "value",
                        "sysparm_limit": 1,
                    },
                )
                log.debug(
                    "version probe name=%s status=%d body=%.200s",
                    prop,
                    r.status_code,
                    r.text,
                )
                if r.status_code != 200:
                    continue
                rows = r.json().get("result", [])
                if not rows:
                    continue
                val = str(rows[0].get("value", "")).strip()
                if not val:
                    continue
                if prop in _BUILDTAG_PROPS:
                    sn_build = val
                    sn_version = parse_buildtag_version(val)
                else:
                    instance_name = val

            if sn_version == "unknown":
                r = client.get(
                    "/api/now/table/sys_properties",
                    params={
                        "sysparm_query": "nameLIKEbuildtag",
                        "sysparm_fields": "name,value",
                        "sysparm_limit": 3,
                    },
                )
                log.debug("version fallback status=%d body=%.300s", r.status_code, r.text)
                if r.status_code == 200:
                    for row in r.json().get("result", []):
                        val = str(row.get("value", "")).strip()
                        if val:
                            sn_build = val
                            sn_version = parse_buildtag_version(val)
                            break

            # On many PDIs an ACL blocks reading `glide.buildtag*` via the
            # Table API but `/stats.do` returns the same info as plain text.
            if sn_version == "unknown":
                r = client.get("/stats.do")
                log.debug("stats.do fallback status=%d body=%.300s", r.status_code, r.text[:300])
                if r.status_code == 200 and r.text:
                    sn_build, sn_version = parse_stats_do(r.text)

    except httpx.RequestError:
        pass
    return sn_version, sn_build, instance_name


def acquire_token(
    profile: str,
) -> tuple[InstanceRegistry, InstanceMeta, str, datetime]:
    """Resolve profile, acquire bearer token, reconnecting automatically if expired.

    When both the access token and refresh token are expired, prompts the user
    for their ServiceNow password and re-authenticates transparently so the
    caller can continue without manual intervention.

    Args:
        profile: Instance profile name (empty string uses config default).

    Returns:
        (registry, meta, bearer_token, token_expiry)
    """
    registry, meta = resolve_profile(profile)
    oauth = oauth_for(meta.profile, meta)
    try:
        token, expiry = oauth.get_bearer_token(meta.token_expires_at)
        # Persist the refreshed expiry so nexus instance list shows the correct status.
        if expiry != meta.token_expires_at:
            registry.save(meta.model_copy(update={"token_expires_at": expiry}))
        return registry, meta, token, expiry
    except TokenExpiredError:
        console.print(f"Session expired for {meta.profile!r}. Reconnecting...")
    try:
        password: str = typer.prompt("ServiceNow password", hide_input=True)
        token, expiry = oauth.reconnect(password)
    except OAuthError as exc:
        err_console.print(f"Reconnect failed: {exc}")
        raise typer.Exit(1) from exc
    registry.save(meta.model_copy(update={"token_expires_at": expiry}))
    console.print(f"Reconnected. Token valid until {expiry.strftime('%H:%M UTC')}.")
    return registry, meta, token, expiry
