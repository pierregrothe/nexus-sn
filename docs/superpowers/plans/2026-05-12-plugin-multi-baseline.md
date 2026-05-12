# Plugin Multi-Baseline Drift Implementation Plan

> REQUIRED SUB-SKILL: superpowers:subagent-driven-development.

**Goal:** Replace single `plugins.baseline.json` with a `baselines/<name>.json` directory. Add `--baseline NAME` option to `drift`, plus `nexus plugins baselines list` and `nexus plugins baselines delete <name>`.

**Spec:** [2026-05-12-plugin-multi-baseline-design.md](../specs/2026-05-12-plugin-multi-baseline-design.md)

---

## File Structure

| File | Responsibility | Task |
|------|----------------|------|
| `src/nexus/plugins/baselines.py` (new) | `DEFAULT_BASELINE_NAME`, `validate_baseline_name`. | 1 |
| `src/nexus/plugins/errors.py` | Add `InvalidBaselineNameError`, `BaselineNotFoundError`. | 1 |
| `src/nexus/plugins/__init__.py` | Re-export new names. | 1 |
| `src/nexus/instances/registry.py` | Name-parameterized baseline methods. | 2 |
| `src/nexus/cli.py` | `--baseline` flag on drift; `baselines list` / `baselines delete` subcommands. | 3, 4 |
| `tests/test_plugins_baselines.py` (new) | Name validation. | 1 |
| `tests/test_instances_registry.py` | New registry methods. | 2 |
| `tests/test_cli_plugins_drift.py` | `--baseline` flag wiring. | 3 |
| `tests/test_cli_plugins_baselines.py` (new) | list/delete subcommands. | 4 |
| `.ratchet.json` | Per-module covered_lines bump. | 5 |

---

## Task 1: baselines.py name validation + errors

**Files:**
- Create: `src/nexus/plugins/baselines.py`
- Modify: `src/nexus/plugins/errors.py`
- Modify: `src/nexus/plugins/__init__.py`
- Create: `tests/test_plugins_baselines.py`

- [ ] **Step 1: Tests.** Create `tests/test_plugins_baselines.py`:

```python
# tests/test_plugins_baselines.py
# Tests for baseline-name validation.
# Author: Pierre Grothe
# Date: 2026-05-12
"""Tests for validate_baseline_name."""

import pytest

from nexus.plugins.baselines import DEFAULT_BASELINE_NAME, validate_baseline_name
from nexus.plugins.errors import InvalidBaselineNameError

__all__: list[str] = []


@pytest.mark.parametrize(
    "name",
    [
        "default",
        "pre-upgrade",
        "quarterly_2026q2",
        "a",
        "0",
        "abc-123_xyz",
        "a" * 63,
    ],
)
def test_validate_baseline_name_accepts_valid(name: str) -> None:
    validate_baseline_name(name)


@pytest.mark.parametrize(
    "name",
    [
        "",
        "_leading-underscore",
        "-leading-dash",
        "UPPERCASE",
        "has space",
        "has/slash",
        "has.dot",
        "a" * 64,
    ],
)
def test_validate_baseline_name_rejects_invalid(name: str) -> None:
    with pytest.raises(InvalidBaselineNameError):
        validate_baseline_name(name)


def test_default_baseline_name_constant() -> None:
    assert DEFAULT_BASELINE_NAME == "default"
    validate_baseline_name(DEFAULT_BASELINE_NAME)
```

- [ ] **Step 2: Run -- expect failures.**

- [ ] **Step 3: Implement `src/nexus/plugins/baselines.py`:**

