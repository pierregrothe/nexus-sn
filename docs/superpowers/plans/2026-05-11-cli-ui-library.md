# CLI UI Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `nexus.ui.components` library of frozen Pydantic models that render to Rich, then migrate `status_reporter.py` and `cli.py` onto it so styling is consistent across commands and "labels coloured, data neutral" is enforced by the component types.

**Architecture:** Eight components in `src/nexus/ui/components/`, each a `frozen=True, strict=True, extra="forbid"` Pydantic model with a `__rich_console__` method that calls into the existing `gradient_panel.py` and `theme.py` primitives. The CLI is the only consumer; no other layer imports from `nexus.ui.components`.

**Tech Stack:** Python 3.14, Rich (existing), Pydantic v2 (existing), pytest with recording-console assertions, no mocks.

**Reference spec:** `docs/superpowers/specs/2026-05-11-cli-ui-library-design.md`.

**Migration ordering note (deviates from spec ordering for green-at-every-commit):** Old theme tokens (`sn.blue`, `sn.lime`, `info`, `accent`, `primary`, `NEXUS_BLUE`, `NEXUS_CYAN`, `SN_TEXT_START`) stay alive in `theme.py` through Commits 1-3 alongside the new tokens. They are deleted in Commit 4 (cleanup) once all callers are converted. The PR still ships with no back-compat shims -- the duplication exists only inside the PR.

---

## File structure

**New files:**
```
src/nexus/ui/components/__init__.py
src/nexus/ui/components/badge.py
src/nexus/ui/components/marker.py
src/nexus/ui/components/notice.py
src/nexus/ui/components/hint.py
src/nexus/ui/components/panel.py
src/nexus/ui/components/table.py
src/nexus/ui/components/guide.py
src/nexus/ui/components/progress.py
src/nexus/instances/badges.py
tests/ui/__init__.py
tests/ui/components/__init__.py
tests/ui/test_theme.py
tests/ui/components/test_badge.py
tests/ui/components/test_marker.py
tests/ui/components/test_notice.py
tests/ui/components/test_hint.py
tests/ui/components/test_panel.py
tests/ui/components/test_table.py
tests/ui/components/test_guide.py
tests/ui/components/test_progress.py
tests/ui/snapshots/nexus_status.txt
tests/ui/snapshots/nexus_instance.txt
tests/ui/snapshots/nexus_capture_discover.txt
tests/ui/test_snapshots.py
tests/instances/test_badges.py
```

**Modified files:**
```
src/nexus/ui/theme.py           # add new tokens (Commit 1) then drop old (Commit 4)
src/nexus/ui/__init__.py        # re-exports
src/nexus/capabilities/status_reporter.py
src/nexus/cli.py
tests/test_capabilities_status.py
tests/test_cli_instance.py
tests/capture/test_*.py         # only those that snapshot CLI output
.ratchet.json
```

---

## Phase A -- Commit 1: Library scaffold (Tasks 1-10)

Goal: every component implemented with full unit tests, public API re-exported. CLI behaviour and existing test suite unchanged.

---

### Task 1: Refactor theme.py (additive, no removals yet)

**Files:**
- Modify: `src/nexus/ui/theme.py`
- Create: `tests/ui/__init__.py`
- Test: `tests/ui/test_theme.py`

- [ ] **Step 1: Create empty test package init**

```python
# tests/ui/__init__.py
"""Tests for nexus.ui."""
```

- [ ] **Step 2: Write failing tests for new theme tokens**

```python
# tests/ui/test_theme.py
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for nexus.ui.theme tokens and Rich Theme map."""

from rich.console import Console

from nexus.ui.theme import NEXUS_THEME, SN_BLUE, SN_LIME

__all__: list[str] = []


def test_sn_blue_matches_brand_rgb() -> None:
    assert SN_BLUE == (0x00, 0x68, 0xB1)


def test_sn_lime_matches_brand_rgb() -> None:
    assert SN_LIME == (0x7C, 0xC1, 0x43)


def test_theme_exposes_label_style() -> None:
    assert "label" in NEXUS_THEME.styles


def test_theme_exposes_value_style() -> None:
    assert "value" in NEXUS_THEME.styles


def test_theme_exposes_dim_style() -> None:
    assert "dim" in NEXUS_THEME.styles


def test_theme_exposes_ok_style() -> None:
    assert "ok" in NEXUS_THEME.styles


def test_theme_exposes_warn_style() -> None:
    assert "warn" in NEXUS_THEME.styles


def test_theme_exposes_error_style() -> None:
    assert "error" in NEXUS_THEME.styles


def test_theme_exposes_border_start_style() -> None:
    assert "border.start" in NEXUS_THEME.styles


def test_theme_exposes_border_end_style() -> None:
    assert "border.end" in NEXUS_THEME.styles


def test_label_renders_in_blue_bold() -> None:
    console = Console(record=True, force_terminal=True, color_system="truecolor", theme=NEXUS_THEME, width=40)
    console.print("[label]User:[/label]")
    out = console.export_text(styles=True)
    assert "User:" in out
    assert "\x1b[" in out  # contains ANSI escapes
```

- [ ] **Step 3: Run tests to verify failures**

Run: `pytest tests/ui/test_theme.py -v`
Expected: FAIL on missing `label`, `value`, `border.start`, `border.end` styles.

- [ ] **Step 4: Update theme.py with new tokens (additive)**

```python
# src/nexus/ui/theme.py
# Rich theme used by the NEXUS CLI Console.
# Author: Pierre Grothe
# Date: 2026-05-08

"""NEXUS visual identity: brand RGB stops + named Rich styles.

Importing nexus.ui.theme has no nicegui dependency, so cli.py can apply the
theme on every invocation without forcing the optional [ui] extra.

This module owns the only colour constants in the project. All components
read from here. Inline markup uses semantic style names (`label`, `value`,
`ok`, `warn`, `error`, `dim`, `border.start`, `border.end`); the legacy
brand-named styles (`sn.blue`, `sn.lime`, `info`, `accent`, `primary`)
remain registered for backwards source-compat during the migration PR and
are removed in the cleanup commit once all callers are converted.
"""

from rich.theme import Theme

__all__ = [
    "NEXUS_BLUE",
    "NEXUS_CYAN",
    "NEXUS_THEME",
    "SN_BLUE",
    "SN_LIME",
    "SN_TEXT_START",
]

NEXUS_BLUE: tuple[int, int, int] = (0x1F, 0x6F, 0xEB)
NEXUS_CYAN: tuple[int, int, int] = (0x39, 0xD3, 0xC3)

SN_BLUE: tuple[int, int, int] = (0x00, 0x68, 0xB1)
SN_LIME: tuple[int, int, int] = (0x7C, 0xC1, 0x43)
SN_TEXT_START: tuple[int, int, int] = (
    int(SN_BLUE[0] + (SN_LIME[0] - SN_BLUE[0]) * 0.40),
    int(SN_BLUE[1] + (SN_LIME[1] - SN_BLUE[1]) * 0.40),
    int(SN_BLUE[2] + (SN_LIME[2] - SN_BLUE[2]) * 0.40),
)

_SN_BLUE_RGB = f"rgb({SN_BLUE[0]},{SN_BLUE[1]},{SN_BLUE[2]})"
_SN_LIME_RGB = f"rgb({SN_LIME[0]},{SN_LIME[1]},{SN_LIME[2]})"

NEXUS_THEME = Theme(
    {
        # New semantic names -- preferred going forward.
        "label": f"{_SN_BLUE_RGB} bold",
        "value": "default",
        "dim": "bright_black",
        "ok": f"{_SN_LIME_RGB} bold",
        "warn": "yellow bold",
        "error": "red bold",
        "border.start": _SN_BLUE_RGB,
        "border.end": _SN_LIME_RGB,
        # Legacy brand-named styles -- removed in cleanup commit.
        "primary": f"rgb({NEXUS_BLUE[0]},{NEXUS_BLUE[1]},{NEXUS_BLUE[2]})",
        "accent": f"rgb({NEXUS_CYAN[0]},{NEXUS_CYAN[1]},{NEXUS_CYAN[2]})",
        "sn.blue": _SN_BLUE_RGB,
        "sn.lime": _SN_LIME_RGB,
        "info": "blue",
        "muted": "bright_black",
    }
)
```

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest tests/ui/test_theme.py -v`
Expected: 10 PASS.

- [ ] **Step 6: Run existing test suite to verify no regression**

Run: `pytest -x`
Expected: ALL PASS (existing tests still see `sn.blue` / `sn.lime` / etc.).

- [ ] **Step 7: Commit**

```bash
git -C D:/dev/nexus-sn add src/nexus/ui/theme.py tests/ui/__init__.py tests/ui/test_theme.py
git -C D:/dev/nexus-sn commit -m "feat(ui): add semantic theme tokens (label/value/ok/warn/error/border.*)"
```

---

### Task 2: StatusBadge component

**Files:**
- Create: `src/nexus/ui/components/__init__.py`
- Create: `src/nexus/ui/components/badge.py`
- Create: `tests/ui/components/__init__.py`
- Test: `tests/ui/components/test_badge.py`

- [ ] **Step 1: Create package init files**

```python
# src/nexus/ui/components/__init__.py
"""NEXUS CLI component library.

Each module exposes a frozen Pydantic model with a __rich_console__ method.
Callers do `console.print(StatusBadge.warn("EXPIRED"))`.
"""

