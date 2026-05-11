# CLI UI Library Design

**Goal:** A unified visualisation, display, and theme library that owns every
visual surface of the NEXUS CLI, so styling is consistent across commands and
the rule "labels coloured, data neutral" is enforced by the component types
rather than by per-command convention.

**Motivation:** Today every command in `cli.py` re-invents its own table, panel,
and inline f-string styling. `status_reporter.py` colours data values with a
gradient while `instance status` colours labels and leaves values neutral.
The two patterns disagree visually. The user-visible symptom is "different
styles depending on the command I trigger"; the underlying cause is the
absence of a component layer.

**Architecture:** Components live in `src/nexus/ui/components/`, one file per
component. Each is a frozen Pydantic model with a `__rich_console__` method,
so callers do `console.print(KeyValuePanel(...))`. The `nexus.ui` layer is
already the top of the dependency stack (depends on `cli`-level surfaces only
for theme registration); no other layer imports from it.

**Tech Stack:** Rich (existing), Pydantic v2 frozen models (existing project
convention), Python 3.14 syntax.

---

## 1. The colour rule

**Labels are coloured, values are neutral.** Concretely:

- **Field labels** (`User:`, `Token:`, `Servers:`, table headers, command-guide
  command column) render in a per-character gradient from `SN_BLUE` to `SN_LIME`.
- **Field values** (email, version, counts, paths, timestamps, table cells)
  render in the terminal's default foreground colour.

**Allowed exceptions** (semantic colour, not data colour):

- **Status words** -- `READY`, `NEEDS REAUTH`, `EXPIRED`, `FAILED`, etc., via
  `StatusBadge` in `ok` / `warn` / `error` variants.
- **Default-row marker** -- the lime bold `*` used to mark the default profile
  in `instance list`, via `default_marker()`.
- **Notice prefixes** -- `Error:`, `Warning:`, `Info:` rendered via `Notice`,
  with the prefix coloured and the message neutral.
- **Inline commands in instructional text** -- bold white (terminal default
  foreground in bold), used by `Hint` for the `Next: nexus capture pull ...`
  pattern. Bold weight, not colour.

Anything not on that list is neutral. Token TTL ("14 min left", "7h 30m"),
record counts, and similar are values -- no colour.

---

## 2. File layout

```
src/nexus/ui/
  __init__.py                # re-exports public API
  theme.py                   # tokens + Rich Theme               (refactored)
  banner.py                  # AsciiBanner                       (kept)
  gradient_panel.py          # GradientPanel + gradient_text     (kept)
  components/
    __init__.py
    panel.py                 # KeyValuePanel, KvRow, two_col
    table.py                 # DataTable, DataColumn
    badge.py                 # StatusBadge
    guide.py                 # CommandGuide
    hint.py                  # Hint
    notice.py                # Notice
    progress.py              # nexus_progress() factory
    marker.py                # default_marker()
tests/ui/
  test_theme.py
  components/
    test_panel.py
    test_table.py
    test_badge.py
    test_guide.py
    test_hint.py
    test_notice.py
    test_progress.py
    test_marker.py
  snapshots/
    nexus_status.txt
    nexus_instance.txt
    nexus_capture_discover.txt
```

**Import direction:** `components/*` import only from `nexus.ui.theme` and
`nexus.ui.gradient_panel`. They never import from `nexus.cli` or any
business-logic module. The CLI is the only consumer of components.

---

## 3. Theme tokens

`theme.py` is rewritten to expose semantic tokens. The current style names
(`sn.blue`, `sn.lime`, `info`, `accent`, `primary`) and the unused colour
constants (`NEXUS_BLUE`, `NEXUS_CYAN`, `SN_TEXT_START`) are deleted in the
same PR. No back-compat shims.

**Kept colour constants:**