```python
# src/nexus/plugins/baselines.py
# Baseline-name validation and default constants.
# Author: Pierre Grothe
# Date: 2026-05-12
"""Baseline naming policy for plugin drift baselines."""

import re

from nexus.plugins.errors import InvalidBaselineNameError

__all__ = ["DEFAULT_BASELINE_NAME", "validate_baseline_name"]

DEFAULT_BASELINE_NAME = "default"
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")


def validate_baseline_name(name: str) -> None:
    """Raise InvalidBaselineNameError when ``name`` is not a safe filename.

    Rules:
        - Lowercase ASCII letters, digits, hyphens, underscores only.
        - Must start with a letter or digit.
        - Maximum 63 characters.

    Args:
        name: Candidate baseline name.

    Raises:
        InvalidBaselineNameError: If ``name`` violates any rule above.
    """
    if not _NAME_RE.match(name):
        raise InvalidBaselineNameError(name)
```

- [ ] **Step 4: Add errors to `src/nexus/plugins/errors.py`:**

```python
class InvalidBaselineNameError(ValueError):
    """Raised when a baseline name fails the safe-filename validation.

    Attributes:
        name: The invalid baseline name as supplied by the caller.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(
            f"invalid baseline name {name!r} -- "
            "must match ^[a-z0-9][a-z0-9_-]{0,62}$"
        )


class BaselineNotFoundError(Exception):
    """Raised when a named baseline file does not exist on disk.

    Attributes:
        profile: Instance profile name.
        name: Baseline name that was requested.
    """

    def __init__(self, profile: str, name: str) -> None:
        self.profile = profile
        self.name = name
        super().__init__(f"no baseline named {name!r} for profile={profile!r}")
```

Add `"InvalidBaselineNameError"` and `"BaselineNotFoundError"` to `__all__`.

- [ ] **Step 5: Re-export from `__init__.py`.** Add to imports + `__all__`:
  `DEFAULT_BASELINE_NAME`, `validate_baseline_name`, `InvalidBaselineNameError`,
  `BaselineNotFoundError`.

- [ ] **Step 6: Run tests + full suite. Commit.**

```bash
git commit -m "feat(plugins): baseline name validation + new errors"
```

---

## Task 2: Registry baseline methods

**Files:**
- Modify: `src/nexus/instances/registry.py`
- Modify: `tests/test_instances_registry.py`

- [ ] **Step 1: Tests** (append to `tests/test_instances_registry.py`):

```python
from nexus.plugins.errors import BaselineNotFoundError


def test_load_plugin_baseline_returns_none_when_missing(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta())
    assert registry.load_plugin_baseline("dev12345", "default") is None


def test_save_and_load_plugin_baseline_round_trip(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta())
    inv = _inventory()
    registry.save_plugin_baseline("dev12345", "default", inv)
    loaded = registry.load_plugin_baseline("dev12345", "default")
    assert loaded is not None
    assert loaded.plugins[0].plugin_id == "com.snc.incident"


def test_save_creates_baselines_dir_lazily(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta())
    profile_dir = tmp_path / "dev12345"
    assert not (profile_dir / "baselines").exists()
    registry.save_plugin_baseline("dev12345", "default", _inventory())
    assert (profile_dir / "baselines" / "default.json").exists()


def test_list_plugin_baselines_returns_empty_tuple_when_dir_missing(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta())
    assert registry.list_plugin_baselines("dev12345") == ()


def test_list_plugin_baselines_sorts_names(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta())
    registry.save_plugin_baseline("dev12345", "zzz", _inventory())
    registry.save_plugin_baseline("dev12345", "aaa", _inventory())
    registry.save_plugin_baseline("dev12345", "mmm", _inventory())
    assert registry.list_plugin_baselines("dev12345") == ("aaa", "mmm", "zzz")


def test_delete_plugin_baseline_removes_file(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta())
    registry.save_plugin_baseline("dev12345", "default", _inventory())
    registry.delete_plugin_baseline("dev12345", "default")
    assert registry.load_plugin_baseline("dev12345", "default") is None


def test_delete_plugin_baseline_raises_when_missing(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta())
    with pytest.raises(BaselineNotFoundError):
        registry.delete_plugin_baseline("dev12345", "nope")


def test_legacy_baseline_file_logged_and_ignored(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    import logging

    registry = InstanceRegistry(tmp_path)
    registry.register(_meta())
    (tmp_path / "dev12345" / "plugins.baseline.json").write_text("{}", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="nexus.instances.registry"):
        assert registry.load_plugin_baseline("dev12345", "default") is None
    assert any("legacy" in r.message.lower() for r in caplog.records)
```

