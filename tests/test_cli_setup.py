# tests/test_cli_setup.py
# Tests for the `nexus setup` command (idempotent gate + reauth + clean slate).
# Author: Pierre Grothe
# Date: 2026-05-18
"""Tests for nexus.cli.commands_setup._setup_main.

Exercises the gate-state matrix:

* keychain unavailable -> exit 1 before any prompt
* corrupted profile dir -> exit 1, surface path + reason
* registry empty -> clean-slate path via run_instance_setup
* profile present, tokens present -> "already configured" summary
* profile present, tokens missing -> inline reauth
* Ctrl-C orphan on SN -> provision_oauth idempotency kicks in
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import httpx
from rich.console import Console

from nexus.cli.commands_setup import _setup_main
from nexus.config.paths import NexusPaths
from nexus.instances.models import InstanceMeta
from nexus.instances.registry import InstanceRegistry
from tests.fakes.fake_keychain import FakeKeychainClient
from tests.fakes.scripted_prompt import ScriptedPromptSource


def _paths(tmp_path: object) -> NexusPaths:
    return NexusPaths(root=Path(str(tmp_path)))


def _json(status: int, payload: dict[str, object]) -> httpx.Response:
    return httpx.Response(
        status_code=status,
        content=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
    )


def _ok_handler() -> Callable[[httpx.Request], httpx.Response]:
    """Handler covering the clean-slate happy path through run_instance_setup."""

    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        method = req.method
        if method == "GET" and path == "/api/now/table/oauth_entity":
            return _json(200, {"result": []})
        if method == "POST" and path == "/api/now/table/oauth_entity":
            return _json(201, {"result": {"client_id": "cid-1"}})
        if method == "GET" and path == "/api/now/table/sys_properties":
            return _json(200, {"result": []})
        if method == "POST" and path == "/oauth_token.do":
            return _json(
                200,
                {
                    "access_token": "access-1",
                    "refresh_token": "refresh-1",
                    "expires_in": 1800,
                },
            )
        return _json(404, {"error": f"unexpected {method} {path}"})

    return handler


def _seed_meta(paths: NexusPaths, profile: str = "prod") -> InstanceMeta:
    registry = InstanceRegistry(paths.instances_dir)
    meta = InstanceMeta.create(
        profile=profile,
        url=f"https://{profile}.service-now.com",
        username="admin",
        client_id=f"cid-{profile}",
        sn_version="Xanadu",
        sn_build="04-01-2025",
        instance_name=profile,
        token_expires_in=1800,
    )
    registry.register(meta)
    return meta


def test_setup_fails_fast_when_keychain_unavailable(tmp_path: object) -> None:
    keychain = FakeKeychainClient(failure_kind="fail")
    code = _setup_main(
        paths=_paths(tmp_path),
        keychain=keychain,
        prompts=ScriptedPromptSource([]),
        console_out=Console(),
        console_err=Console(),
    )
    assert code == 1


def test_setup_surfaces_corrupted_profile_with_path(tmp_path: object) -> None:
    """AC4: scan_profile_dirs sees corrupted dir -> exit 1, no prompt."""
    paths = _paths(tmp_path)
    bad = paths.instances_dir / "broken"
    bad.mkdir(parents=True)
    (bad / "meta.json").write_text("{ not json", encoding="utf-8")
    code = _setup_main(
        paths=paths,
        keychain=FakeKeychainClient(),
        prompts=ScriptedPromptSource([]),
        console_out=Console(),
        console_err=Console(),
    )
    assert code == 1


def test_setup_runs_clean_slate_when_no_profiles_registered(tmp_path: object) -> None:
    """AC1: empty registry -> run_instance_setup -> success, profile persisted."""
    paths = _paths(tmp_path)
    keychain = FakeKeychainClient()
    prompts = ScriptedPromptSource(["new-profile", "dev12345", "admin", "pw"])
    code = _setup_main(
        paths=paths,
        keychain=keychain,
        prompts=prompts,
        console_out=Console(),
        console_err=Console(),
        transport=httpx.MockTransport(_ok_handler()),
    )
    assert code == 0
    registry = InstanceRegistry(paths.instances_dir)
    loaded = registry.load("new-profile")
    assert loaded.profile == "new-profile"


def test_setup_idempotent_skip_when_valid_profile_with_tokens_exists(
    tmp_path: object,
) -> None:
    """AC2: a profile with tokens present -> summary panel, no prompt, exit 0."""
    paths = _paths(tmp_path)
    _seed_meta(paths, "prod")
    keychain = FakeKeychainClient(
        credentials={
            ("sn-prod", "access-token"): "tok",
            ("sn-prod", "refresh-token"): "ref",
            ("sn-prod", "client-secret"): "cs",
        }
    )
    code = _setup_main(
        paths=paths,
        keychain=keychain,
        prompts=ScriptedPromptSource([]),  # empty -> any prompt would raise
        console_out=Console(),
        console_err=Console(),
    )
    assert code == 0


def test_setup_runs_inline_reauth_when_tokens_missing(tmp_path: object) -> None:
    """AC3: profile valid, no access_token in keychain -> inline re-exchange."""
    paths = _paths(tmp_path)
    _seed_meta(paths, "prod")
    keychain = FakeKeychainClient(
        credentials={
            # client_secret present but tokens are gone -> inline reauth path
            ("sn-prod", "client-secret"): "stored-secret",
        }
    )

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "POST" and req.url.path == "/oauth_token.do":
            return _json(
                200,
                {
                    "access_token": "fresh-access",
                    "refresh_token": "fresh-refresh",
                    "expires_in": 1800,
                },
            )
        return _json(404, {})

    prompts = ScriptedPromptSource(["pw-re-entered"])
    code = _setup_main(
        paths=paths,
        keychain=keychain,
        prompts=prompts,
        console_out=Console(),
        console_err=Console(),
        transport=httpx.MockTransport(handler),
    )
    assert code == 0
    assert keychain.get("sn-prod", "access-token") == "fresh-access"


def test_setup_inline_reauth_fails_when_client_secret_also_missing(
    tmp_path: object,
) -> None:
    """Tokens AND client_secret missing -> exit 1, user must delete + re-register."""
    paths = _paths(tmp_path)
    _seed_meta(paths, "prod")
    keychain = FakeKeychainClient()  # empty -- no client_secret either
    code = _setup_main(
        paths=paths,
        keychain=keychain,
        prompts=ScriptedPromptSource([]),
        console_out=Console(),
        console_err=Console(),
    )
    assert code == 1


def test_setup_inline_reauth_propagates_oauth_error(tmp_path: object) -> None:
    """If the refresh exchange fails (401), bubble it up as exit 1."""
    paths = _paths(tmp_path)
    _seed_meta(paths, "prod")
    keychain = FakeKeychainClient(credentials={("sn-prod", "client-secret"): "stored-secret"})

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "POST" and req.url.path == "/oauth_token.do":
            return _json(401, {"error": "invalid_grant", "error_description": "bad creds"})
        return _json(404, {})

    code = _setup_main(
        paths=paths,
        keychain=keychain,
        prompts=ScriptedPromptSource(["wrong-pw"]),
        console_out=Console(),
        console_err=Console(),
        transport=httpx.MockTransport(handler),
    )
    assert code == 1


def test_setup_clean_slate_propagates_oauth_error_from_exchange(
    tmp_path: object,
) -> None:
    """run_instance_setup raises OAuthError -> setup returns 1."""
    paths = _paths(tmp_path)

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "GET" and req.url.path == "/api/now/table/oauth_entity":
            return _json(200, {"result": []})
        if req.method == "POST" and req.url.path == "/api/now/table/oauth_entity":
            return _json(201, {"result": {"client_id": "cid"}})
        if req.method == "GET" and req.url.path == "/api/now/table/sys_properties":
            return _json(200, {"result": []})
        if req.method == "POST" and req.url.path == "/oauth_token.do":
            return _json(401, {"error": "invalid_grant"})
        return _json(404, {})

    code = _setup_main(
        paths=paths,
        keychain=FakeKeychainClient(),
        prompts=ScriptedPromptSource(["new-profile", "dev12345", "admin", "wrong-pw"]),
        console_out=Console(),
        console_err=Console(),
        transport=httpx.MockTransport(handler),
    )
    assert code == 1


def test_setup_resumes_after_oauth_entity_orphan(tmp_path: object) -> None:
    """AC7: a prior interrupted run left an SN oauth_entity; clean-slate finds + rotates it."""
    paths = _paths(tmp_path)
    keychain = FakeKeychainClient()

    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        method = req.method
        if (
            method == "GET"
            and path == "/api/now/table/oauth_entity"
            and req.url.params.get("sysparm_query") == "name=nexus-new-profile"
        ):
            return _json(
                200,
                {
                    "result": [
                        {
                            "name": "nexus-new-profile",
                            "client_id": "orphan-cid",
                            "sys_id": "orphan-sys",
                        }
                    ]
                },
            )
        if method == "PATCH" and path == "/api/now/table/oauth_entity/orphan-sys":
            return _json(200, {"result": {}})
        if method == "POST" and path == "/oauth_token.do":
            return _json(
                200,
                {
                    "access_token": "access-after-resume",
                    "refresh_token": "refresh-after-resume",
                    "expires_in": 1800,
                },
            )
        return _json(404, {"error": f"unexpected {method} {path}"})

    code = _setup_main(
        paths=paths,
        keychain=keychain,
        prompts=ScriptedPromptSource(["new-profile", "dev12345", "admin", "pw"]),
        console_out=Console(),
        console_err=Console(),
        transport=httpx.MockTransport(handler),
    )
    assert code == 0
    registry = InstanceRegistry(paths.instances_dir)
    loaded = registry.load("new-profile")
    assert loaded.client_id == "orphan-cid"  # reused, not duplicated
