# tests/test_ui_capabilities.py
# Unit tests for nexus.ui.capabilities: TerminalCapabilities + pick_profile.
# Author: Pierre Grothe
# Date: 2026-05-15

"""Cover detect(), pick_profile(), and the helper detectors."""

from io import StringIO

import pytest
from rich.console import Console

from nexus.ui.capabilities import (
    CI_ENV_VARS,
    ColorDepth,
    RenderProfile,
    TerminalCapabilities,
    detect,
    pick_profile,
)


def _make_caps(**overrides: object) -> TerminalCapabilities:
    base: dict[str, object] = {
        "is_tty": True,
        "is_ci": False,
        "color_depth": ColorDepth.TRUECOLOR,
        "cols": 120,
        "rows": 40,
        "legacy_windows": False,
        "term_program": "WindowsTerminal",
        "is_dumb_terminal": False,
        "is_multiplexer": False,
        "no_color_env": False,
        "forced_plain": False,
        "supports_hyperlinks": True,
    }
    base.update(overrides)
    return TerminalCapabilities.model_validate(base)


def test_terminalcapabilities_rejects_non_positive_cols() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        _make_caps(cols=0)


def test_terminalcapabilities_rejects_non_positive_rows() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        _make_caps(rows=-1)


def test_terminalcapabilities_is_frozen() -> None:
    caps = _make_caps()
    with pytest.raises(ValueError, match="frozen"):
        caps.is_tty = False


def test_pickprofile_returns_plain_for_non_tty() -> None:
    assert pick_profile(_make_caps(is_tty=False)) is RenderProfile.PLAIN


def test_pickprofile_returns_plain_for_forced_plain() -> None:
    assert pick_profile(_make_caps(forced_plain=True)) is RenderProfile.PLAIN


def test_pickprofile_returns_plain_for_dumb_terminal() -> None:
    assert pick_profile(_make_caps(is_dumb_terminal=True)) is RenderProfile.PLAIN


def test_pickprofile_returns_plain_for_ci() -> None:
    assert pick_profile(_make_caps(is_ci=True)) is RenderProfile.PLAIN


def test_pickprofile_returns_legacy_for_legacy_windows() -> None:
    assert pick_profile(_make_caps(legacy_windows=True)) is RenderProfile.LEGACY


def test_pickprofile_returns_legacy_for_no_color_depth() -> None:
    assert pick_profile(_make_caps(color_depth=ColorDepth.NONE)) is RenderProfile.LEGACY


def test_pickprofile_returns_rich_for_modern_terminal() -> None:
    assert pick_profile(_make_caps()) is RenderProfile.RICH


def test_pickprofile_returns_basic_for_ansi16() -> None:
    assert pick_profile(_make_caps(color_depth=ColorDepth.ANSI16)) is RenderProfile.BASIC


def test_pickprofile_returns_basic_for_short_terminal() -> None:
    assert pick_profile(_make_caps(rows=20)) is RenderProfile.BASIC


def test_pickprofile_returns_basic_for_no_color_env() -> None:
    assert pick_profile(_make_caps(no_color_env=True)) is RenderProfile.BASIC


def test_pickprofile_returns_basic_for_multiplexer() -> None:
    assert pick_profile(_make_caps(is_multiplexer=True)) is RenderProfile.BASIC


def test_detect_uses_truecolor_console_system() -> None:
    console = Console(file=StringIO(), force_terminal=True, color_system="truecolor")
    caps = detect(console, forced_plain=False, environ={})
    assert caps.color_depth is ColorDepth.TRUECOLOR


def test_detect_maps_256_to_ansi256() -> None:
    console = Console(file=StringIO(), force_terminal=True, color_system="256")
    caps = detect(console, forced_plain=False, environ={})
    assert caps.color_depth is ColorDepth.ANSI256


def test_detect_maps_standard_to_ansi16() -> None:
    console = Console(file=StringIO(), force_terminal=True, color_system="standard")
    caps = detect(console, forced_plain=False, environ={})
    assert caps.color_depth is ColorDepth.ANSI16