| Token     | Value                  | Use                                              |
| --------- | ---------------------- | ------------------------------------------------ |
| `SN_BLUE` | `(0x00, 0x68, 0xB1)`   | left edge of label gradient + panel border start |
| `SN_LIME` | `(0x7C, 0xC1, 0x43)`   | right edge of label gradient + panel border end + `ok` semantic |

**Rich Theme map** (named styles for inline `[token]...[/token]` markup):

```python
NEXUS_THEME = Theme({
    "label":        f"rgb({SN_BLUE[0]},{SN_BLUE[1]},{SN_BLUE[2]}) bold",
    "value":        "default",
    "dim":          "bright_black",
    "ok":           f"rgb({SN_LIME[0]},{SN_LIME[1]},{SN_LIME[2]}) bold",
    "warn":         "yellow bold",
    "error":        "red bold",
    "border.start": f"rgb({SN_BLUE[0]},{SN_BLUE[1]},{SN_BLUE[2]})",
    "border.end":   f"rgb({SN_LIME[0]},{SN_LIME[1]},{SN_LIME[2]})",
})
```

The `[label]` style is a flat colour, not a per-character gradient. Per-character
gradient is applied where it matters (K/V row labels, data table headers, panel
borders) by the components calling `gradient_text()` from `gradient_panel.py`
directly. Inline `[label]...[/label]` markup is the cheap fallback for one-off
strings.

`value: "default"` resolves to whatever the terminal's foreground colour is.
This avoids forcing white over a light-themed terminal.

`ok` uses `SN_LIME` so the green semantic colour and the brand colour line up.
`warn` and `error` stay generic Rich colours -- the project does not brand
error states.

---

## 4. Component spec

Each component is a `ConfigDict(frozen=True, strict=True, extra="forbid")`
Pydantic model with `__rich_console__`. Field types use Python 3.14 syntax
(`str | None`, `list[...]`).

### KvRow + KeyValuePanel  (`components/panel.py`)

```python
class KvRow(BaseModel):
    label: str
    value: str | RenderableType
    suffix: RenderableType | None = None
```

Rendered as `<gradient-label>:<padding><value> <optional-suffix>`. Label padding
is computed at render time across all rows in the parent panel (longest label
+ two spaces). When `value` is a string it renders in `value` style; when it
is a Rich renderable (e.g. `StatusBadge`) it renders as-is.

```python
class KeyValuePanel(BaseModel):
    title: str
    rows: list[KvRow]
    min_height: int = 0
```

Wraps `rows` in a `GradientPanel(title=title, start=SN_BLUE, end=SN_LIME)` with
the rendered rows as content. `min_height` lets the caller equalise heights of
two side-by-side panels.

`two_col(left: KeyValuePanel, right: KeyValuePanel) -> Renderable` -- module-level
helper composing two panels in a two-column `Table.grid` with equal ratios and
matching `min_height`. Replaces the inline `_two_col` in `status_reporter.py`.

### DataColumn + DataTable  (`components/table.py`)

```python
class DataColumn(BaseModel):
    header: str
    width: int | None = None
    justify: Literal["left", "right", "center"] = "left"
    no_wrap: bool = True

class DataTable(BaseModel):
    title: str
    columns: list[DataColumn]
    rows: list[list[str | RenderableType]]
```

Renders a Rich `Table(box=None, show_header=True, pad_edge=False,
show_edge=False)` wrapped in a `GradientPanel(title=title)`. Header cells
are pre-rendered to `Text` via `gradient_text(column.header, start=SN_BLUE,
end=SN_LIME)` and added with `Table.add_column(header=...)`. Data cells
render in default style. Row cells can be plain strings or other components
(`StatusBadge`, the result of `default_marker() + name`, etc.).

### StatusBadge  (`components/badge.py`)

```python
class StatusBadge(BaseModel):
    text: str
    variant: Literal["ok", "warn", "error"]

    @classmethod
    def ok(cls, text: str) -> "StatusBadge": ...
    @classmethod
    def warn(cls, text: str) -> "StatusBadge": ...
    @classmethod
    def error(cls, text: str) -> "StatusBadge": ...
```