- [ ] **Step 2: Replace baseline methods.** In `src/nexus/instances/registry.py`,
  replace the existing `load_plugin_baseline` / `save_plugin_baseline` methods
  (the old single-file pair) with the four name-parameterized methods below.

  Add the constant near the other path constants:

```python
_BASELINES_DIR = "baselines"
```

  Add to imports:

```python
from nexus.plugins.baselines import validate_baseline_name
from nexus.plugins.errors import BaselineNotFoundError
```

  Methods:

```python
    def load_plugin_baseline(
        self, profile: str, name: str
    ) -> PluginInventory | None:
        """Read a named baseline file. Returns None if absent.

        Logs a WARNING and ignores any legacy plugins.baseline.json
        present in the profile directory.

        Raises:
            InstanceNotFoundError: If the profile directory does not exist.
            InvalidBaselineNameError: If ``name`` is not a safe filename.
        """
        validate_baseline_name(name)
        profile_dir = self._dir(profile)
        if not profile_dir.exists():
            raise InstanceNotFoundError(profile)
        self._warn_legacy_baseline(profile, profile_dir)
        baseline_file = profile_dir / _BASELINES_DIR / f"{name}.json"
        if not baseline_file.exists():
            return None
        try:
            return PluginInventory.model_validate_json(
                baseline_file.read_text(encoding="utf-8")
            )
        except ValidationError:
            log.warning(
                "baselines/%s.json schema outdated for profile=%s -- "
                "run 'nexus plugins drift --ack --baseline %s' to rebuild",
                name, profile, name,
            )
            return None

    def save_plugin_baseline(
        self, profile: str, name: str, inventory: PluginInventory
    ) -> None:
        """Atomically write a named baseline file under baselines/.

        Raises:
            InstanceNotFoundError: If the profile directory does not exist.
            InvalidBaselineNameError: If ``name`` is not a safe filename.
        """
        validate_baseline_name(name)
        profile_dir = self._dir(profile)
        if not profile_dir.exists():
            raise InstanceNotFoundError(profile)
        (profile_dir / _BASELINES_DIR).mkdir(parents=True, exist_ok=True)
        self._atomic_write(
            profile,
            f"{_BASELINES_DIR}/{name}.json",
            inventory.model_dump_json(indent=2),
        )

    def list_plugin_baselines(self, profile: str) -> tuple[str, ...]:
        """Return the names of all baselines for a profile, sorted ascending.

        Returns:
            Tuple of baseline names. Empty tuple when the baselines/ dir is
            absent or contains no .json files.

        Raises:
            InstanceNotFoundError: If the profile directory does not exist.
        """
        profile_dir = self._dir(profile)
        if not profile_dir.exists():
            raise InstanceNotFoundError(profile)
        self._warn_legacy_baseline(profile, profile_dir)
        baselines_dir = profile_dir / _BASELINES_DIR
        if not baselines_dir.exists():
            return ()
        return tuple(sorted(p.stem for p in baselines_dir.glob("*.json")))

    def delete_plugin_baseline(self, profile: str, name: str) -> None:
        """Remove a named baseline.

        Raises:
            InstanceNotFoundError: If the profile directory does not exist.
            InvalidBaselineNameError: If ``name`` is not a safe filename.
            BaselineNotFoundError: If the file does not exist.
        """
        validate_baseline_name(name)
        profile_dir = self._dir(profile)
        if not profile_dir.exists():
            raise InstanceNotFoundError(profile)
        baseline_file = profile_dir / _BASELINES_DIR / f"{name}.json"
        if not baseline_file.exists():
            raise BaselineNotFoundError(profile, name)
        baseline_file.unlink()

    def _warn_legacy_baseline(self, profile: str, profile_dir: Path) -> None:
        """Emit a one-line WARNING when plugins.baseline.json is present.

        The legacy single-file baseline was replaced by baselines/<name>.json
        in sub-project L. Users must re-ack to migrate.
        """
        legacy = profile_dir / "plugins.baseline.json"
        if legacy.exists():
            log.warning(
                "legacy plugins.baseline.json for profile=%s is ignored; "
                "re-ack via 'nexus plugins drift --ack' to create a named baseline",
                profile,
            )
```

