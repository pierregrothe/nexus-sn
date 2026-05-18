# src/nexus/cli/commands_setup.py
# `nexus setup` -- idempotent first-run wizard for the credential setup flow.
# Author: Pierre Grothe
# Date: 2026-05-18
"""nexus setup: probe keychain, scan profiles, dispatch to the right flow.

States the command handles:

1. Keychain unavailable -> print distro hint, exit 1.
2. Corrupted profile dir found by ``scan_profile_dirs`` -> print path
   and reason, exit 1.
3. No profiles registered -> run ``run_instance_setup`` clean-slate,
   print summary + closing Notice, exit 0.
4. Profile exists but its tokens are missing in the keychain -> inline
   re-auth flow (re-prompt password, re-exchange tokens), print
   "tokens restored" + closing Notice, exit 0.
5. All profiles valid + tokens present -> print summary panel and a
   Hint pointing at ``nexus instance register`` / ``nexus reauth`` /
   ``nexus sync``, exit 0.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import typer

from nexus.auth.errors import AuthError, KeychainUnavailableError
from nexus.auth.keychain import KeychainClient
from nexus.cli.apps import app
from nexus.cli.console import console, err_console
from nexus.cli.prompts import PromptSource, TyperPromptSource
from nexus.cli.wizard import run_instance_setup
from nexus.config.paths import NexusPaths
from nexus.instances.errors import OAuthError
from nexus.instances.oauth import SNOAuthClient
from nexus.instances.registry import InstanceRegistry
from nexus.ui import Hint, KeyValuePanel, KvRow, Notice

if TYPE_CHECKING:
    from rich.console import Console

    from nexus.instances.models import InstanceMeta

__all__: list[str] = []

_NEXT_STEP_MESSAGE = "Next: run `nexus sync` to pull the template catalog."


@app.command()
def setup() -> None:
    """First-run wizard: configure credentials and register your first instance.

    Idempotent: safe to re-run. Detects an already-configured installation
    and prints a summary instead of starting over.
    """
    exit_code = _setup_main(
        paths=NexusPaths.from_env(),
        keychain=KeychainClient(),
        prompts=TyperPromptSource(),
        console_out=console,
        console_err=err_console,
    )
    if exit_code != 0:
        raise typer.Exit(exit_code)


def _setup_main(
    *,
    paths: NexusPaths,
    keychain: KeychainClient,
    prompts: PromptSource,
    console_out: Console,
    console_err: Console,
    transport: httpx.BaseTransport | None = None,
) -> int:
    """Core setup logic; returns exit code (0 success, 1 error).

    Extracted from the Typer ``setup`` command so tests can call it
    directly with fake collaborators (``FakeKeychainClient``,
    ``ScriptedPromptSource``, ``httpx.MockTransport``) without going
    through the Typer ``CliRunner``.

    Args:
        paths: ``NexusPaths`` rooted at the runtime ``.nexus/`` dir.
        keychain: ``KeychainClient`` for probing backend availability
            and storing/retrieving tokens.
        prompts: ``PromptSource`` for every interactive input.
        console_out: Rich console for user-facing status output.
        console_err: Rich console for errors.
        transport: Optional injected httpx transport, forwarded to
            ``run_instance_setup`` and ``SNOAuthClient``.

    Returns:
        0 on success; 1 on any error path (keychain unavailable,
        corrupted profile, OAuth failure during clean-slate or inline
        reauth).
    """
    try:
        keychain.check_available()
    except KeychainUnavailableError as exc:
        console_err.print(Notice.error(f"OS keychain unavailable: {exc.hint}"))
        return 1

    registry = InstanceRegistry(paths.instances_dir)
    scan = registry.scan_profile_dirs()

    if scan.corrupted:
        for entry in scan.corrupted:
            console_err.print(Notice.error(f"Corrupted profile at {entry.path}: {entry.reason}"))
        console_err.print(
            Hint(
                label="Resolve",
                command="inspect or remove the offending file, then re-run nexus setup",
            )
        )
        return 1

    if not scan.valid:
        return _run_clean_slate(
            paths=paths,
            keychain=keychain,
            prompts=prompts,
            console_out=console_out,
            console_err=console_err,
            transport=transport,
        )

    needs_reauth = [m for m in scan.valid if not _has_access_token(keychain, m.profile)]
    if needs_reauth:
        return _run_inline_reauth(
            metas=needs_reauth,
            keychain=keychain,
            prompts=prompts,
            console_out=console_out,
            console_err=console_err,
            transport=transport,
        )

    _print_already_configured_summary(scan.valid, console_out=console_out)
    console_out.print(Notice.info(_NEXT_STEP_MESSAGE))
    return 0


def _run_clean_slate(
    *,
    paths: NexusPaths,
    keychain: KeychainClient,
    prompts: PromptSource,
    console_out: Console,
    console_err: Console,
    transport: httpx.BaseTransport | None,
) -> int:
    """Run ``run_instance_setup`` and print the summary + next-step Notice."""
    try:
        meta = run_instance_setup(
            paths,
            prompts,
            console_out,
            transport=transport,
            keychain=keychain,
        )
    except OAuthError as exc:
        console_err.print(Notice.error(str(exc)))
        return 1
    _print_already_configured_summary([meta], console_out=console_out)
    console_out.print(Notice.info(_NEXT_STEP_MESSAGE))
    return 0


def _run_inline_reauth(
    *,
    metas: list[InstanceMeta],
    keychain: KeychainClient,
    prompts: PromptSource,
    console_out: Console,
    console_err: Console,
    transport: httpx.BaseTransport | None,
) -> int:
    """Re-prompt password and re-run the OAuth exchange for each profile."""
    for meta in metas:
        console_out.print(
            Notice.info(f"Tokens missing for profile {meta.profile!r}; re-auth required")
        )
        try:
            client_secret = keychain.get(f"sn-{meta.profile}", "client-secret")
        except AuthError:
            console_err.print(
                Notice.error(
                    f"Cannot recover {meta.profile!r}: client_secret is also missing. "
                    f"Delete and re-register the profile."
                )
            )
            return 1
        password = prompts.ask(f"  Password for {meta.username} on {meta.url}", hide=True)
        oauth = SNOAuthClient(
            profile=meta.profile,
            url=meta.url,
            client_id=meta.client_id,
            username=meta.username,
            keychain=keychain,
            transport=transport,
        )
        try:
            oauth.exchange(client_secret, password)
        except OAuthError as exc:
            console_err.print(Notice.error(str(exc)))
            return 1
        console_out.print(Notice.info(f"Tokens restored for {meta.profile!r}."))
    console_out.print(Notice.info(_NEXT_STEP_MESSAGE))
    return 0


def _has_access_token(keychain: KeychainClient, profile: str) -> bool:
    """Return True when the keychain has an access_token for ``profile``."""
    try:
        keychain.get(f"sn-{profile}", "access-token")
    except AuthError:
        return False
    return True


def _print_already_configured_summary(
    metas: list[InstanceMeta] | tuple[InstanceMeta, ...], *, console_out: Console
) -> None:
    """Print a KeyValuePanel of registered instances and a Hint to common next commands."""
    console_out.print(
        KeyValuePanel(
            title="Registered instances",
            rows=[KvRow(label=m.profile, value=m.url) for m in metas],
        )
    )
    console_out.print(
        Hint(
            label="What next?",
            command="nexus instance register <profile>",
            suffix="(add another) | nexus reauth | nexus sync",
        )
    )