Renders as `Text(text, style=variant)` which resolves to the theme's `ok` / `warn`
/ `error` style. Used for `READY` / `NEEDS REAUTH` / `EXPIRED`, token TTL labels,
future state indicators.

### CommandGuide  (`components/guide.py`)

```python
class CommandGuide(BaseModel):
    app_name: str
    items: list[tuple[str, str]]  # (subcommand, description)
```

Renders a two-column table -- subcommand in label gradient bold, description in
dim -- wrapped in `GradientPanel(title=app_name)`, followed by a footer line
`Run <app_name> <command> --help for details.` (dim). Replaces
`_print_command_guide` in `cli.py`.

### Hint  (`components/hint.py`)

```python
class Hint(BaseModel):
    label: str
    command: str
    suffix: str | None = None
```

Renders `  <gradient-label>: <bold default command><dim suffix>`. The two-space
leading indent is baked in (does not depend on the caller indenting). Replaces
the `Next: nexus capture pull ...` lines in `capture_discover` and
`capture_pull`.

### Notice  (`components/notice.py`)

```python
class Notice(BaseModel):
    severity: Literal["error", "warn", "info"]
    message: str

    @classmethod
    def error(cls, message: str) -> "Notice": ...
    @classmethod
    def warn(cls, message: str) -> "Notice": ...
    @classmethod
    def info(cls, message: str) -> "Notice": ...
```

Renders `<colored-bold severity>: <neutral message>` with severity prefix in
`error` / `warn` / `info` (info uses the `label` style -- same blue as labels).
Used for the `Probe failed: ...` / `err_console.print(...)` patterns scattered
through `cli.py`.

### nexus_progress  (`components/progress.py`)

```python
def nexus_progress(console: Console) -> Progress: ...
```

Returns a styled Rich `Progress` (spinner, text, bar, M/N counter, time
elapsed) using the project gradient colours. Module-level function, not a
component, because Rich's `Progress` is already a context manager with
mutable state. Replaces `_make_progress` in `cli.py`.

### default_marker  (`components/marker.py`)

```python
def default_marker() -> Text: ...
```

Returns `Text("* ", style="ok")`. Used to prefix the active row in
`instance list`. Function, not a class -- it has no state.

---

## 5. Migration plan (single PR, four commits)

### Commit 1 -- Library scaffold

- `src/nexus/ui/theme.py` rewritten with semantic tokens; old styles deleted.
- `src/nexus/ui/components/{panel,table,badge,guide,hint,notice,progress,marker}.py`
  added with full implementation and `__all__`.
- `src/nexus/ui/__init__.py` re-exports the public API.
- `tests/ui/test_theme.py` and `tests/ui/components/test_*.py` -- one file
  per component.

After this commit: `nexus` CLI behaviour unchanged, library is dead code,
test suite green, 100% coverage on new files.

### Commit 2 -- Convert `status_reporter.py`

- `_panel`, `_two_col`, `_val`, `_line_count` deleted; replaced with
  `KeyValuePanel`, `two_col`, removed gradient on values.
- `_humanize_bytes` and `_humanize_age` stay -- they format strings, they
  don't paint pixels.
- The five panels (Identity / System / Integrations / Diagnostics /
  Auto-update) reconstructed using `KeyValuePanel(rows=[KvRow(...), ...])`
  and `DataTable` for Integrations.
- Reauth footer becomes `Notice.warn(...)`.
- `tests/test_capabilities_status.py` updated: assertions move from
  "value gradient applied to email" to "label gradient applied to `User:`".

### Commit 3 -- Convert `cli.py`

- Delete: `_make_progress`, `_sn_panel`, `_print_command_guide`, `_token_cell`,
  `_count_cell`, `_trunc` (if unused after migration), `_SN_BLUE_S`, `_SN_LIME_S`.