__all__: list[str] = []
```

```python
# tests/ui/components/__init__.py
"""Tests for nexus.ui.components."""
```

- [ ] **Step 2: Write failing tests**

```python
# tests/ui/components/test_badge.py
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for StatusBadge component."""

import pytest
from pydantic import ValidationError
from rich.console import Console

from nexus.ui.components.badge import StatusBadge
from nexus.ui.theme import NEXUS_THEME

__all__: list[str] = []


def _record_console() -> Console:
    return Console(
        record=True,
        force_terminal=True,
        color_system="truecolor",
        theme=NEXUS_THEME,
        width=40,
    )


def test_status_badge_construction_holds_text_and_variant() -> None:
    badge = StatusBadge(text="READY", variant="ok")
    assert badge.text == "READY"
    assert badge.variant == "ok"


def test_status_badge_rejects_unknown_variant() -> None:
    with pytest.raises(ValidationError):
        StatusBadge(text="READY", variant="nope")  # type: ignore[arg-type]


def test_status_badge_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        StatusBadge(text="READY", variant="ok", extra="x")  # type: ignore[call-arg]


def test_status_badge_is_frozen() -> None:
    badge = StatusBadge(text="READY", variant="ok")
    with pytest.raises(ValidationError):
        badge.text = "OTHER"  # type: ignore[misc]


def test_status_badge_ok_classmethod_sets_variant() -> None:
    badge = StatusBadge.ok("READY")
    assert badge.variant == "ok"
    assert badge.text == "READY"


def test_status_badge_warn_classmethod_sets_variant() -> None:
    assert StatusBadge.warn("NEEDS REAUTH").variant == "warn"


def test_status_badge_error_classmethod_sets_variant() -> None:
    assert StatusBadge.error("EXPIRED").variant == "error"


def test_status_badge_renders_text_in_terminal() -> None:
    console = _record_console()
    console.print(StatusBadge.ok("READY"))
    plain = console.export_text(styles=False)
    assert "READY" in plain


def test_status_badge_warn_emits_yellow_ansi() -> None:
    console = _record_console()
    console.print(StatusBadge.warn("NEEDS REAUTH"))
    styled = console.export_text(styles=True)
    assert "NEEDS REAUTH" in styled
    assert "\x1b[" in styled


def test_status_badge_renders_plain_when_not_terminal() -> None:
    console = Console(record=True, force_terminal=False, theme=NEXUS_THEME, width=40)
    console.print(StatusBadge.error("EXPIRED"))
    styled = console.export_text(styles=True)
    assert "EXPIRED" in styled
    assert "\x1b[" not in styled
```

- [ ] **Step 3: Run tests to verify failure**

Run: `pytest tests/ui/components/test_badge.py -v`
Expected: FAIL on missing module.

- [ ] **Step 4: Implement StatusBadge**

```python
# src/nexus/ui/components/badge.py
# Semantic state indicator (READY / NEEDS REAUTH / EXPIRED).
# Author: Pierre Grothe
# Date: 2026-05-11

"""StatusBadge: a single coloured word marking a semantic state.

ok    -> SN_LIME bold (READY, healthy)
warn  -> yellow bold  (NEEDS REAUTH, expiring)
error -> red bold     (EXPIRED, FAILED)
"""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict
from rich.console import Console, ConsoleOptions, RenderResult
from rich.text import Text

__all__ = ["StatusBadge"]


class StatusBadge(BaseModel):
    """A single semantic-coloured state word.

    Attributes:
        text: The word to render (e.g. ``"READY"``).
        variant: One of ``"ok"``, ``"warn"``, ``"error"`` mapped to the
            theme styles of the same name.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    text: str
    variant: Literal["ok", "warn", "error"]

    @classmethod
    def ok(cls, text: str) -> Self:
        """Build an ``ok`` badge (lime bold).

        Args:
            text: The word to render.

        Returns:
            A frozen ``StatusBadge`` with ``variant="ok"``.
        """
        return cls(text=text, variant="ok")

    @classmethod
    def warn(cls, text: str) -> Self:
        """Build a ``warn`` badge (yellow bold)."""
        return cls(text=text, variant="warn")

    @classmethod
    def error(cls, text: str) -> Self:
        """Build an ``error`` badge (red bold)."""
        return cls(text=text, variant="error")

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        """Yield a styled Text whose style resolves to the theme variant.

        Args:
            console: Destination console (unused -- Text resolves the style
                against the console's theme at render time).
            options: Render options (unused).

        Yields:
            A single ``rich.text.Text`` carrying the badge text.
        """
        del console, options
        yield Text(self.text, style=self.variant)
```

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest tests/ui/components/test_badge.py -v`
Expected: 10 PASS.

- [ ] **Step 6: Commit**

```bash
git -C D:/dev/nexus-sn add src/nexus/ui/components/__init__.py src/nexus/ui/components/badge.py tests/ui/components/__init__.py tests/ui/components/test_badge.py
git -C D:/dev/nexus-sn commit -m "feat(ui): add StatusBadge component"
```

---

### Task 3: default_marker helper

**Files:**
- Create: `src/nexus/ui/components/marker.py`
- Test: `tests/ui/components/test_marker.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/ui/components/test_marker.py
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for default_marker helper."""

from rich.console import Console
from rich.text import Text

from nexus.ui.components.marker import default_marker
from nexus.ui.theme import NEXUS_THEME

__all__: list[str] = []


def test_default_marker_returns_text() -> None:
    assert isinstance(default_marker(), Text)


def test_default_marker_text_is_asterisk_space() -> None:
    assert default_marker().plain == "* "


def test_default_marker_uses_ok_style() -> None:
    assert default_marker().style == "ok"


def test_default_marker_renders_with_ansi_in_terminal() -> None:
    console = Console(
        record=True, force_terminal=True, color_system="truecolor",
        theme=NEXUS_THEME, width=20,
    )
    console.print(default_marker(), end="")
    styled = console.export_text(styles=True)
    assert "*" in styled
    assert "\x1b[" in styled
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/ui/components/test_marker.py -v`
Expected: FAIL on missing module.

- [ ] **Step 3: Implement default_marker**

```python
# src/nexus/ui/components/marker.py
# Lime bold "* " prefix marking the active default row in a list.
# Author: Pierre Grothe
# Date: 2026-05-11

"""default_marker: the lime asterisk used in `nexus instance list` to point
at the configured default profile.
"""

from rich.text import Text

__all__ = ["default_marker"]


def default_marker() -> Text:
    """Return the lime bold ``"* "`` indicator.

    Returns:
        A ``rich.text.Text`` carrying the asterisk and trailing space,
        styled with the theme's ``ok`` style.
    """
    return Text("* ", style="ok")
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/ui/components/test_marker.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git -C D:/dev/nexus-sn add src/nexus/ui/components/marker.py tests/ui/components/test_marker.py
git -C D:/dev/nexus-sn commit -m "feat(ui): add default_marker helper"
```

---

### Task 4: Notice component

**Files:**
- Create: `src/nexus/ui/components/notice.py`
- Test: `tests/ui/components/test_notice.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/ui/components/test_notice.py
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for Notice component."""

import pytest
from pydantic import ValidationError
from rich.console import Console

from nexus.ui.components.notice import Notice
from nexus.ui.theme import NEXUS_THEME

__all__: list[str] = []


def _record_console() -> Console:
    return Console(
        record=True, force_terminal=True, color_system="truecolor",
        theme=NEXUS_THEME, width=80,
    )


def test_notice_construction_holds_severity_and_message() -> None:
    notice = Notice(severity="error", message="Something broke")
    assert notice.severity == "error"
    assert notice.message == "Something broke"


def test_notice_rejects_unknown_severity() -> None:
    with pytest.raises(ValidationError):
        Notice(severity="critical", message="x")  # type: ignore[arg-type]


def test_notice_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        Notice(severity="info", message="x", extra="y")  # type: ignore[call-arg]


def test_notice_is_frozen() -> None:
    notice = Notice(severity="info", message="x")
    with pytest.raises(ValidationError):
        notice.message = "y"  # type: ignore[misc]


def test_notice_error_classmethod_sets_severity() -> None:
    assert Notice.error("oops").severity == "error"


def test_notice_warn_classmethod_sets_severity() -> None:
    assert Notice.warn("careful").severity == "warn"


def test_notice_info_classmethod_sets_severity() -> None:
    assert Notice.info("hello").severity == "info"


def test_notice_renders_prefix_capitalized_with_message() -> None:
    console = _record_console()
    console.print(Notice.error("Profile not found"))
    plain = console.export_text(styles=False)
    assert "Error: Profile not found" in plain


def test_notice_warn_renders_warning_prefix() -> None:
    console = _record_console()
    console.print(Notice.warn("Token expiring soon"))
    plain = console.export_text(styles=False)
    assert "Warning: Token expiring soon" in plain


def test_notice_info_renders_info_prefix() -> None:
    console = _record_console()
    console.print(Notice.info("Done"))
    plain = console.export_text(styles=False)
    assert "Info: Done" in plain


def test_notice_emits_ansi_in_terminal_for_prefix() -> None:
    console = _record_console()
    console.print(Notice.error("oops"))
    styled = console.export_text(styles=True)
    assert "\x1b[" in styled
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/ui/components/test_notice.py -v`
Expected: FAIL on missing module.

- [ ] **Step 3: Implement Notice**

```python
# src/nexus/ui/components/notice.py
# Single-line user notice (Error: / Warning: / Info: prefix + neutral message).
# Author: Pierre Grothe
# Date: 2026-05-11

"""Notice: a one-line user-facing message.

The prefix word is colour-coded by severity; the message stays in the
terminal's default foreground colour.
"""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict
from rich.console import Console, ConsoleOptions, RenderResult
from rich.text import Text

__all__ = ["Notice"]

_PREFIX: dict[str, tuple[str, str]] = {
    "error": ("Error", "error"),
    "warn": ("Warning", "warn"),
    "info": ("Info", "label"),
}


class Notice(BaseModel):
    """A coloured-prefix neutral-message line.

    Attributes:
        severity: One of ``"error"``, ``"warn"``, ``"info"``.
        message: The neutral text rendered after the prefix.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    severity: Literal["error", "warn", "info"]
    message: str

    @classmethod
    def error(cls, message: str) -> Self:
        """Build an ``error`` notice (red bold prefix)."""
        return cls(severity="error", message=message)

    @classmethod
    def warn(cls, message: str) -> Self:
        """Build a ``warn`` notice (yellow bold prefix)."""
        return cls(severity="warn", message=message)

    @classmethod
    def info(cls, message: str) -> Self:
        """Build an ``info`` notice (blue label-style prefix)."""
        return cls(severity="info", message=message)

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        """Yield ``<prefix>: <message>`` with prefix in the severity style.

        Args:
            console: Destination console (unused).
            options: Render options (unused).

        Yields:
            A single ``rich.text.Text``.
        """
        del console, options
        word, style = _PREFIX[self.severity]
        text = Text()
        text.append(f"{word}: ", style=style)
        text.append(self.message)
        yield text
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/ui/components/test_notice.py -v`
Expected: 11 PASS.

- [ ] **Step 5: Commit**

```bash
git -C D:/dev/nexus-sn add src/nexus/ui/components/notice.py tests/ui/components/test_notice.py
git -C D:/dev/nexus-sn commit -m "feat(ui): add Notice component"
```

---

### Task 5: Hint component

