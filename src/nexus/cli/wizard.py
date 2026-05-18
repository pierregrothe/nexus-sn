# src/nexus/cli/wizard.py
# Shared interactive flow for `nexus instance register` and `nexus setup`.
# Author: Pierre Grothe
# Date: 2026-05-18
"""run_instance_setup: prompt host/user/password, exchange OAuth, write meta.

Called by both ``nexus instance register`` (with the profile name from
the CLI argument) and the upcoming ``nexus setup`` command (with the
profile name prompted from the user). Synchronous -- matches the
existing Typer command shape.

Architecturally lives in ``cli/`` rather than ``instances/`` because it
orchestrates several CLI-layer collaborators (``provision_oauth`` from
``cli/oauth.py``, ``detect_sn_version`` from ``cli/auth.py``). Placing
it in ``instances/`` would invert the layer dependency.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from nexus.cli.auth import detect_sn_version
from nexus.cli.oauth import provision_oauth
from nexus.cli.prompts import PromptSource
from nexus.instances.errors import InvalidProfileNameError
from nexus.instances.models import InstanceMeta
from nexus.instances.oauth import SNOAuthClient
from nexus.instances.profile_name import validate_profile_name
from nexus.instances.registry import InstanceRegistry
from nexus.ui import Notice

if TYPE_CHECKING:
    from rich.console import Console

    from nexus.auth.keychain import KeychainClient
    from nexus.config.paths import NexusPaths

__all__ = ["run_instance_setup"]


def run_instance_setup(
    paths: NexusPaths,
    prompts: PromptSource,
    console_out: Console,
    *,
    profile: str | None = None,
    transport: httpx.BaseTransport | None = None,
    keychain: KeychainClient | None = None,
) -> InstanceMeta:
    """Run the host-prompt -> OAuth -> exchange -> registry-write flow.

    When ``profile`` is ``None``, prompts for a profile name in a loop
    that re-asks on validation failure (story 03 rules). When
    ``profile`` is provided (e.g. from a Typer CLI argument), trusts the
    caller to validate -- ``nexus instance register`` already accepts
    arbitrary strings, so passing through preserves backward
    compatibility.

    Args:
        paths: ``NexusPaths`` whose ``instances_dir`` receives the new
            ``meta.json``.
        prompts: ``PromptSource`` used for every interactive prompt
            (host, username, password, OAuth fallback). Tests pass a
            ``ScriptedPromptSource``.
        console_out: Rich console for user-facing status output.
        profile: Optional profile name. If ``None``, prompts for one
            with retry on validation failure.
        transport: Optional injected httpx transport passed to
            ``provision_oauth`` and ``SNOAuthClient``. Tests use this
            to drive responses without network I/O.
        keychain: Optional injected ``KeychainClient``. Tests pass a
            ``FakeKeychainClient`` so token storage stays in-memory
            instead of writing to the host OS keychain.

    Returns:
        The persisted ``InstanceMeta`` on success.

    Raises:
        OAuthError: Propagated from ``SNOAuthClient.exchange`` -- the
            caller is expected to print the error and exit with status
            1, just like ``nexus instance register`` did before this
            refactor.
    """
    if profile is None:
        profile = _prompt_profile_name(prompts, console_out)

    console_out.print(f"Registering instance '{profile}'")
    console_out.print(f"  '{profile}' is your local alias -- use it in all nexus commands.")
    console_out.print("")
    raw_url = prompts.ask("  Instance (subdomain, FQDN, or https:// URL -- e.g. dev12345)")
    host = raw_url.removeprefix("https://").removeprefix("http://").rstrip("/")
    if "." not in host:
        host = f"{host}.service-now.com"
    url = f"https://{host}"
    username = prompts.ask("  Username")
    password = prompts.ask("  Password", hide=True)

    client_id, client_secret = provision_oauth(
        url, profile, username, password, prompts, transport=transport
    )

    console_out.print("  Exchanging credentials for OAuth token...")
    oauth = SNOAuthClient(
        profile=profile,
        url=url,
        client_id=client_id,
        username=username,
        keychain=keychain,
        transport=transport,
    )
    token_response = oauth.exchange(client_secret, password)

    sn_version, sn_build, instance_name = detect_sn_version(
        url, token_response.access_token, profile
    )
    if sn_version == "unknown":
        console_out.print(
            Notice.warn(
                "Version: unknown (glide.buildtag not in sys_properties -- "
                "run with --log-level DEBUG to diagnose)"
            )
        )

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
    console_out.print(Notice.info(f"Registered {profile} ({sn_version})."))
    return meta


def _prompt_profile_name(prompts: PromptSource, console_out: Console) -> str:
    """Prompt for a profile name in a loop until validation passes.

    Args:
        prompts: ``PromptSource`` to drive the prompts.
        console_out: Rich console -- prints a Notice on each rejection.

    Returns:
        A name that satisfies ``validate_profile_name``.
    """
    while True:
        candidate = prompts.ask("  Profile name (alphanumeric, '-' or '_', up to 64 chars)")
        try:
            return validate_profile_name(candidate)
        except InvalidProfileNameError as exc:
            console_out.print(Notice.warn(f"{exc}; try again."))