- Replace call sites in: `instance_callback`, `instance_list`, `instance_status`,
  `capture_callback`, `capture_discover`, `capture_pull`, `capture_list`,
  `capture_push`, `status`, `reauth`, `update`, `sync`, `templates`, `assess`,
  `apply`, `run`, `rollback`.
- `instance_status`'s loose `console.print()` lines for the snapshot section
  become a `KeyValuePanel` -- last bespoke render in `cli.py`.
- A small helper `token_badge(meta: InstanceMeta) -> StatusBadge` lives in
  `instances/` (depends on `InstanceMeta`, not a generic component); replaces
  `_token_cell`.
- `tests/test_cli_instance.py`, `tests/capture/test_*.py`,
  `tests/test_capabilities_status.py` updated where they snapshot CLI output.

### Commit 4 -- Cleanup + ratchet

- Re-record `.ratchet.json` baselines for `cli.py` (line count drops
  significantly).
- Remove any helper that became unused after the refactor.
- Coverage 100% restored across `nexus.ui.*` and `nexus.cli`.

### Risk gates inside the PR

- `pre-commit run --all-files` green at every commit.
- `pytest --cov=nexus --cov-fail-under=100` green at every commit.
- `mypy --strict` and `pyright --strict` zero errors.
- Manual smoke renders (`nexus status`, `nexus instance`, `nexus capture
  discover`) attached as PR-description screenshots so the visual diff is
  reviewable.

---

## 6. Testing strategy

**Per-component unit tests** -- four shapes per component:

1. **Construction** -- model accepts valid args, rejects extras
   (`extra="forbid"`).
2. **State** -- assert on the frozen model fields directly. No console needed.
3. **Render** -- `Console(record=True, width=80, force_terminal=True,
   color_system="truecolor", theme=NEXUS_THEME)`, `console.print(component)`,
   then `console.export_text()` and `console.export_text(styles=False)` for
   structural and styled assertions.
4. **TTY-off** -- `Console(record=True, force_terminal=False)`. Components
   render plain text with no ANSI when piped. Same gate `print_banner`
   already uses.

Test names follow the project convention `test_<component>_<scenario>`:
`test_kvrow_renders_label_with_gradient`,
`test_status_badge_warn_uses_yellow`,
`test_data_table_renders_neutral_cells`,
`test_command_guide_renders_footer`,
`test_hint_indents_two_spaces`,
`test_notice_error_prefixes_message`, etc.

**Cross-component visual snapshots** in `tests/ui/snapshots/`:

- `nexus_status.txt` -- full status dashboard render at width 80.
- `nexus_instance.txt` -- instance list + command guide at width 80.
- `nexus_capture_discover.txt` -- discover output at width 80.

Snapshots use a fixed-width recording console with `force_terminal=True` and
`color_system="truecolor"`. When a render changes intentionally, the snapshot
is updated in the same commit.

**No mocks** per the global rule. Tests use real `Console` (recording or
non-terminal), real component instances, real theme.

---

## 7. Open questions resolved

1. `KvRow.value: str | RenderableType` (Option B). Lets `Token: EXPIRED` use
   the badge directly as the value. Convention enforces neutrality, not the
   type system.
2. The snapshot section of `instance status` becomes a `KeyValuePanel` -- the
   last bespoke render in `cli.py`. Consistency over local economy.
3. `Hint` always renders with a two-space leading indent. The caller does not
   indent.

---

## 8. Out of scope

- The NiceGUI dashboard (`ui/app.py`). When that lands, theme tokens and
  semantic state names can be exposed as a thin shared module; renderable
  components stay Rich-only.
- A custom semgrep rule that blocks colouring values. The component types do
  the work; a lint rule would be belt-and-suspenders. Revisit only if the
  rule is observed to drift.
- Internationalisation of label / status text. Components take strings; if
  i18n is added later it wraps the strings before they reach the components.