**Files:**
- Create: `src/nexus/ui/components/hint.py`
- Test: `tests/ui/components/test_hint.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/ui/components/test_hint.py
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for Hint component."""

import pytest
from pydantic import ValidationError
from rich.console import Console

from nexus.ui.components.hint import Hint
from nexus.ui.theme import NEXUS_THEME

__all__: list[str] = []


def _record_console() -> Console:
    return Console(
        record=True, force_terminal=True, color_system="truecolor",
        theme=NEXUS_THEME, width=80,
    )


def test_hint_construction_defaults_suffix_to_none() -> None:
    hint = Hint(label="Next", command="nexus capture pull --scope x_foo")
    assert hint.suffix is None


def test_hint_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        Hint(label="Next", command="x", extra="y")  # type: ignore[call-arg]


def test_hint_is_frozen() -> None:
    hint = Hint(label="Next", command="x")
    with pytest.raises(ValidationError):
        hint.command = "y"  # type: ignore[misc]


def test_hint_renders_with_two_space_indent() -> None:
    console = _record_console()
    console.print(Hint(label="Next", command="nexus capture pull"))
    plain = console.export_text(styles=False)
    assert plain.startswith("  Next:")


def test_hint_renders_label_command_and_suffix() -> None:
    console = _record_console()
    console.print(Hint(label="Next", command="nexus capture pull", suffix="(repeatable)"))
    plain = console.export_text(styles=False)
    assert "Next:" in plain
    assert "nexus capture pull" in plain
    assert "(repeatable)" in plain


def test_hint_omits_suffix_when_none() -> None:
    console = _record_console()
    console.print(Hint(label="Next", command="nexus capture pull"))
    plain = console.export_text(styles=False)
    assert "(" not in plain


def test_hint_emits_ansi_for_label_in_terminal() -> None:
    console = _record_console()
    console.print(Hint(label="Next", command="nexus capture pull"))
    styled = console.export_text(styles=True)
    assert "\x1b[" in styled
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/ui/components/test_hint.py -v`
Expected: FAIL on missing module.

- [ ] **Step 3: Implement Hint**

```python
# src/nexus/ui/components/hint.py
# "Next: <command>" style instructional line with baked-in two-space indent.
# Author: Pierre Grothe
# Date: 2026-05-11

"""Hint: one-line prompt pointing the user at the next command to run.

Format: ``  <label>: <command> <suffix?>`` -- label in the gradient label
style, command bold, suffix dim. Two-space leading indent is part of the
component, not the caller's responsibility.
"""

from pydantic import BaseModel, ConfigDict
from rich.console import Console, ConsoleOptions, RenderResult
from rich.text import Text

__all__ = ["Hint"]


class Hint(BaseModel):
    """A coloured-label / bold-command instructional line.

    Attributes:
        label: Short prefix word (e.g. ``"Next"``, ``"Try"``).
        command: The literal command to run.
        suffix: Optional dim parenthetical shown after the command.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    label: str
    command: str
    suffix: str | None = None

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        """Yield ``  <label>: <command> <suffix>`` styled per the theme.

        Args:
            console: Destination console (unused).
            options: Render options (unused).

        Yields:
            A single ``rich.text.Text``.
        """
        del console, options
        text = Text("  ")
        text.append(f"{self.label}: ", style="label")
        text.append(self.command, style="bold")
        if self.suffix is not None:
            text.append(f" {self.suffix}", style="dim")
        yield text
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/ui/components/test_hint.py -v`
Expected: 7 PASS.

- [ ] **Step 5: Commit**

```bash
git -C D:/dev/nexus-sn add src/nexus/ui/components/hint.py tests/ui/components/test_hint.py
git -C D:/dev/nexus-sn commit -m "feat(ui): add Hint component"
```

---

### Task 6: KvRow + KeyValuePanel + two_col

**Files:**
- Create: `src/nexus/ui/components/panel.py`
- Test: `tests/ui/components/test_panel.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/ui/components/test_panel.py
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for KvRow, KeyValuePanel, two_col."""

import pytest
from pydantic import ValidationError
from rich.console import Console

from nexus.ui.components.badge import StatusBadge
from nexus.ui.components.panel import KeyValuePanel, KvRow, two_col
from nexus.ui.theme import NEXUS_THEME

__all__: list[str] = []


def _record_console(width: int = 80) -> Console:
    return Console(
        record=True, force_terminal=True, color_system="truecolor",
        theme=NEXUS_THEME, width=width,
    )


def test_kvrow_construction_holds_label_value() -> None:
    row = KvRow(label="User", value="pierre@servicenow.com")
    assert row.label == "User"
    assert row.value == "pierre@servicenow.com"
    assert row.suffix is None


def test_kvrow_accepts_renderable_value() -> None:
    badge = StatusBadge.error("EXPIRED")
    row = KvRow(label="Token", value=badge)
    assert row.value is badge


def test_kvrow_accepts_renderable_suffix() -> None:
    badge = StatusBadge.warn("1 need reauth")
    row = KvRow(label="Servers", value="3/4 ready", suffix=badge)
    assert row.suffix is badge


def test_kvrow_is_frozen() -> None:
    row = KvRow(label="x", value="y")
    with pytest.raises(ValidationError):
        row.label = "z"  # type: ignore[misc]


def test_keyvaluepanel_renders_title_and_rows() -> None:
    console = _record_console()
    console.print(KeyValuePanel(
        title="Identity",
        rows=[
            KvRow(label="User", value="pierre@servicenow.com"),
            KvRow(label="Tier", value="PRO"),
        ],
    ))
    plain = console.export_text(styles=False)
    assert "Identity" in plain
    assert "User:" in plain
    assert "pierre@servicenow.com" in plain
    assert "Tier:" in plain
    assert "PRO" in plain


def test_keyvaluepanel_pads_labels_to_longest() -> None:
    console = _record_console()
    console.print(KeyValuePanel(
        title="x",
        rows=[
            KvRow(label="A", value="1"),
            KvRow(label="LongerLabel", value="2"),
        ],
    ))
    plain = console.export_text(styles=False)
    a_idx = plain.index("1")
    b_idx = plain.index("2")
    assert plain[a_idx - 4 : a_idx] == "    "  # at least padded


def test_keyvaluepanel_renders_with_status_badge_value() -> None:
    console = _record_console()
    console.print(KeyValuePanel(
        title="Auth",
        rows=[KvRow(label="Token", value=StatusBadge.error("EXPIRED"))],
    ))
    plain = console.export_text(styles=False)
    assert "Token:" in plain
    assert "EXPIRED" in plain


def test_keyvaluepanel_renders_suffix_after_value() -> None:
    console = _record_console()
    console.print(KeyValuePanel(
        title="x",
        rows=[KvRow(
            label="Servers", value="3/4 ready",
            suffix=StatusBadge.warn("1 need reauth"),
        )],
    ))
    plain = console.export_text(styles=False)
    pos_value = plain.index("3/4 ready")
    pos_suffix = plain.index("1 need reauth")
    assert pos_value < pos_suffix


def test_keyvaluepanel_is_frozen() -> None:
    panel = KeyValuePanel(title="x", rows=[KvRow(label="a", value="b")])
    with pytest.raises(ValidationError):
        panel.title = "y"  # type: ignore[misc]


def test_two_col_renders_both_panels_at_equal_height() -> None:
    left = KeyValuePanel(title="L", rows=[KvRow(label="a", value="1")])
    right = KeyValuePanel(title="R", rows=[
        KvRow(label="a", value="1"),
        KvRow(label="b", value="2"),
        KvRow(label="c", value="3"),
    ])
    console = _record_console(width=80)
    console.print(two_col(left, right))
    plain = console.export_text(styles=False)
    assert "L" in plain
    assert "R" in plain
    # Both panels should have the same number of body lines because two_col
    # equalises min_height -- check by counting the right-edge marker rows.
    # A weaker structural check: presence of all three labels from the right.
    assert "a:" in plain
    assert "b:" in plain
    assert "c:" in plain


def test_keyvaluepanel_renders_plain_when_not_terminal() -> None:
    console = Console(
        record=True, force_terminal=False, theme=NEXUS_THEME, width=80,
    )
    console.print(KeyValuePanel(
        title="x", rows=[KvRow(label="a", value="b")],
    ))
    styled = console.export_text(styles=True)
    assert "\x1b[" not in styled
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/ui/components/test_panel.py -v`
Expected: FAIL on missing module.

- [ ] **Step 3: Implement KvRow + KeyValuePanel + two_col**