The `_atomic_write` helper does not currently support nested filenames
(it builds `profile_dir / filename`). Confirm by reading the method; if
it joins the filename via slash already, the `f"{_BASELINES_DIR}/{name}.json"`
form will work. If it uses a flat single-name interpretation, update
`_atomic_write` to accept a relative subpath (or special-case the
baseline writes). Inspect and adapt accordingly.

- [ ] **Step 3: Run tests + full suite. Commit.**

```bash
git commit -m "feat(instances): name-parameterized baseline registry methods"
```

---

## Task 3: `--baseline` flag on `nexus plugins drift`

**Files:**
- Modify: `src/nexus/cli.py`
- Modify: `tests/test_cli_plugins_drift.py`

- [ ] **Step 1: Tests.** Update existing `test_cli_plugins_drift.py` tests
  that rely on the old single-file baseline path. Add new tests:

```python
def test_drift_uses_default_baseline_when_no_flag(runner, tmp_path, monkeypatch):
    # Seed an inventory and ack default baseline; run drift -- expect no entries
    ...


def test_drift_with_baseline_flag_compares_against_named(runner, tmp_path, monkeypatch):
    # Save two baselines (default + custom); run drift --baseline custom
    ...


def test_drift_with_invalid_baseline_name_exits_one(runner, tmp_path):
    result = runner.invoke(app, ["plugins", "drift", "--baseline", "BAD NAME"])
    assert result.exit_code == 1
    assert "invalid baseline name" in result.output.lower()


def test_drift_with_missing_baseline_exits_one(runner, tmp_path, monkeypatch):
    # Seed inventory only -- no baseline. drift --baseline missing -> exit 1 with hint
    ...
```

- [ ] **Step 2: Update `plugins_drift` in cli.py.** Add the option:

```python
    baseline_name: Annotated[
        str,
        typer.Option(
            "--baseline",
            help=f"Named baseline to compare against (default: {DEFAULT_BASELINE_NAME}).",
        ),
    ] = DEFAULT_BASELINE_NAME,
```

  Inside the function, validate the name via `validate_baseline_name`,
  then pass it to `registry.load_plugin_baseline(profile, baseline_name)`.
  The `--ack` branch calls `registry.save_plugin_baseline(profile,
  baseline_name, current_inventory)`.

  Update the error path: when `load_plugin_baseline` returns None and
  `--ack` is not set, print a hint mentioning `--baseline <name>`.

  Add to top imports:

```python
from nexus.plugins.baselines import DEFAULT_BASELINE_NAME, validate_baseline_name
from nexus.plugins.errors import InvalidBaselineNameError
```

  Wrap the `validate_baseline_name` call in `try/except
  InvalidBaselineNameError` to print a friendly error.

- [ ] **Step 3: Run tests + commit.**

```bash
git commit -m "feat(cli): --baseline flag on plugins drift"
```

---

## Task 4: `nexus plugins baselines list` + `baselines delete` subcommands

**Files:**
- Modify: `src/nexus/cli.py`
- Create: `tests/test_cli_plugins_baselines.py`

- [ ] **Step 1: Tests.** Cover: list with zero baselines prints info notice;
  list with N renders DataTable; delete removes the file; delete missing exits 1;
  delete invalid name exits 1.

