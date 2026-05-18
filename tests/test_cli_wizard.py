# tests/test_cli_wizard.py
# Tests for run_instance_setup (shared by `instance register` + `setup`).
# Author: Pierre Grothe
# Date: 2026-05-18
"""Tests for nexus.cli.wizard.run_instance_setup.

Drives the real flow with ``ScriptedPromptSource``, ``FakeKeychainClient``,
and ``httpx.MockTransport``. Confirms:

* AC1: clean-slate happy path -- registry receives meta.json, tokens
  reach the keychain.
* AC2: validate_profile_name rejection triggers a retry inside the
  helper -- no exception leaks to the caller.
* AC3: OAuthError from exchange propagates so callers (instance
  register) can show the error message and exit non-zero.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from rich.console import Console

from nexus.cli.wizard import run_instance_setup
from nexus.config.paths import NexusPaths
from nexus.instances.errors import OAuthError
from nexus.instances.registry import InstanceRegistry
from tests.fakes.fake_keychain import FakeKeychainClient
from tests.fakes.scripted_prompt import ScriptedPromptSource


def _paths(tmp_path: object) -> NexusPaths:
    """Return a NexusPaths anchored at the pytest tmp_path."""
    return NexusPaths(root=Path(str(tmp_path)))


def _json(status: int, payload: dict[str, object]) -> httpx.Response:
    return httpx.Response(
        status_code=status,
        content=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
    )


def _ok_handler() -> Callable[[httpx.Request], httpx.Response]:
    """Handler covering the full register happy path (POST oauth + token grant)."""

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


def test_run_instance_setup_writes_meta_json_on_happy_path(tmp_path: object) -> None:
    paths = _paths(tmp_path)
    prompts = ScriptedPromptSource(["dev12345", "admin", "secret-pw"])
    keychain = FakeKeychainClient()

    meta = run_instance_setup(
        paths,
        prompts,
        Console(),
        profile="dev",
        transport=httpx.MockTransport(_ok_handler()),
        keychain=keychain,
    )

    assert meta.profile == "dev"
    assert meta.url == "https://dev12345.service-now.com"
    assert meta.username == "admin"
    assert meta.client_id == "cid-1"

    registry = InstanceRegistry(paths.instances_dir)
    loaded = registry.load("dev")
    assert loaded.profile == "dev"
    assert loaded.client_id == "cid-1"


def test_run_instance_setup_stores_oauth_tokens_in_keychain(tmp_path: object) -> None:
    paths = _paths(tmp_path)
    prompts = ScriptedPromptSource(["dev12345", "admin", "secret-pw"])
    keychain = FakeKeychainClient()

    run_instance_setup(
        paths,
        prompts,
        Console(),
        profile="prod",
        transport=httpx.MockTransport(_ok_handler()),
        keychain=keychain,
    )

    assert keychain.get("sn-prod", "access-token") == "access-1"
    assert keychain.get("sn-prod", "refresh-token") == "refresh-1"


def test_run_instance_setup_prompts_for_profile_when_none_given(tmp_path: object) -> None:
    """AC: when profile=None, helper prompts (story 03 validator applied)."""
    paths = _paths(tmp_path)
    prompts = ScriptedPromptSource(["valid-profile", "dev12345", "admin", "secret-pw"])
    keychain = FakeKeychainClient()

    meta = run_instance_setup(
        paths,
        prompts,
        Console(),
        transport=httpx.MockTransport(_ok_handler()),
        keychain=keychain,
    )

    assert meta.profile == "valid-profile"


def test_run_instance_setup_retries_profile_prompt_when_validation_rejects(
    tmp_path: object,
) -> None:
    """AC2: invalid profile name triggers re-prompt; no exception leaks."""
    paths = _paths(tmp_path)
    # First answer fails (path traversal); second is accepted.
    prompts = ScriptedPromptSource(["../bad", "good-name", "dev12345", "admin", "pw"])
    keychain = FakeKeychainClient()

    meta = run_instance_setup(
        paths,
        prompts,
        Console(),
        transport=httpx.MockTransport(_ok_handler()),
        keychain=keychain,
    )

    assert meta.profile == "good-name"


def test_run_instance_setup_normalizes_bare_subdomain_to_service_now_url(
    tmp_path: object,
) -> None:
    paths = _paths(tmp_path)
    prompts = ScriptedPromptSource(["devshort", "admin", "pw"])
    keychain = FakeKeychainClient()

    meta = run_instance_setup(
        paths,
        prompts,
        Console(),
        profile="p",
        transport=httpx.MockTransport(_ok_handler()),
        keychain=keychain,
    )

    assert meta.url == "https://devshort.service-now.com"


def test_run_instance_setup_strips_scheme_and_trailing_slash_from_url(
    tmp_path: object,
) -> None:
    paths = _paths(tmp_path)
    prompts = ScriptedPromptSource(["https://dev.example.com/", "admin", "pw"])
    keychain = FakeKeychainClient()

    meta = run_instance_setup(
        paths,
        prompts,
        Console(),
        profile="p",
        transport=httpx.MockTransport(_ok_handler()),
        keychain=keychain,
    )

    assert meta.url == "https://dev.example.com"


def test_run_instance_setup_propagates_oauth_error_from_exchange(
    tmp_path: object,
) -> None:
    """AC3: OAuthError from token grant bubbles up unchanged."""
    paths = _paths(tmp_path)

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "GET" and req.url.path == "/api/now/table/oauth_entity":
            return _json(200, {"result": []})
        if req.method == "POST" and req.url.path == "/api/now/table/oauth_entity":
            return _json(201, {"result": {"client_id": "cid"}})
        if req.method == "GET" and req.url.path == "/api/now/table/sys_properties":
            return _json(200, {"result": []})
        if req.method == "POST" and req.url.path == "/oauth_token.do":
            return _json(
                401,
                {"error": "invalid_grant", "error_description": "bad credentials"},
            )
        return _json(404, {})

    prompts = ScriptedPromptSource(["dev12345", "admin", "wrong-pw"])
    keychain = FakeKeychainClient()

    with pytest.raises(OAuthError):
        run_instance_setup(
            paths,
            prompts,
            Console(),
            profile="dev",
            transport=httpx.MockTransport(handler),
            keychain=keychain,
        )


def test_run_instance_setup_handles_unknown_sn_version_gracefully(
    tmp_path: object,
) -> None:
    """detect_sn_version's network call fails (no real server) -> 'unknown'."""
    paths = _paths(tmp_path)
    prompts = ScriptedPromptSource(["dev12345", "admin", "pw"])
    keychain = FakeKeychainClient()

    meta = run_instance_setup(
        paths,
        prompts,
        Console(),
        profile="dev",
        transport=httpx.MockTransport(_ok_handler()),
        keychain=keychain,
    )

    # detect_sn_version uses its own httpx.Client (no transport passed in),
    # so it makes a real network call to a fake host -> fails -> "unknown".
    assert meta.sn_version == "unknown"