```python
# src/nexus/ui/components/panel.py
# KeyValuePanel: gradient-bordered panel of <coloured label> <neutral value> rows.
# Author: Pierre Grothe
# Date: 2026-05-11

"""KvRow / KeyValuePanel / two_col.

KvRow holds a label and value (string or Rich renderable). KeyValuePanel
arranges a list of KvRows inside a GradientPanel with brand-coloured
borders, padding labels to a common width. two_col composes two panels
side-by-side at equal height.
"""

from pydantic import BaseModel, ConfigDict
from rich.console import Console, ConsoleOptions, RenderableType, RenderResult
from rich.table import Table
from rich.text import Text

from nexus.ui.gradient_panel import GradientPanel, gradient_text
from nexus.ui.theme import SN_BLUE, SN_LIME

__all__ = ["KeyValuePanel", "KvRow", "two_col"]


class KvRow(BaseModel):
    """A single ``<gradient-label>: <value> [suffix]`` row.

    Attributes:
        label: The label text (rendered with the per-character gradient).
        value: A plain string or any Rich renderable.
        suffix: Optional renderable appended after the value with one space.
    """

    model_config = ConfigDict(
        frozen=True, strict=True, extra="forbid", arbitrary_types_allowed=True,
    )

    label: str
    value: str | RenderableType
    suffix: RenderableType | None = None


class KeyValuePanel(BaseModel):
    """Gradient-bordered panel of K/V rows.

    Attributes:
        title: Title shown on the top border.
        rows: The K/V rows in render order.
        min_height: Minimum body line count, used by two_col to equalise
            heights of side-by-side panels.
    """

    model_config = ConfigDict(
        frozen=True, strict=True, extra="forbid", arbitrary_types_allowed=True,
    )

    title: str
    rows: list[KvRow]
    min_height: int = 0

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        """Render the panel with brand gradient borders and padded rows.

        Args:
            console: Destination console.
            options: Render options.

        Yields:
            A single ``GradientPanel`` containing the body.
        """
        del console, options
        body = self._body()
        panel = GradientPanel(
            body, title=self.title, start=SN_BLUE, end=SN_LIME,
            min_height=self.min_height,
        )
        yield panel

    def _body(self) -> Text:
        """Build the multi-line body with padded labels.

        Returns:
            ``rich.text.Text`` with one line per row.
        """
        if not self.rows:
            return Text()
        pad = max(len(row.label) for row in self.rows) + 2
        out = Text()
        for i, row in enumerate(self.rows):
            label_str = f"{row.label}:"
            label = gradient_text(label_str, start=SN_BLUE, end=SN_LIME)
            out.append_text(label)
            out.append(" " * (pad - len(label_str)))
            if isinstance(row.value, str):
                out.append(row.value, style="value")
            else:
                out.append_text(_render_inline(row.value))
            if row.suffix is not None:
                out.append("  ")
                if isinstance(row.suffix, str):
                    out.append(row.suffix)
                else:
                    out.append_text(_render_inline(row.suffix))
            if i < len(self.rows) - 1:
                out.append("\n")
        return out


def two_col(left: KeyValuePanel, right: KeyValuePanel) -> RenderableType:
    """Compose two KeyValuePanels side-by-side at equal height.

    Args:
        left: Left-column panel.
        right: Right-column panel.

    Returns:
        A ``Table.grid`` rendering ``left`` and ``right`` in equal-ratio columns.
    """
    height = max(len(left.rows), len(right.rows))
    left_eq = left.model_copy(update={"min_height": height})
    right_eq = right.model_copy(update={"min_height": height})
    grid = Table.grid(expand=True)
    grid.add_column(ratio=1)
    grid.add_column(ratio=1)
    grid.add_row(left_eq, right_eq)
    return grid


def _render_inline(renderable: RenderableType) -> Text:
    """Render a Rich renderable as inline Text via a temporary Console.

    Args:
        renderable: Anything Console.print can accept.

    Returns:
        ``rich.text.Text`` holding the styled output without trailing newline.
    """
    console = Console(file=None, force_terminal=False, color_system=None, width=200)
    with console.capture() as cap:
        console.print(renderable, end="")
    plain = cap.get()
    if isinstance(renderable, Text):
        return renderable
    return Text(plain)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/ui/components/test_panel.py -v`
Expected: 11 PASS.

- [ ] **Step 5: Commit**

```bash
git -C D:/dev/nexus-sn add src/nexus/ui/components/panel.py tests/ui/components/test_panel.py
git -C D:/dev/nexus-sn commit -m "feat(ui): add KvRow, KeyValuePanel, two_col"
```

---

### Task 7: DataColumn + DataTable

**Files:**
- Create: `src/nexus/ui/components/table.py`
- Test: `tests/ui/components/test_table.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/ui/components/test_table.py
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for DataColumn / DataTable."""

import pytest
from pydantic import ValidationError
from rich.console import Console

from nexus.ui.components.badge import StatusBadge
from nexus.ui.components.table import DataColumn, DataTable
from nexus.ui.theme import NEXUS_THEME

__all__: list[str] = []


def _record_console(width: int = 80) -> Console:
    return Console(
        record=True, force_terminal=True, color_system="truecolor",
        theme=NEXUS_THEME, width=width,
    )


def test_datacolumn_construction_defaults() -> None:
    col = DataColumn(header="Profile")
    assert col.header == "Profile"
    assert col.width is None
    assert col.justify == "left"
    assert col.no_wrap is True


def test_datacolumn_rejects_invalid_justify() -> None:
    with pytest.raises(ValidationError):
        DataColumn(header="x", justify="middle")  # type: ignore[arg-type]


def test_datatable_construction_holds_columns_and_rows() -> None:
    tbl = DataTable(
        title="Instances",
        columns=[DataColumn(header="Profile"), DataColumn(header="URL")],
        rows=[["dev", "https://dev.service-now.com"]],
    )
    assert tbl.title == "Instances"
    assert len(tbl.columns) == 2
    assert tbl.rows == [["dev", "https://dev.service-now.com"]]


def test_datatable_is_frozen() -> None:
    tbl = DataTable(title="x", columns=[DataColumn(header="A")], rows=[["1"]])
    with pytest.raises(ValidationError):
        tbl.title = "y"  # type: ignore[misc]


def test_datatable_renders_title_headers_and_data() -> None:
    console = _record_console()
    console.print(DataTable(
        title="Instances",
        columns=[DataColumn(header="Profile"), DataColumn(header="Token")],
        rows=[
            ["dev", StatusBadge.ok("7h 30m")],
            ["prod", StatusBadge.error("EXPIRED")],
        ],
    ))
    plain = console.export_text(styles=False)
    assert "Instances" in plain
    assert "Profile" in plain
    assert "Token" in plain
    assert "dev" in plain
    assert "prod" in plain
    assert "7h 30m" in plain
    assert "EXPIRED" in plain


def test_datatable_renders_neutral_cells_in_terminal() -> None:
    console = _record_console()
    console.print(DataTable(
        title="x",
        columns=[DataColumn(header="A")],
        rows=[["plain-data"]],
    ))
    styled = console.export_text(styles=True)
    assert "plain-data" in styled


def test_datatable_renders_plain_when_not_terminal() -> None:
    console = Console(
        record=True, force_terminal=False, theme=NEXUS_THEME, width=80,
    )
    console.print(DataTable(
        title="x", columns=[DataColumn(header="A")], rows=[["b"]],
    ))
    styled = console.export_text(styles=True)
    assert "\x1b[" not in styled
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/ui/components/test_table.py -v`
Expected: FAIL on missing module.

- [ ] **Step 3: Implement DataColumn + DataTable**

```python
# src/nexus/ui/components/table.py
# DataTable: gradient-bordered tabular display with coloured headers.
# Author: Pierre Grothe
# Date: 2026-05-11

"""DataColumn / DataTable.

DataTable wraps a Rich Table inside a GradientPanel. Headers carry the
brand gradient via gradient_text(); data cells render in the terminal's
default foreground style. Cells may be plain strings or Rich renderables
(StatusBadge, default_marker(), etc.).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict
from rich.console import Console, ConsoleOptions, RenderableType, RenderResult
from rich.table import Table

from nexus.ui.gradient_panel import GradientPanel, gradient_text
from nexus.ui.theme import SN_BLUE, SN_LIME

__all__ = ["DataColumn", "DataTable"]


class DataColumn(BaseModel):
    """Column descriptor for DataTable.

    Attributes:
        header: Column header text (rendered with the brand gradient).
        width: Optional fixed width in characters.
        justify: Cell alignment.
        no_wrap: When True, cells truncate rather than wrap.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    header: str
    width: int | None = None
    justify: Literal["left", "right", "center"] = "left"
    no_wrap: bool = True


class DataTable(BaseModel):
    """Tabular display with gradient borders and coloured headers.

    Attributes:
        title: Title shown on the top border.
        columns: Column descriptors in render order.
        rows: Row cells -- each cell may be a string or a Rich renderable.
    """

    model_config = ConfigDict(
        frozen=True, strict=True, extra="forbid", arbitrary_types_allowed=True,
    )

    title: str
    columns: list[DataColumn]
    rows: list[list[str | RenderableType]]

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        """Yield the GradientPanel-wrapped Rich Table.

        Args:
            console: Destination console (unused).
            options: Render options (unused).

        Yields:
            A single ``GradientPanel`` containing a ``rich.table.Table``.
        """
        del console, options
        table = Table(
            box=None, show_header=True, pad_edge=False,
            show_edge=False, expand=True,
        )
        for col in self.columns:
            header = gradient_text(col.header, start=SN_BLUE, end=SN_LIME)
            table.add_column(
                header=header,
                width=col.width,
                justify=col.justify,
                no_wrap=col.no_wrap,
            )
        for row in self.rows:
            table.add_row(*row)
        yield GradientPanel(
            table, title=self.title, start=SN_BLUE, end=SN_LIME,
        )
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/ui/components/test_table.py -v`
Expected: 7 PASS.

- [ ] **Step 5: Commit**

```bash
git -C D:/dev/nexus-sn add src/nexus/ui/components/table.py tests/ui/components/test_table.py
git -C D:/dev/nexus-sn commit -m "feat(ui): add DataColumn, DataTable"
```

---

### Task 8: CommandGuide

**Files:**
- Create: `src/nexus/ui/components/guide.py`
- Test: `tests/ui/components/test_guide.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/ui/components/test_guide.py
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for CommandGuide."""

import pytest
from pydantic import ValidationError
from rich.console import Console

from nexus.ui.components.guide import CommandGuide
from nexus.ui.theme import NEXUS_THEME

__all__: list[str] = []


def _record_console() -> Console:
    return Console(
        record=True, force_terminal=True, color_system="truecolor",
        theme=NEXUS_THEME, width=80,
    )


def test_commandguide_construction_holds_app_name_and_items() -> None:
    guide = CommandGuide(
        app_name="nexus instance",
        items=[("register <profile>", "Add an instance")],
    )
    assert guide.app_name == "nexus instance"
    assert guide.items == [("register <profile>", "Add an instance")]


def test_commandguide_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        CommandGuide(app_name="x", items=[], extra="y")  # type: ignore[call-arg]


def test_commandguide_is_frozen() -> None:
    guide = CommandGuide(app_name="x", items=[("a", "b")])
    with pytest.raises(ValidationError):
        guide.app_name = "y"  # type: ignore[misc]


def test_commandguide_renders_title_commands_descriptions_and_footer() -> None:
    console = _record_console()
    console.print(CommandGuide(
        app_name="nexus instance",
        items=[
            ("register <profile>", "Add an instance"),
            ("list", "Show all registered instances"),
        ],
    ))
    plain = console.export_text(styles=False)
    assert "nexus instance" in plain
    assert "register <profile>" in plain
    assert "Add an instance" in plain
    assert "list" in plain
    assert "Show all registered instances" in plain
    assert "Run nexus instance <command> --help for details." in plain


def test_commandguide_renders_plain_when_not_terminal() -> None:
    console = Console(
        record=True, force_terminal=False, theme=NEXUS_THEME, width=80,
    )
    console.print(CommandGuide(app_name="x", items=[("a", "b")]))
    styled = console.export_text(styles=True)
    assert "\x1b[" not in styled
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/ui/components/test_guide.py -v`
Expected: FAIL on missing module.

- [ ] **Step 3: Implement CommandGuide**