- [ ] **Step 2: Add a sub-app for baselines.** In cli.py:

```python
baselines_app = typer.Typer(no_args_is_help=True, help="Manage plugin drift baselines.")
plugins_app.add_typer(baselines_app, name="baselines")


@baselines_app.command("list")
def plugins_baselines_list(
    instance: Annotated[
        str,
        typer.Option("--instance", help="Instance profile (default: configured default)"),
    ] = "",
) -> None:
    """Show all named baselines for an instance."""
    paths = NexusPaths.from_env()
    registry = InstanceRegistry(paths.instances_dir)
    meta, _ = _load_inventory_or_exit(instance)
    names = registry.list_plugin_baselines(meta.profile)
    if not names:
        console.print(Notice.info(f"No baselines saved for {meta.profile}."))
        return
    rows: list[list[RenderableType]] = []
    for n in names:
        inv = registry.load_plugin_baseline(meta.profile, n)
        if inv is None:
            continue
        rows.append([n, str(inv.captured_at)[:19], str(len(inv.plugins))])
    console.print(
        DataTable(
            title=f"Baselines for instance {meta.profile}",
            columns=[
                DataColumn(header="Name", width=24),
                DataColumn(header="Captured", width=20),
                DataColumn(header="Plugins", width=8),
            ],
            rows=rows,
        )
    )


@baselines_app.command("delete")
def plugins_baselines_delete(
    name: Annotated[str, typer.Argument(help="Baseline name to delete.")],
    instance: Annotated[
        str,
        typer.Option("--instance", help="Instance profile (default: configured default)"),
    ] = "",
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation."),
    ] = False,
) -> None:
    """Delete a named baseline."""
    try:
        validate_baseline_name(name)
    except InvalidBaselineNameError as exc:
        console.print(Notice.error(str(exc)))
        raise typer.Exit(1) from exc
    paths = NexusPaths.from_env()
    registry = InstanceRegistry(paths.instances_dir)
    meta, _ = _load_inventory_or_exit(instance)
    if not yes:
        confirmed = typer.confirm(f"Delete baseline {name!r} for {meta.profile}?")
        if not confirmed:
            console.print(Notice.info("Aborted."))
            return
    try:
        registry.delete_plugin_baseline(meta.profile, name)
    except BaselineNotFoundError as exc:
        console.print(Notice.error(str(exc)))
        raise typer.Exit(1) from exc
    console.print(Notice.info(f"Deleted baseline {name}"))
```

  Import `BaselineNotFoundError` at the top.

- [ ] **Step 3: Run tests + commit.**

---

## Task 5: Coverage ratchet + final pre-commit

- [ ] **Step 1: Run focused coverage** on `nexus.plugins.baselines`,
  `nexus.plugins.errors`, `nexus.instances.registry`, `nexus.cli`.

- [ ] **Step 2: Update `.ratchet.json`.** Add entry for `nexus.plugins.baselines`
  (new module). Bump existing entries as needed.

- [ ] **Step 3: `pre-commit run --all-files` must pass.** Apply black if needed.

- [ ] **Step 4: Commit.**

```bash
git commit -m "chore(ratchet): bump coverage baselines after sub-project L"
```

---

## Self-Review

**Spec coverage:**
- Multi-named baselines on disk -> Task 2
- `validate_baseline_name` + errors -> Task 1
- `--baseline` flag on drift -> Task 3
- `baselines list` + `baselines delete` -> Task 4
- Legacy file warning -> Task 2 (`_warn_legacy_baseline`)
- Ratchet bump -> Task 5

**Type consistency:** `validate_baseline_name(name: str) -> None`,
`load_plugin_baseline(profile: str, name: str) -> PluginInventory | None`,
`list_plugin_baselines(profile: str) -> tuple[str, ...]`,
`delete_plugin_baseline(profile: str, name: str) -> None`.
