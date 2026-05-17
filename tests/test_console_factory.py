# tests/test_console_factory.py
# Tests for make_console + argv_has_plain pre-scan.
# Author: Pierre Grothe
# Date: 2026-05-15

"""Cover the process-startup factory and argv pre-scan."""

import pytest

from nexus.ui.capabilities import RenderProfile
from nexus.ui.console_factory import argv_has_plain, make_console


def test_argvhasplain_with_plain_flag_returns_true() -> None:
    assert argv_has_plain(["nexus", "plugins", "list", "--plain"]) is True


def test_argvhasplain_without_plain_flag_returns_false() -> None:
    assert argv_has_plain(["nexus", "plugins", "list"]) is False


def test_argvhasplain_ignores_program_name() -> None:
    assert argv_has_plain(["--plain"]) is False


def test_argvhasplain_with_no_arguments_returns_false() -> None:
    assert argv_has_plain([]) is False


def test_argvhasplain_defaults_to_sys_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["nexus", "--plain"])
    assert argv_has_plain() is True


def test_makeconsole_returns_render_context_with_console_attached() -> None:
    ctx = make_console(forced_plain=True, environ={}, argv=["nexus"])
    assert ctx.console is not None
    assert ctx.profile is RenderProfile.PLAIN


def test_makeconsole_argv_plain_forces_plain_profile() -> None:
    ctx = make_console(environ={}, argv=["nexus", "plugins", "list", "--plain"])
    assert ctx.profile is RenderProfile.PLAIN


def test_makeconsole_env_plain_forces_plain_profile() -> None:
    ctx = make_console(environ={"NEXUS_PLAIN": "1"}, argv=["nexus", "plugins", "list"])
    assert ctx.profile is RenderProfile.PLAIN


def test_makeconsole_without_overrides_falls_back_to_real_environ(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEXUS_PLAIN", "1")
    monkeypatch.setattr("sys.argv", ["nexus"])
    ctx = make_console()
    assert ctx.profile is RenderProfile.PLAIN


def test_makeconsole_caps_forced_plain_reflects_pre_scan() -> None:
    ctx = make_console(environ={}, argv=["nexus", "--plain"])
    assert ctx.caps.forced_plain is True


def test_makeconsole_no_force_no_tty_yields_plain_profile() -> None:
    ctx = make_console(forced_plain=False, environ={}, argv=["nexus"])
    assert ctx.profile is RenderProfile.PLAIN  # No TTY in pytest -> PLAIN.