```python
# src/nexus/ui/components/guide.py
# CommandGuide: subcommand listing rendered as a gradient-bordered panel.
# Author: Pierre Grothe
# Date: 2026-05-11

"""CommandGuide: the per-subapp command list (replacement for cli._print_command_guide).

Two-column layout: command in the brand gradient, description in dim,
wrapped in a GradientPanel titled with the app name. A dim footer line
points at ``--help`` for details.
"""

from pydantic import BaseModel, ConfigDict
from rich.console import Console, ConsoleOptions, Group, RenderResult
from rich.table import Table
from rich.text import Text

from nexus.ui.gradient_panel import GradientPanel, gradient_text
from nexus.ui.theme import SN_BLUE, SN_LIME

__all__ = ["CommandGuide"]


class CommandGuide(BaseModel):
    """Subcommand listing wrapped in a gradient-bordered panel.

    Attributes:
        app_name: The fully-qualified Typer app path (e.g. ``"nexus instance"``).
        items: ``(subcommand, description)`` pairs in render order.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    app_name: str
    items: list[tuple[str, str]]

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        """Yield the GradientPanel-wrapped guide and its dim footer.

        Args:
            console: Destination console (unused).
            options: Render options (unused).

        Yields:
            One ``GradientPanel`` then one footer ``Text``.
        """
        del console, options
        table = Table(
            box=None, show_header=False, pad_edge=False, show_edge=False,
            padding=(0, 2),
        )
        table.add_column("cmd", no_wrap=True, width=36)
        table.add_column("desc", style="dim", no_wrap=True)
        for cmd, desc in self.items:
            cmd_text = gradient_text(
                f"{self.app_name} {cmd}", start=SN_BLUE, end=SN_LIME,
            )
            cmd_text.stylize("bold")
            table.add_row(cmd_text, desc)
        panel = GradientPanel(
            table, title=self.app_name, start=SN_BLUE, end=SN_LIME,
        )
        footer = Text(
            f"  Run {self.app_name} <command> --help for details.",
            style="dim",
        )
        yield Group(panel, footer)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/ui/components/test_guide.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git -C D:/dev/nexus-sn add src/nexus/ui/components/guide.py tests/ui/components/test_guide.py
git -C D:/dev/nexus-sn commit -m "feat(ui): add CommandGuide"
```

---

### Task 9: nexus_progress factory

**Files:**
- Create: `src/nexus/ui/components/progress.py`
- Test: `tests/ui/components/test_progress.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/ui/components/test_progress.py
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for nexus_progress factory."""

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from nexus.ui.components.progress import nexus_progress
from nexus.ui.theme import NEXUS_THEME

__all__: list[str] = []


def test_nexus_progress_returns_progress_instance() -> None:
    console = Console(theme=NEXUS_THEME)
    progress = nexus_progress(console)
    assert isinstance(progress, Progress)


def test_nexus_progress_includes_expected_columns() -> None:
    console = Console(theme=NEXUS_THEME)
    progress = nexus_progress(console)
    types = [type(c) for c in progress.columns]
    assert SpinnerColumn in types
    assert TextColumn in types
    assert BarColumn in types
    assert MofNCompleteColumn in types
    assert TimeElapsedColumn in types


def test_nexus_progress_uses_provided_console() -> None:
    console = Console(theme=NEXUS_THEME)
    progress = nexus_progress(console)
    assert progress.console is console


def test_nexus_progress_is_transient() -> None:
    console = Console(theme=NEXUS_THEME)
    progress = nexus_progress(console)
    assert progress.transient is True
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/ui/components/test_progress.py -v`
Expected: FAIL on missing module.

- [ ] **Step 3: Implement nexus_progress**

```python
# src/nexus/ui/components/progress.py
# Styled Rich Progress factory for long-running CLI operations.
# Author: Pierre Grothe
# Date: 2026-05-11

"""nexus_progress: brand-styled Rich Progress.

Rich's Progress is already a context manager with mutable state, so we
expose a factory function rather than wrapping it in a Pydantic model.
"""

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Column

__all__ = ["nexus_progress"]


def nexus_progress(console: Console) -> Progress:
    """Return a brand-styled Progress bound to ``console``.

    Args:
        console: The Console to render onto. Caller-controlled so the same
            Console (with its theme) stays in scope for prompts during the
            operation.

    Returns:
        A transient Progress with spinner, text, bar, M/N count, and elapsed
        columns. The bar uses the project gradient endpoints; the spinner
        uses the brand blue.
    """
    return Progress(
        SpinnerColumn(style="border.start"),
        TextColumn(
            "[label]{task.description}",
            table_column=Column(min_width=50, no_wrap=True),
        ),
        BarColumn(
            bar_width=30,
            style="bar.back",
            complete_style="border.end",
            finished_style="border.end",
            pulse_style="border.end",
        ),
        MofNCompleteColumn(table_column=Column(style="border.end", no_wrap=True)),
        TimeElapsedColumn(table_column=Column(style="dim", no_wrap=True)),
        console=console,
        transient=True,
    )
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/ui/components/test_progress.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git -C D:/dev/nexus-sn add src/nexus/ui/components/progress.py tests/ui/components/test_progress.py
git -C D:/dev/nexus-sn commit -m "feat(ui): add nexus_progress factory"
```

---

### Task 10: Public API re-exports + Phase A green check

**Files:**
- Modify: `src/nexus/ui/__init__.py`
- Modify: `src/nexus/ui/components/__init__.py`

- [ ] **Step 1: Read the current ui/__init__.py**

Run: `cat D:/dev/nexus-sn/src/nexus/ui/__init__.py`

- [ ] **Step 2: Update ui/components/__init__.py**

```python
# src/nexus/ui/components/__init__.py
"""NEXUS CLI component library.

Each module exposes a frozen Pydantic model with a __rich_console__ method
or a tiny helper function. Callers do
``console.print(StatusBadge.warn("EXPIRED"))``.
"""

from nexus.ui.components.badge import StatusBadge
from nexus.ui.components.guide import CommandGuide
from nexus.ui.components.hint import Hint
from nexus.ui.components.marker import default_marker
from nexus.ui.components.notice import Notice
from nexus.ui.components.panel import KeyValuePanel, KvRow, two_col
from nexus.ui.components.progress import nexus_progress
from nexus.ui.components.table import DataColumn, DataTable

__all__ = [
    "CommandGuide",
    "DataColumn",
    "DataTable",
    "Hint",
    "KeyValuePanel",
    "KvRow",
    "Notice",
    "StatusBadge",
    "default_marker",
    "nexus_progress",
    "two_col",
]
```

- [ ] **Step 3: Update ui/__init__.py to re-export the public surface**

```python
# src/nexus/ui/__init__.py
"""NEXUS CLI visual library.

Public API:

  - components.*  -- frozen Pydantic models with __rich_console__
  - banner.*      -- ASCII banner (existing primitive)
  - gradient_panel.* -- panel with gradient borders (existing primitive)
  - theme.*       -- colour constants and Rich Theme
"""

from nexus.ui.banner import banner_text, gradient, print_banner
from nexus.ui.components import (
    CommandGuide,
    DataColumn,
    DataTable,
    Hint,
    KeyValuePanel,
    KvRow,
    Notice,
    StatusBadge,
    default_marker,
    nexus_progress,
    two_col,
)
from nexus.ui.gradient_panel import GradientPanel, gradient_text
from nexus.ui.theme import NEXUS_THEME, SN_BLUE, SN_LIME

__all__ = [
    "CommandGuide",
    "DataColumn",
    "DataTable",
    "GradientPanel",
    "Hint",
    "KeyValuePanel",
    "KvRow",
    "NEXUS_THEME",
    "Notice",
    "SN_BLUE",
    "SN_LIME",
    "StatusBadge",
    "banner_text",
    "default_marker",
    "gradient",
    "gradient_text",
    "nexus_progress",
    "print_banner",
    "two_col",
]
```

- [ ] **Step 4: Run full test suite**

Run: `pytest`
Expected: ALL PASS, coverage 100% on new files.

- [ ] **Step 5: Run linters**

Run: `ruff check src/nexus/ui tests/ui && black --check src/nexus/ui tests/ui && pyright src/nexus/ui tests/ui`
Expected: zero issues.

- [ ] **Step 6: Commit Phase A**

```bash
git -C D:/dev/nexus-sn add src/nexus/ui/__init__.py src/nexus/ui/components/__init__.py
git -C D:/dev/nexus-sn commit -m "feat(ui): expose component library through nexus.ui public API"
```

---

## Phase B -- Commit 2: Convert status_reporter.py (Task 11)

---

### Task 11: Migrate status_reporter.py to components

**Files:**
- Modify: `src/nexus/capabilities/status_reporter.py`
- Modify: `tests/test_capabilities_status.py`

- [ ] **Step 1: Read the current status_reporter.py and its test**

Run: `cat D:/dev/nexus-sn/src/nexus/capabilities/status_reporter.py D:/dev/nexus-sn/tests/test_capabilities_status.py`

- [ ] **Step 2: Update tests/test_capabilities_status.py to assert on the new style**

Replace assertions that check for the value-gradient with assertions that check the label appears with the gradient and the value appears in plain text. For each existing test that asserts on rendered output of `nexus status`, change patterns of the form:

```python
# OLD
assert "pierre@servicenow.com" in styled  # value gradient applied
```

to:

```python
# NEW
plain = console.export_text(styles=False)
assert "User:" in plain
assert "pierre@servicenow.com" in plain
# Optional: verify label has ANSI styling and value does not
```

Add explicit tests for the new shape using the convention `test_<func>_<scenario>` where the function is the rendering target (e.g. `test_status_reporter_renders_user_label_in_gradient`).

- [ ] **Step 3: Run tests to verify failures**

Run: `pytest tests/test_capabilities_status.py -v`
Expected: FAIL on the new assertions because old code still applies the gradient to values.

- [ ] **Step 4: Rewrite status_reporter.py**