def test_detect_maps_no_color_system_to_none() -> None:
    console = Console(file=StringIO(), force_terminal=False, color_system=None)
    caps = detect(console, forced_plain=False, environ={})
    assert caps.color_depth is ColorDepth.NONE


def test_detect_reports_ci_when_github_actions_set() -> None:
    console = Console(file=StringIO())
    caps = detect(console, forced_plain=False, environ={"GITHUB_ACTIONS": "true"})
    assert caps.is_ci is True


def test_detect_reports_no_ci_in_empty_environment() -> None:
    console = Console(file=StringIO())
    caps = detect(console, forced_plain=False, environ={})
    assert caps.is_ci is False


def test_detect_recognises_all_documented_ci_vars() -> None:
    console = Console(file=StringIO())
    for var in CI_ENV_VARS:
        caps = detect(console, forced_plain=False, environ={var: "1"})
        assert caps.is_ci is True, f"{var} should mark CI"


def test_detect_suppresses_legacy_windows_when_wt_session_set() -> None:
    console = Console(file=StringIO(), legacy_windows=True)
    caps = detect(console, forced_plain=False, environ={"WT_SESSION": "abc"})
    assert caps.legacy_windows is False


def test_detect_suppresses_legacy_windows_when_iterm_session_set() -> None:
    console = Console(file=StringIO(), legacy_windows=True)
    caps = detect(console, forced_plain=False, environ={"ITERM_SESSION_ID": "w0"})
    assert caps.legacy_windows is False


def test_detect_reports_no_color_env() -> None:
    console = Console(file=StringIO())
    caps = detect(console, forced_plain=False, environ={"NO_COLOR": ""})
    assert caps.no_color_env is True


def test_detect_reports_dumb_terminal() -> None:
    console = Console(file=StringIO())
    caps = detect(console, forced_plain=False, environ={"TERM": "dumb"})
    assert caps.is_dumb_terminal is True


def test_detect_reports_multiplexer_for_tmux() -> None:
    console = Console(file=StringIO())
    caps = detect(console, forced_plain=False, environ={"TERM": "tmux-256color"})
    assert caps.is_multiplexer is True


def test_detect_reports_multiplexer_for_screen() -> None:
    console = Console(file=StringIO())
    caps = detect(console, forced_plain=False, environ={"TERM": "screen-256color"})
    assert caps.is_multiplexer is True


def test_detect_suppresses_multiplexer_when_colorterm_truecolor() -> None:
    console = Console(file=StringIO())
    caps = detect(
        console,
        forced_plain=False,
        environ={"TERM": "tmux-256color", "COLORTERM": "truecolor"},
    )
    assert caps.is_multiplexer is False


def test_detect_captures_term_program() -> None:
    console = Console(file=StringIO())
    caps = detect(console, forced_plain=False, environ={"TERM_PROGRAM": "iTerm.app"})
    assert caps.term_program == "iTerm.app"


def test_detect_term_program_defaults_to_empty_string() -> None:
    console = Console(file=StringIO())
    caps = detect(console, forced_plain=False, environ={})
    assert caps.term_program == ""


def test_detect_falls_back_to_os_environ_when_environ_arg_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TERM_PROGRAM", "vscode")
    console = Console(file=StringIO())
    caps = detect(console, forced_plain=False)
    assert caps.term_program == "vscode"


def test_detect_supports_hyperlinks_requires_ansi256_or_better() -> None:
    console = Console(
        file=StringIO(), force_terminal=True, color_system="standard", legacy_windows=False
    )
    caps = detect(console, forced_plain=False, environ={})
    assert caps.supports_hyperlinks is False


def test_detect_supports_hyperlinks_true_for_truecolor() -> None:
    console = Console(
        file=StringIO(), force_terminal=True, color_system="truecolor", legacy_windows=False
    )
    caps = detect(console, forced_plain=False, environ={})
    assert caps.supports_hyperlinks is True


def test_detect_falls_back_to_80x24_when_terminal_size_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(**_kwargs: object) -> object:
        raise OSError("no tty")

    monkeypatch.setattr("nexus.ui.capabilities.get_terminal_size", _raise)
    console = Console(file=StringIO())
    caps = detect(console, forced_plain=False, environ={})
    assert caps.cols == 80
    assert caps.rows == 24