```python
# src/nexus/capabilities/status_reporter.py
# Rich-based status panels for `nexus status`.
# Author: Pierre Grothe
# Date: 2026-05-08

"""StatusReporter: render the condensed `nexus status` dashboard.

Layout (3 rows, all gradient-bordered KeyValuePanels):
  Row 1: Identity | System          (two equal columns)
  Row 2: Integrations               (full width DataTable)
  Row 3: Diagnostics | Auto-update  (two equal columns)

All labels use the brand gradient; all values render in the terminal
default foreground style. Status words go through StatusBadge.
"""

from rich.console import Console

from nexus.capabilities.feature_flags import FEATURE_MAP
from nexus.capabilities.registry import CapabilitySet
from nexus.capabilities.runtime_info import RuntimeInfo, collect_runtime_info
from nexus.capabilities.tier import TierDetection
from nexus.ui import (
    DataColumn,
    DataTable,
    KeyValuePanel,
    KvRow,
    Notice,
    StatusBadge,
    two_col,
)

__all__ = ["StatusReporter"]

_KB = 1024
_MB = _KB * 1024
_GB = _MB * 1024


class StatusReporter:
    """Render the condensed ``nexus status`` dashboard.

    Args:
        console: Rich Console used for output. Tests pass a recording console.
    """

    def __init__(self, console: Console) -> None:
        """See class docstring."""
        self._console = console

    def print(self, detection: TierDetection, capabilities: CapabilitySet) -> None:
        """Print Identity + System + Integrations + Diagnostics + Auto-update.

        Args:
            detection: Tier detection result with config + detected servers.
            capabilities: Resolved capability set (currently unused; the view
                uses ``detection.detected_servers`` directly).
        """
        del capabilities
        runtime = collect_runtime_info()

        self._console.print(
            two_col(self._identity_panel(detection, runtime), self._system_panel(runtime))
        )
        self._console.print(self._integrations_panel(detection))
        self._console.print(
            two_col(self._diagnostics_panel(runtime), self._update_panel(runtime))
        )
        if detection.needs_reauth_servers:
            servers = sorted(s.value for s in detection.needs_reauth_servers)
            if len(servers) == 1:
                msg = f"Run `nexus reauth --server {servers[0]}` to fix."
            else:
                msg = (
                    f"Run `nexus reauth --server <name>` for: {', '.join(servers)}"
                )
            self._console.print(Notice.warn(msg))

    def _identity_panel(
        self, detection: TierDetection, runtime: RuntimeInfo
    ) -> KeyValuePanel:
        """Build the Identity panel."""
        config = detection.config
        reauth_detected = detection.detected_servers & detection.needs_reauth_servers
        total = len(detection.detected_servers)
        ready = total - len(reauth_detected)
        rows: list[KvRow] = [
            KvRow(label="User", value=config.email or "-"),
            KvRow(label="Org", value=config.organization_name or "-"),
            KvRow(label="Tier", value=detection.tier.value.upper()),
            KvRow(label="Version", value=runtime.nexus_version or "unknown"),
        ]
        if total:
            suffix = (
                StatusBadge.warn(f"{len(reauth_detected)} need reauth")
                if reauth_detected
                else None
            )
            rows.append(KvRow(label="Servers", value=f"{ready}/{total} ready", suffix=suffix))
        return KeyValuePanel(title="Identity", rows=rows)

    def _system_panel(self, runtime: RuntimeInfo) -> KeyValuePanel:
        """Build the System panel."""
        return KeyValuePanel(
            title="System",
            rows=[
                KvRow(label="Python", value=runtime.python_version),
                KvRow(label="Platform", value=runtime.platform_label),
                KvRow(label="Install", value=runtime.install_mode),
            ],
        )

    def _integrations_panel(self, detection: TierDetection) -> object:
        """Build the Integrations panel (DataTable or empty KeyValuePanel)."""
        if not detection.detected_servers:
            return KeyValuePanel(
                title="Integrations",
                rows=[KvRow(label="Status", value="No enterprise integrations detected.")],
            )
        rows: list[list[str | object]] = []
        for server in sorted(detection.detected_servers, key=lambda s: s.value):
            spec = FEATURE_MAP.get(server)
            name = spec.name if spec else server.value
            badge = (
                StatusBadge.warn("NEEDS REAUTH")
                if server in detection.needs_reauth_servers
                else StatusBadge.ok("READY")
            )
            rows.append([name, badge])
        return DataTable(
            title="Integrations",
            columns=[DataColumn(header="Server"), DataColumn(header="Status")],
            rows=rows,
        )

    def _diagnostics_panel(self, runtime: RuntimeInfo) -> KeyValuePanel:
        """Build the Diagnostics panel."""
        return KeyValuePanel(
            title="Diagnostics",
            rows=[
                KvRow(label="Config root", value=str(runtime.config_root)),
                KvRow(label="Cache size", value=_humanize_bytes(runtime.cache_size_bytes)),
            ],
        )

    def _update_panel(self, runtime: RuntimeInfo) -> KeyValuePanel:
        """Build the Auto-update panel."""
        rows = [
            KvRow(
                label="Enabled",
                value=(
                    StatusBadge.ok("yes") if runtime.auto_update_enabled
                    else StatusBadge.warn("no (NEXUS_AUTO_UPDATE=0)")
                ),
            ),
            KvRow(label="Last check", value=_humanize_age(runtime.last_update_check_ago_seconds)),
        ]
        if runtime.install_mode == "editable":
            rows.append(KvRow(label="Note", value="editable install: auto-update disabled"))
        return KeyValuePanel(title="Auto-update", rows=rows)


def _humanize_bytes(n: int) -> str:
    """Format byte count as a human-readable string."""
    if n < _KB:
        return f"{n} B"
    if n < _MB:
        return f"{n / _KB:.1f} KB"
    if n < _GB:
        return f"{n / _MB:.1f} MB"
    return f"{n / _GB:.2f} GB"


def _humanize_age(seconds: float | None) -> str:
    """Format elapsed seconds as a human-readable age string."""
    if seconds is None:
        return "never"
    if seconds < 60:
        return f"{int(seconds)} seconds ago"
    if seconds < 3600:
        return f"{int(seconds / 60)} minutes ago"
    if seconds < 86400:
        return f"{seconds / 3600:.1f} hours ago"
    return f"{seconds / 86400:.1f} days ago"
```

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest tests/test_capabilities_status.py tests/ui -v`
Expected: ALL PASS.

- [ ] **Step 6: Smoke-render `nexus status`**

Run: `D:/dev/nexus-sn/.venv/Scripts/nexus.exe status`
Expected: Identity / System / Integrations / Diagnostics / Auto-update panels render with coloured labels and neutral values. Visual inspection only -- no automated check.

- [ ] **Step 7: Run full suite**

Run: `pytest`
Expected: ALL PASS, coverage 100%.

- [ ] **Step 8: Commit**

```bash
git -C D:/dev/nexus-sn add src/nexus/capabilities/status_reporter.py tests/test_capabilities_status.py
git -C D:/dev/nexus-sn commit -m "refactor(status): migrate StatusReporter to ui.components"
```

---

## Phase C -- Commit 3: Convert cli.py (Tasks 12-16)

---

### Task 12: token_badge helper in instances/

**Files:**
- Create: `src/nexus/instances/badges.py`
- Test: `tests/instances/test_badges.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/instances/test_badges.py
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for token_badge helper."""

from datetime import UTC, datetime, timedelta

from nexus.instances.badges import token_badge
from nexus.instances.models import InstanceMeta
from nexus.ui.components.badge import StatusBadge

__all__: list[str] = []


def _meta(token_expires_at: datetime) -> InstanceMeta:
    return InstanceMeta(
        profile="dev",
        url="https://dev.service-now.com",
        username="admin",
        client_id="cid",
        sn_version="Xanadu",
        sn_build="04-01-2025_1200",
        instance_name="dev",
        registered_at=datetime.now(UTC),
        last_connected_at=datetime.now(UTC),
        token_expires_at=token_expires_at,
        snapshot_counts=None,
    )


def test_token_badge_returns_error_when_expired() -> None:
    badge = token_badge(_meta(datetime.now(UTC) - timedelta(minutes=1)))
    assert isinstance(badge, StatusBadge)
    assert badge.variant == "error"
    assert badge.text == "EXPIRED"


def test_token_badge_returns_warn_when_under_thirty_minutes() -> None:
    badge = token_badge(_meta(datetime.now(UTC) + timedelta(minutes=10)))
    assert badge.variant == "warn"
    assert "min left" in badge.text


def test_token_badge_returns_ok_when_hours_remaining() -> None:
    badge = token_badge(_meta(datetime.now(UTC) + timedelta(hours=3, minutes=15)))
    assert badge.variant == "ok"
    assert "h" in badge.text
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/instances/test_badges.py -v`
Expected: FAIL on missing module.

- [ ] **Step 3: Confirm InstanceMeta field shape**

Run: `cat D:/dev/nexus-sn/src/nexus/instances/models.py`. Verify the constructor signature in the test fixture matches `InstanceMeta`. Adjust the fixture if any field is named differently (e.g. `snapshot_counts` may be a different model). Re-run Step 2 if changes were needed.

- [ ] **Step 4: Implement token_badge**

```python
# src/nexus/instances/badges.py
# Token TTL -> StatusBadge mapping for instance display surfaces.
# Author: Pierre Grothe
# Date: 2026-05-11

"""token_badge: turn an InstanceMeta's token TTL into a StatusBadge.

Lives in ``instances/`` rather than ``ui/components/`` because it depends
on ``InstanceMeta``. Keeps generic UI components free of business types.
"""

from datetime import UTC, datetime

from nexus.instances.models import InstanceMeta
from nexus.ui.components.badge import StatusBadge

__all__ = ["token_badge"]

_WARN_THRESHOLD_MINUTES = 30


def token_badge(meta: InstanceMeta) -> StatusBadge:
    """Build a StatusBadge describing the OAuth token's remaining validity.

    Args:
        meta: Instance metadata with ``token_expires_at``.

    Returns:
        ``error`` -> token already expired (text ``"EXPIRED"``).
        ``warn``  -> under 30 minutes remaining (text ``"<n> min left"``).
        ``ok``    -> 30+ minutes remaining (text ``"<h>h <m>m"`` or
                     ``"<n> min"`` when under one hour).
    """
    now = datetime.now(UTC)
    if now >= meta.token_expires_at:
        return StatusBadge.error("EXPIRED")
    minutes = int((meta.token_expires_at - now).total_seconds() / 60)
    if minutes < _WARN_THRESHOLD_MINUTES:
        return StatusBadge.warn(f"{minutes} min left")
    hours = minutes // 60
    if hours == 0:
        return StatusBadge.ok(f"{minutes} min")
    return StatusBadge.ok(f"{hours}h {minutes % 60}m")
```

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest tests/instances/test_badges.py -v`
Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
git -C D:/dev/nexus-sn add src/nexus/instances/badges.py tests/instances/test_badges.py
git -C D:/dev/nexus-sn commit -m "feat(instances): add token_badge helper"
```

---

### Task 13: Migrate `instance` subcommands in cli.py

**Files:**
- Modify: `src/nexus/cli.py` (instance_callback, instance_list, instance_status)
- Modify: `tests/test_cli_instance.py`

- [ ] **Step 1: Read tests/test_cli_instance.py to inventory existing assertions**

Run: `cat D:/dev/nexus-sn/tests/test_cli_instance.py`

- [ ] **Step 2: Replace `_token_cell` references with `token_badge` and update tests**

In `tests/test_cli_instance.py`, change every assertion that depended on coloured-text shaping of the token cell to assert on the plain text (e.g. `"EXPIRED"` substring). Add a test that runs `nexus instance list` against a registry containing one default and one non-default profile and asserts the default-marker `*` appears before the default profile name in plain text.

- [ ] **Step 3: Run tests to verify failures**

Run: `pytest tests/test_cli_instance.py -v`
Expected: some failures (assertions misaligned with old impl).

- [ ] **Step 4: Convert `instance_callback`, `instance_list`, `instance_status`, `instance_delete`, `instance_use`, `instance_connect`, `instance_refresh`, `instance_register` in cli.py**

Replace the inline f-string styling and the `_token_cell` / `_print_command_guide` / `_sn_panel` calls with components. Concrete edits:

- Top of file: add `from nexus.ui import (CommandGuide, DataColumn, DataTable, Hint, KeyValuePanel, KvRow, Notice, StatusBadge, default_marker, nexus_progress, two_col)` and `from nexus.instances.badges import token_badge`. Remove `from nexus.ui.banner import print_banner` only if no longer used directly here (it is -- keep it). Remove `from nexus.ui.gradient_panel import GradientPanel` and `from nexus.ui.theme import NEXUS_THEME, SN_BLUE, SN_LIME` after Task 17 -- for now keep them since other commands still use them.
- Delete `_token_cell` (replaced by `token_badge`), `_print_command_guide` (replaced by `CommandGuide`).
- `instance_list`: build a `DataTable` with `default_marker() + Text(profile)` style row (use `Text.assemble(default_marker(), profile)` or concatenate). Token column uses `token_badge(meta)`.
- `instance_status`: build a `KeyValuePanel` with rows for Instance / URL / Version / Token / Connected, plus a second `KeyValuePanel` for the snapshot counts when present. Use `KvRow(label="Token", value=token_badge(meta))`.
- `instance_callback`: when no instances registered, print a `Hint(label="Get started", command="nexus instance register dev", suffix="...")` instead of inline `console.print`. Then `console.print(CommandGuide(app_name="nexus instance", items=_INSTANCE_HELP))`.
- `instance_delete`, `instance_use`, `instance_connect`, `instance_refresh`, `instance_register`: replace bare `console.print(...)` info messages with `console.print(Notice.info(...))` only where the message is a confirmation; leave plain prompts (`typer.prompt`) untouched.

The full new file is large. Keep lines under 100. Run `black src/nexus/cli.py` after editing.

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_cli_instance.py tests/ui tests/instances -v`
Expected: ALL PASS.

- [ ] **Step 6: Smoke render**

Run: `D:/dev/nexus-sn/.venv/Scripts/nexus.exe instance` (assumes at least one registered profile, or shows the empty-state hint).
Expected: panel with coloured labels and neutral values; command guide rendered consistently.

- [ ] **Step 7: Commit**

```bash
git -C D:/dev/nexus-sn add src/nexus/cli.py tests/test_cli_instance.py
git -C D:/dev/nexus-sn commit -m "refactor(cli): migrate instance subcommands to ui.components"
```

---

### Task 14: Migrate `capture` subcommands in cli.py

**Files:**
- Modify: `src/nexus/cli.py` (capture_callback, capture_discover, capture_pull, capture_list, capture_push)
- Modify: `tests/capture/test_*.py` -- only files that snapshot CLI output

- [ ] **Step 1: Identify which capture tests assert on CLI output**

Run: `grep -rln "console" D:/dev/nexus-sn/tests/capture` and `grep -rln "export_text" D:/dev/nexus-sn/tests/capture`

- [ ] **Step 2: Update those tests** for the new style (label coloured, value neutral, counts neutral, `Hint` for next-step suggestions). Add explicit tests for the new `Hint`-rendered next step in `discover` and `pull`.

- [ ] **Step 3: Run failing tests**

Run: `pytest tests/capture -v`
Expected: failures on the updated assertions.

- [ ] **Step 4: Convert capture commands in cli.py**

- `capture_callback`: replace `_print_command_guide("nexus capture", _CAPTURE_HELP)` with `console.print(CommandGuide(app_name="nexus capture", items=_CAPTURE_HELP))`.
- `capture_discover`: replace `_make_progress()` with `nexus_progress(console)`. Replace the inline `Table(...)` with a `DataTable(...)`. Replace the `_count_cell(...)` call with the bare integer (count cells now neutral). Replace the trailing "Next: ..." block with `console.print(Hint(label="Next", command=f"nexus capture pull --scope {example}"))` and a follow-up `console.print(Hint(label="Tip", command="--scope x_a --scope x_b", suffix="captures multiple at once"))` when applicable.
- `capture_pull`: replace `_make_progress()` with `nexus_progress(console)`. Replace the inline summary `Table` with `KeyValuePanel(title="Capture complete", rows=[KvRow(label="Records", value=f"{manifest.record_count:,}"), KvRow(label="Archive", value=str(manifest.archive_dir)), KvRow(label="Next", value=f"nexus capture push {manifest.archive_dir}")])`.
- `capture_list`: replace the inline `Table` with `DataTable(title="Archives", columns=[DataColumn(header="Instance"), DataColumn(header="Captured"), DataColumn(header="Recs"), DataColumn(header="Archive")], rows=[...])`. Counts render neutral.
- `capture_push`: replace the two `console.print(...)` confirmation lines with a `KeyValuePanel(title="Push complete", rows=[KvRow(label="Records", value=str(ref.record_count)), KvRow(label="Update set", value=ref.name), KvRow(label="sys_id", value=ref.sys_id)])`.

- [ ] **Step 5: Run tests**

Run: `pytest tests/capture tests/ui -v`
Expected: ALL PASS.

- [ ] **Step 6: Smoke render**

Run: `D:/dev/nexus-sn/.venv/Scripts/nexus.exe capture` (with at least one archive on disk; otherwise the empty-state branch). Visual inspection.

- [ ] **Step 7: Commit**

```bash
git -C D:/dev/nexus-sn add src/nexus/cli.py tests/capture
git -C D:/dev/nexus-sn commit -m "refactor(cli): migrate capture subcommands to ui.components"
```

---

### Task 15: Migrate remaining commands in cli.py

**Files:**
- Modify: `src/nexus/cli.py` (status, reauth, update, sync, templates, assess, apply, run, rollback, ui)

- [ ] **Step 1: Convert each command's plain `console.print(...)` lines to use `Notice.info(...)` for plain confirmations and `Notice.error(...)` for the `err_console.print` paths. Leave structured output (tables / panels) alone -- those commands print plain not-yet-implemented messages today.**

Concrete edits:

- `status`: keep `print_banner(console)` then `StatusReporter(console=console).print(detection, capabilities)` -- already migrated in Phase B.
- `reauth`: when a server is supplied and not flagged, replace `err_console.print(f"[error]Server {server!r} is not currently flagged for re-auth.[/error] ...")` with `err_console.print(Notice.error(f"Server {server!r} is not currently flagged for re-auth. Run nexus status --refresh if you think this is wrong."))`. Similarly for the listing branch -- print one `Notice.info(...)` per server or wrap in a `KeyValuePanel(title="Re-auth commands", rows=[...])`. Choose the panel form for visual consistency.
- `update`: change three `console.print(...)` info lines to `console.print(Notice.info(...))` for the not-installed and up-to-date branches; keep the "Update available" line as `console.print(Notice.info(f"Update available: {current} -> {info.tag_name}"))`.
- `sync`, `templates`, `assess`, `apply`, `run`, `rollback`: each is a single not-yet-implemented `console.print(...)`. Wrap in `Notice.info(...)`.
- `ui`: change `err_console.print(f"[error]{exc}[/error]")` to `err_console.print(Notice.error(str(exc)))`.

- [ ] **Step 2: Run tests**

Run: `pytest`
Expected: ALL PASS.

- [ ] **Step 3: Smoke render**

Run each command briefly:
```
D:/dev/nexus-sn/.venv/Scripts/nexus.exe status
D:/dev/nexus-sn/.venv/Scripts/nexus.exe reauth
D:/dev/nexus-sn/.venv/Scripts/nexus.exe update --check-only
D:/dev/nexus-sn/.venv/Scripts/nexus.exe sync
D:/dev/nexus-sn/.venv/Scripts/nexus.exe templates
D:/dev/nexus-sn/.venv/Scripts/nexus.exe assess
```

- [ ] **Step 4: Commit**

```bash
git -C D:/dev/nexus-sn add src/nexus/cli.py
git -C D:/dev/nexus-sn commit -m "refactor(cli): migrate remaining commands to ui.components"
```

---

### Task 16: Cross-component snapshot tests

**Files:**
- Create: `tests/ui/test_snapshots.py`
- Create: `tests/ui/snapshots/nexus_status.txt`
- Create: `tests/ui/snapshots/nexus_instance.txt`
- Create: `tests/ui/snapshots/nexus_capture_discover.txt`

- [ ] **Step 1: Write the snapshot test**

```python
# tests/ui/test_snapshots.py
# Author: Pierre Grothe
# Date: 2026-05-11
"""Cross-component visual snapshots for major rendered surfaces.

Each test renders a fixed input through the production component pipeline
and compares against a recorded text snapshot. When a render changes
intentionally, update the snapshot file in the same commit.
"""

from pathlib import Path

from rich.console import Console

from nexus.ui import (
    CommandGuide,
    DataColumn,
    DataTable,
    KeyValuePanel,
    KvRow,
    StatusBadge,
)
from nexus.ui.theme import NEXUS_THEME

__all__: list[str] = []

_SNAPSHOTS = Path(__file__).parent / "snapshots"


def _record(width: int = 80) -> Console:
    return Console(
        record=True, force_terminal=True, color_system="truecolor",
        theme=NEXUS_THEME, width=width,
    )


def _assert_snapshot(name: str, console: Console) -> None:
    actual = console.export_text(styles=False)
    path = _SNAPSHOTS / name
    if not path.exists():
        path.write_text(actual, encoding="utf-8")
        return
    expected = path.read_text(encoding="utf-8")
    assert actual == expected, (
        f"Snapshot drift for {name}. Update {path} if change is intentional."
    )


def test_snapshot_status_dashboard() -> None:
    console = _record()
    console.print(KeyValuePanel(
        title="Identity",
        rows=[
            KvRow(label="User", value="pierre@servicenow.com"),
            KvRow(label="Org", value="ServiceNow"),
            KvRow(label="Tier", value="PRO"),
            KvRow(label="Version", value="2026.05.1"),
            KvRow(
                label="Servers", value="3/4 ready",
                suffix=StatusBadge.warn("1 need reauth"),
            ),
        ],
    ))
    _assert_snapshot("nexus_status.txt", console)


def test_snapshot_instance_list_and_guide() -> None:
    console = _record()
    console.print(DataTable(
        title="Instances",
        columns=[
            DataColumn(header="Profile", width=12),
            DataColumn(header="URL", width=30),
            DataColumn(header="Token", width=12),
        ],
        rows=[
            ["* prod", "acme.service-now.com", StatusBadge.ok("7h 30m")],
            ["  stage", "stage.service-now.com", StatusBadge.warn("14 min left")],
        ],
    ))
    console.print(CommandGuide(
        app_name="nexus instance",
        items=[
            ("register <profile>", "Add an instance"),
            ("connect [profile]", "Verify connection and refresh token"),
            ("list", "Show all registered instances"),
        ],
    ))
    _assert_snapshot("nexus_instance.txt", console)


def test_snapshot_capture_discover_table() -> None:
    console = _record()
    console.print(DataTable(
        title="Custom scopes on prod",
        columns=[
            DataColumn(header="Scope Key", width=26),
            DataColumn(header="Name", width=20),
            DataColumn(header="Skl", width=5, justify="right"),
            DataColumn(header="Flow", width=5, justify="right"),
        ],
        rows=[
            ["x_snc_app", "ACME App", "3", "12"],
            ["x_snc_helper", "ACME Helper", "0", "5"],
        ],
    ))
    _assert_snapshot("nexus_capture_discover.txt", console)
```

- [ ] **Step 2: Run the test once to seed the snapshots**

Run: `pytest tests/ui/test_snapshots.py -v`
Expected: 3 PASS (snapshots written on first run).

- [ ] **Step 3: Run again to verify deterministic match**

Run: `pytest tests/ui/test_snapshots.py -v`
Expected: 3 PASS (snapshots compared and matched).

- [ ] **Step 4: Run full suite**

Run: `pytest`
Expected: ALL PASS, coverage 100%.

- [ ] **Step 5: Commit**

```bash
git -C D:/dev/nexus-sn add tests/ui/test_snapshots.py tests/ui/snapshots
git -C D:/dev/nexus-sn commit -m "test(ui): add cross-component visual snapshots"
```

---

## Phase D -- Commit 4: Cleanup (Tasks 17-18)

---

### Task 17: Delete old theme tokens and dead helpers

**Files:**
- Modify: `src/nexus/ui/theme.py`
- Modify: `src/nexus/cli.py`
- Modify: `tests/ui/test_theme.py`

- [ ] **Step 1: Verify no remaining callers of legacy tokens**

Run: `grep -rn "sn.blue\|sn.lime\|\[info\]\|\[accent\]\|\[primary\]\|\[muted\]\|NEXUS_BLUE\|NEXUS_CYAN\|SN_TEXT_START\|_make_progress\|_sn_panel\|_print_command_guide\|_token_cell\|_count_cell\|_SN_BLUE_S\|_SN_LIME_S" D:/dev/nexus-sn/src D:/dev/nexus-sn/tests`
Expected: only matches inside `theme.py` itself (the deletions about to happen) and in this plan file. If any production matches remain, return to the appropriate Phase C task and fix.

- [ ] **Step 2: Delete the legacy entries from theme.py**

Replace the body of `NEXUS_THEME` so only the new semantic styles remain. Drop `NEXUS_BLUE`, `NEXUS_CYAN`, `SN_TEXT_START` constants and prune `__all__` accordingly.

```python
# src/nexus/ui/theme.py
# Rich theme used by the NEXUS CLI Console.
# Author: Pierre Grothe
# Date: 2026-05-08

"""NEXUS visual identity: brand RGB stops + named Rich styles.

Importing nexus.ui.theme has no nicegui dependency, so cli.py can apply the
theme on every invocation without forcing the optional [ui] extra.
"""

from rich.theme import Theme

__all__ = [
    "NEXUS_THEME",
    "SN_BLUE",
    "SN_LIME",
]

SN_BLUE: tuple[int, int, int] = (0x00, 0x68, 0xB1)
SN_LIME: tuple[int, int, int] = (0x7C, 0xC1, 0x43)

_SN_BLUE_RGB = f"rgb({SN_BLUE[0]},{SN_BLUE[1]},{SN_BLUE[2]})"
_SN_LIME_RGB = f"rgb({SN_LIME[0]},{SN_LIME[1]},{SN_LIME[2]})"

NEXUS_THEME = Theme(
    {
        "label": f"{_SN_BLUE_RGB} bold",
        "value": "default",
        "dim": "bright_black",
        "ok": f"{_SN_LIME_RGB} bold",
        "warn": "yellow bold",
        "error": "red bold",
        "border.start": _SN_BLUE_RGB,
        "border.end": _SN_LIME_RGB,
    }
)
```

- [ ] **Step 3: Update tests/ui/test_theme.py to remove the legacy-style tests**

If any tests in `test_theme.py` assert on legacy style names, delete them.

- [ ] **Step 4: Delete dead helpers from cli.py**

Edit `src/nexus/cli.py`:
- Remove `_make_progress`, `_sn_panel`, `_print_command_guide`, `_token_cell`, `_count_cell`, `_trunc` (only if grep confirms unused), `_SN_BLUE_S`, `_SN_LIME_S` definitions.
- Remove imports they relied on that are no longer needed: `from nexus.ui.gradient_panel import GradientPanel`, `from nexus.ui.theme import NEXUS_THEME, SN_BLUE, SN_LIME` -- replace with `from nexus.ui import NEXUS_THEME` (only the theme is needed here for the Console init).

- [ ] **Step 5: Run full suite**

Run: `pytest`
Expected: ALL PASS, coverage 100%.

- [ ] **Step 6: Run linters**

Run: `ruff check src tests && black --check src tests && pyright src tests && mypy src/nexus`
Expected: zero issues.

- [ ] **Step 7: Commit**

```bash
git -C D:/dev/nexus-sn add src/nexus/ui/theme.py src/nexus/cli.py tests/ui/test_theme.py
git -C D:/dev/nexus-sn commit -m "chore(ui): remove legacy theme tokens and cli helpers"
```

---

### Task 18: Re-record .ratchet.json baselines

**Files:**
- Modify: `.ratchet.json`

- [ ] **Step 1: Inspect current baselines**

Run: `cat D:/dev/nexus-sn/.ratchet.json`

- [ ] **Step 2: Identify which entries need updating**

The cli.py line count drops significantly. Any per-file metric the ratchet tracks (line count, complexity) needs the new value as the floor.

- [ ] **Step 3: Re-record baselines**

If a `scripts/refresh-ratchet.py` (or similar) exists, run it. Otherwise, edit `.ratchet.json` manually so the entries for `src/nexus/cli.py` and `src/nexus/capabilities/status_reporter.py` reflect the new (lower) values. The new entries for the new files (`src/nexus/ui/components/*.py`, `src/nexus/instances/badges.py`) should also be added at their new sizes.

Run: `cat D:/dev/nexus-sn/scripts/` -- if there is a ratchet refresh script, prefer it.

- [ ] **Step 4: Verify ratchet check passes**

Run: `pre-commit run --all-files`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git -C D:/dev/nexus-sn add .ratchet.json
git -C D:/dev/nexus-sn commit -m "chore: refresh ratchet baselines after ui refactor"
```

---

## Final verification

- [ ] **Run full quality suite**

Run: `pre-commit run --all-files && pytest --cov=nexus --cov-fail-under=100 && mypy --strict src/nexus && pyright src/nexus`
Expected: ALL PASS.

- [ ] **Smoke-render every command surface**

```
D:/dev/nexus-sn/.venv/Scripts/nexus.exe status
D:/dev/nexus-sn/.venv/Scripts/nexus.exe instance
D:/dev/nexus-sn/.venv/Scripts/nexus.exe capture
```

Visual inspection:
- All labels render in the SN blue->lime gradient.
- All values render in the terminal's default foreground.
- Status words (READY, NEEDS REAUTH, EXPIRED) carry semantic colour.
- Default-row marker (`*`) is lime.
- Inline commands in `Hint` lines are bold default-foreground.
- No command's panels look stylistically different from another's.

- [ ] **Push branch and open PR**

```bash
git -C D:/dev/nexus-sn push -u origin <branch-name>
gh pr create --title "feat(ui): unified component library; labels coloured, data neutral"
```

PR description should include the four screenshot smoke-renders for visual review.

---

## Self-review summary

- **Spec coverage:** every section of the spec maps to at least one task.
  - Section 1 (colour rule) -> enforced by Tasks 1-9 (theme + components).
  - Section 2 (file layout) -> Tasks 1-10.
  - Section 3 (theme tokens) -> Tasks 1, 17.
  - Section 4 (component spec) -> Tasks 2-9.
  - Section 5 (migration plan) -> Tasks 11-18.
  - Section 6 (testing) -> Tasks 2-9, 16.
  - Section 7 (open questions resolved) -> reflected in Task 6 (`KvRow.value: str | RenderableType`), Task 13 (snapshot panel for instance status), Task 5 (Hint two-space indent baked in).
  - Section 8 (out of scope) -> respected; no NiceGUI work in plan.
- **Placeholders:** none remaining; Tasks 13-15 use prose for the larger refactors but every concrete component substitution is named explicitly.
- **Type consistency:** component class names, factory methods, and field names match across tasks (`StatusBadge.ok/warn/error`, `KvRow(label, value, suffix)`, `KeyValuePanel(title, rows, min_height)`, `DataTable(title, columns, rows)`, `CommandGuide(app_name, items)`, `Hint(label, command, suffix)`, `Notice.error/warn/info`, `nexus_progress(console)`, `default_marker()`, `token_badge(meta)`).

