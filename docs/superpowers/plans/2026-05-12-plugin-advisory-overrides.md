# Plugin Advisory Overrides Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Per-instance deferral of EOL/CVE/license advisory findings with required reason. Three CLI subcommands (`defer`, `undo-defer`, `list-deferred`) plus a `--include-deferred` flag.

**Architecture:** New pure module `overrides.py` (Pydantic models + `apply_overrides`). New per-instance YAML artifact `advisory-overrides.yaml`. Registry methods mirror the inventory/baseline pattern.

**Tech Stack:** Python 3.14+, Pydantic v2 frozen+strict+extra=forbid, PyYAML for YAML I/O, typer for CLI.

**Spec:** [docs/superpowers/specs/2026-05-12-plugin-advisory-overrides-design.md](../specs/2026-05-12-plugin-advisory-overrides-design.md)

---

## File Structure

| File | Responsibility | Task |
|------|----------------|------|
| `src/nexus/plugins/overrides.py` (new) | AdvisoryOverride, AdvisoryOverrideSet, apply_overrides. | 1 |
| `src/nexus/plugins/errors.py` | Add AdvisoryOverrideError. | 1 |
| `src/nexus/plugins/__init__.py` | Re-export new public names. | 1 |
| `src/nexus/instances/registry.py` | load_advisory_overrides + save_advisory_overrides. | 2 |
| `src/nexus/cli.py` | Three new subcommands + --include-deferred flag. | 3, 4, 5, 6 |
| `tests/test_plugins_overrides.py` (new) | Tests for apply_overrides and models. | 1 |
| `tests/test_instances_registry.py` | Tests for new registry methods. | 2 |
| `tests/test_cli_plugins_advisories_defer.py` (new) | Tests for defer/undo-defer/list-deferred. | 3-6 |
| `tests/test_cli_plugins_advisories.py` | Updates for --include-deferred + summary count. | 6 |
| `.ratchet.json` | Per-module covered_lines bump. | 7 |

---

## Task 1: overrides.py module + AdvisoryOverrideError

**Files:**
- Create: `src/nexus/plugins/overrides.py`
- Modify: `src/nexus/plugins/errors.py`
- Modify: `src/nexus/plugins/__init__.py`
- Create: `tests/test_plugins_overrides.py`

- [ ] **Step 1: Write failing tests** in `tests/test_plugins_overrides.py`:

```python
# tests/test_plugins_overrides.py
# Tests for advisory override models and apply_overrides.
# Author: Pierre Grothe
# Date: 2026-05-12
"""Tests for AdvisoryOverride, AdvisoryOverrideSet, apply_overrides."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from nexus.plugins.models import AdvisoryFinding, AdvisorySet, AdvisoryType, Severity
from nexus.plugins.overrides import (
    AdvisoryOverride,
    AdvisoryOverrideSet,
    apply_overrides,
)

__all__: list[str] = []


def _finding(
    plugin_id: str = "com.x",
    advisory_type: AdvisoryType = AdvisoryType.CVE,
    details: str = "CVE-2024-1",
    severity: Severity = Severity.HIGH,
) -> AdvisoryFinding:
    return AdvisoryFinding(
        plugin_id=plugin_id,
        plugin_name=plugin_id,
        plugin_version="1.0",
        advisory_type=advisory_type,
        severity=severity,
        summary="x",
        details=details,
    )


def _override(
    plugin_id: str = "com.x",
    advisory_type: AdvisoryType = AdvisoryType.CVE,
    details: str = "CVE-2024-1",
    reason: str = "ok",
) -> AdvisoryOverride:
    return AdvisoryOverride(
        plugin_id=plugin_id,
        advisory_type=advisory_type,
        details=details,
        reason=reason,
        created_at=datetime(2026, 5, 12, tzinfo=UTC),
    )


def test_advisory_override_is_frozen() -> None:
    o = _override()
    with pytest.raises(ValidationError):
        o.reason = "changed"


def test_advisory_override_rejects_empty_reason() -> None:
    with pytest.raises(ValidationError):
        AdvisoryOverride(
            plugin_id="com.x",
            advisory_type=AdvisoryType.CVE,
            details="CVE-2024-1",
            reason="",
            created_at=datetime(2026, 5, 12, tzinfo=UTC),
        )


def test_advisory_override_set_round_trips_through_json() -> None:
    s = AdvisoryOverrideSet(overrides=(_override(),))
    re = AdvisoryOverrideSet.model_validate_json(s.model_dump_json())
    assert re == s


def test_apply_overrides_with_no_overrides_returns_all_findings() -> None:
    findings = (_finding("com.a"), _finding("com.b"))
    advisories = AdvisorySet(findings=findings)
    overrides = AdvisoryOverrideSet(overrides=())
    remaining, deferred = apply_overrides(advisories, overrides)
    assert remaining.findings == findings
    assert deferred == ()


def test_apply_overrides_filters_matching_finding() -> None:
    finding = _finding("com.x", AdvisoryType.CVE, "CVE-2024-1")
    advisories = AdvisorySet(findings=(finding,))
    overrides = AdvisoryOverrideSet(
        overrides=(_override("com.x", AdvisoryType.CVE, "CVE-2024-1"),)
    )
    remaining, deferred = apply_overrides(advisories, overrides)
    assert remaining.findings == ()
    assert deferred == (finding,)


def test_apply_overrides_no_match_on_different_details() -> None:
    finding = _finding(details="CVE-2024-1")
    advisories = AdvisorySet(findings=(finding,))
    overrides = AdvisoryOverrideSet(overrides=(_override(details="CVE-2024-2"),))
    remaining, deferred = apply_overrides(advisories, overrides)
    assert remaining.findings == (finding,)
    assert deferred == ()


def test_apply_overrides_no_match_on_different_advisory_type() -> None:
    finding = _finding(advisory_type=AdvisoryType.CVE)
    advisories = AdvisorySet(findings=(finding,))
    overrides = AdvisoryOverrideSet(
        overrides=(_override(advisory_type=AdvisoryType.EOL),)
    )
    remaining, deferred = apply_overrides(advisories, overrides)
    assert remaining.findings == (finding,)


def test_apply_overrides_preserves_sort_order_of_remaining() -> None:
    a, b, c = _finding("com.a"), _finding("com.b"), _finding("com.c")
    advisories = AdvisorySet(findings=(a, b, c))
    overrides = AdvisoryOverrideSet(overrides=(_override("com.b"),))
    remaining, deferred = apply_overrides(advisories, overrides)
    assert remaining.findings == (a, c)
    assert deferred == (b,)


def test_apply_overrides_multi_match_filters_all() -> None:
    f1 = _finding("com.x", AdvisoryType.CVE, "CVE-2024-1")
    f2 = _finding("com.x", AdvisoryType.CVE, "CVE-2024-2")
    advisories = AdvisorySet(findings=(f1, f2))
    overrides = AdvisoryOverrideSet(
        overrides=(
            _override("com.x", AdvisoryType.CVE, "CVE-2024-1"),
            _override("com.x", AdvisoryType.CVE, "CVE-2024-2"),
        )
    )
    remaining, deferred = apply_overrides(advisories, overrides)
    assert remaining.findings == ()
    assert set(deferred) == {f1, f2}


def test_public_api_reexports() -> None:
    import nexus.plugins as plugins_pkg

    for name in ("AdvisoryOverride", "AdvisoryOverrideSet", "apply_overrides"):
        assert name in plugins_pkg.__all__
        assert hasattr(plugins_pkg, name)
```

- [ ] **Step 2: Run tests to verify they fail.** `pytest tests/test_plugins_overrides.py -v`.

- [ ] **Step 3: Implement `src/nexus/plugins/overrides.py`:**

```python
# src/nexus/plugins/overrides.py
# Per-instance advisory override (defer) logic.
# Author: Pierre Grothe
# Date: 2026-05-12
"""AdvisoryOverride, AdvisoryOverrideSet, and apply_overrides."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from nexus.config.types import UtcDatetime
from nexus.plugins.models import AdvisoryFinding, AdvisorySet, AdvisoryType

__all__ = [
    "AdvisoryOverride",
    "AdvisoryOverrideSet",
    "apply_overrides",
]

_FROZEN = ConfigDict(frozen=True, strict=True, extra="forbid")


class AdvisoryOverride(BaseModel):
    """One deferred advisory finding.

    Attributes:
        plugin_id: SN plugin identifier matching ``AdvisoryFinding.plugin_id``.
        advisory_type: Advisory category being deferred.
        details: The exact ``AdvisoryFinding.details`` string identifying the
            specific finding (CVE id, EOL date string, license vendor).
        reason: Free-form non-empty justification.
        created_at: When the override was recorded (UTC).
    """

    model_config = _FROZEN

    plugin_id: str
    advisory_type: AdvisoryType
    details: str
    reason: Annotated[str, Field(min_length=1)]
    created_at: UtcDatetime


class AdvisoryOverrideSet(BaseModel):
    """All overrides for one profile.

    Attributes:
        overrides: Tuple sorted by ``(plugin_id, advisory_type, details)``.
    """

    model_config = _FROZEN

    overrides: tuple[AdvisoryOverride, ...]


def _key(plugin_id: str, advisory_type: AdvisoryType, details: str) -> tuple[str, str, str]:
    """Return the match tuple keyed by the finding's identity triple."""
    return (plugin_id, advisory_type.value, details)


def apply_overrides(
    advisories: AdvisorySet,
    overrides: AdvisoryOverrideSet,
) -> tuple[AdvisorySet, tuple[AdvisoryFinding, ...]]:
    """Split findings into (remaining, deferred) using the override key triple.

    Args:
        advisories: Output from ``compute_advisories``.
        overrides: Loaded override set for the instance.

    Returns:
        ``(remaining, deferred)``. ``remaining`` is an AdvisorySet with all
        non-overridden findings in their original sort order. ``deferred``
        is the tuple of filtered findings in their original sort order.
    """
    keyset = {_key(o.plugin_id, o.advisory_type, o.details) for o in overrides.overrides}
    remaining: list[AdvisoryFinding] = []
    deferred: list[AdvisoryFinding] = []
    for finding in advisories.findings:
        if _key(finding.plugin_id, finding.advisory_type, finding.details) in keyset:
            deferred.append(finding)
        else:
            remaining.append(finding)
    return AdvisorySet(findings=tuple(remaining)), tuple(deferred)
```

- [ ] **Step 4: Add error to `src/nexus/plugins/errors.py`.** Append:

```python
class AdvisoryOverrideError(Exception):
    """Raised by the CLI override commands on user-input failure.

    Attributes:
        plugin_id: Plugin identifier referenced by the failed command.
        advisory_type: Advisory type referenced by the failed command.
        details: Finding details string referenced by the failed command.
        reason_code: One of ``no_matching_finding``, ``duplicate``, ``not_found``.
    """

    def __init__(
        self,
        plugin_id: str,
        advisory_type: str,
        details: str,
        reason_code: str,
    ) -> None:
        self.plugin_id = plugin_id
        self.advisory_type = advisory_type
        self.details = details
        self.reason_code = reason_code
        super().__init__(
            f"override {reason_code} for plugin={plugin_id} "
            f"type={advisory_type} details={details!r}"
        )
```

Add `"AdvisoryOverrideError"` to errors.py `__all__`.

- [ ] **Step 5: Update `src/nexus/plugins/__init__.py`.** Add re-exports for `AdvisoryOverride`, `AdvisoryOverrideSet`, `apply_overrides`, and `AdvisoryOverrideError`.

- [ ] **Step 6: Run tests + full suite.** `pytest tests/test_plugins_overrides.py -v && pytest -q`. Expected: all PASS.

- [ ] **Step 7: Commit.**

```bash
git add src/nexus/plugins/overrides.py src/nexus/plugins/errors.py src/nexus/plugins/__init__.py tests/test_plugins_overrides.py
git commit -m "$(cat <<'EOF'
feat(plugins): AdvisoryOverride model and apply_overrides function

Pure layer: Pydantic AdvisoryOverride / AdvisoryOverrideSet plus
apply_overrides(advisories, overrides) -> (remaining, deferred). Match
key is the (plugin_id, advisory_type, details) triple. Error type
AdvisoryOverrideError covers CLI input-failure cases.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Registry persistence

**Files:**
- Modify: `src/nexus/instances/registry.py`
- Modify: `tests/test_instances_registry.py`

- [ ] **Step 1: Write failing tests** (append to `tests/test_instances_registry.py`):

```python
from datetime import UTC, datetime as dt
from nexus.plugins.models import AdvisoryType
from nexus.plugins.overrides import AdvisoryOverride, AdvisoryOverrideSet


def _override_set() -> AdvisoryOverrideSet:
    return AdvisoryOverrideSet(
        overrides=(
            AdvisoryOverride(
                plugin_id="com.x",
                advisory_type=AdvisoryType.CVE,
                details="CVE-2024-1",
                reason="WAF rule in place",
                created_at=dt(2026, 5, 12, tzinfo=UTC),
            ),
        )
    )


def test_load_advisory_overrides_returns_empty_when_file_missing(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta())
    result = registry.load_advisory_overrides("dev12345")
    assert result.overrides == ()


def test_save_and_load_advisory_overrides_round_trips(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta())
    expected = _override_set()
    registry.save_advisory_overrides("dev12345", expected)
    loaded = registry.load_advisory_overrides("dev12345")
    assert loaded == expected


def test_load_advisory_overrides_with_legacy_shape_returns_empty_and_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    registry = InstanceRegistry(tmp_path)
    registry.register(_meta())
    bogus = "overrides:\n  - plugin_id: com.x\n    unknown_field: 1\n"
    (tmp_path / "dev12345" / "advisory-overrides.yaml").write_text(bogus, encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="nexus.instances.registry"):
        result = registry.load_advisory_overrides("dev12345")
    assert result.overrides == ()
    assert any("overrides" in r.message.lower() for r in caplog.records)


def test_load_advisory_overrides_raises_when_profile_missing(tmp_path: Path) -> None:
    registry = InstanceRegistry(tmp_path)
    with pytest.raises(InstanceNotFoundError):
        registry.load_advisory_overrides("nonexistent")
```

- [ ] **Step 2: Run tests to confirm failures.**

- [ ] **Step 3: Add methods to `src/nexus/instances/registry.py`.** Add new constant near the top:

```python
_ADVISORY_OVERRIDES = "advisory-overrides.yaml"
```

Add the imports for YAML handling at the top:

```python
import yaml

from nexus.plugins.overrides import AdvisoryOverrideSet
```

Add the two methods on `InstanceRegistry`:

```python
    def load_advisory_overrides(self, profile: str) -> AdvisoryOverrideSet:
        """Read advisory-overrides.yaml for a profile, or return an empty set.

        Args:
            profile: Profile name.

        Returns:
            AdvisoryOverrideSet with the persisted overrides, or an empty set
            when the file is missing or has a stale schema. Schema mismatches
            log a WARNING.

        Raises:
            InstanceNotFoundError: If the profile directory does not exist.
        """
        profile_dir = self._dir(profile)
        if not profile_dir.exists():
            raise InstanceNotFoundError(profile)
        file_path = profile_dir / _ADVISORY_OVERRIDES
        if not file_path.exists():
            return AdvisoryOverrideSet(overrides=())
        try:
            data = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
            return AdvisoryOverrideSet.model_validate(data)
        except (yaml.YAMLError, ValidationError):
            log.warning(
                "advisory-overrides.yaml schema outdated for profile=%s -- "
                "edit by hand or remove the file",
                profile,
            )
            return AdvisoryOverrideSet(overrides=())

    def save_advisory_overrides(
        self, profile: str, overrides: AdvisoryOverrideSet
    ) -> None:
        """Atomically write advisory-overrides.yaml for a profile.

        Args:
            profile: Profile name.
            overrides: Override set to persist.

        Raises:
            InstanceNotFoundError: If the profile directory does not exist.
        """
        payload = yaml.safe_dump(overrides.model_dump(mode="json"), sort_keys=False)
        self._atomic_write(profile, _ADVISORY_OVERRIDES, payload)
```

- [ ] **Step 4: Run tests + full suite.** Expected: all PASS.

- [ ] **Step 5: Commit.**

```bash
git add src/nexus/instances/registry.py tests/test_instances_registry.py
git commit -m "$(cat <<'EOF'
feat(instances): persist advisory-overrides.yaml per profile

load_advisory_overrides returns empty set when missing or schema-stale
(logs WARNING). save_advisory_overrides atomic-writes via the existing
_atomic_write helper. YAML format chosen for human review and
hand-editing.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: CLI `plugins advisories defer` subcommand

**Files:**
- Modify: `src/nexus/cli.py`
- Create: `tests/test_cli_plugins_advisories_defer.py`

- [ ] **Step 1: Write failing tests** in `tests/test_cli_plugins_advisories_defer.py`. Follow the pattern in existing `tests/test_cli_plugins_*.py` files. Cover: seed inventory with a known CVE finding -> defer it -> verify advisory-overrides.yaml written; defer same CVE twice -> exit 1 (duplicate); defer a non-existent finding -> exit 1 (no matching finding); reason omitted -> typer click error.

- [ ] **Step 2: Add the subcommand to `cli.py`.** Inside the `plugins_app` typer group (alongside `plugins_advisories`):

```python
@plugins_app.command("defer")
def plugins_advisories_defer(
    plugin_id: Annotated[str, typer.Argument(help="SN plugin identifier")],
    advisory_type: Annotated[str, typer.Argument(help="eol | cve | license")],
    details: Annotated[str, typer.Argument(help="Exact finding details string")],
    reason: Annotated[str, typer.Option("--reason", help="Required justification")],
    instance: Annotated[
        str,
        typer.Option("--instance", help="Instance profile (default: configured default)"),
    ] = "",
) -> None:
    """Defer an EOL/CVE/license advisory finding on a plugin."""
    try:
        wanted_type = AdvisoryType(advisory_type)
    except ValueError as exc:
        console.print(Notice.error(f"Unknown advisory type: {advisory_type}"))
        raise typer.Exit(1) from exc
    if not reason.strip():
        console.print(Notice.error("--reason must not be empty"))
        raise typer.Exit(1)

    paths = NexusPaths.from_env()
    registry = InstanceRegistry(paths.instances_dir)
    meta, inventory = _load_inventory_or_exit(instance)
    db = AdvisoryDatabase.load()
    today = datetime.now(UTC).date()
    advisories = compute_advisories(inventory, db, today=today)

    if not any(
        f.plugin_id == plugin_id and f.advisory_type is wanted_type and f.details == details
        for f in advisories.findings
    ):
        console.print(
            Notice.error(
                f"No matching finding for plugin={plugin_id} type={wanted_type.value} "
                f"details={details!r}"
            )
        )
        raise typer.Exit(1)

    existing = registry.load_advisory_overrides(meta.profile)
    if any(
        o.plugin_id == plugin_id
        and o.advisory_type is wanted_type
        and o.details == details
        for o in existing.overrides
    ):
        console.print(Notice.error("Override already exists for that finding"))
        raise typer.Exit(1)

    new_override = AdvisoryOverride(
        plugin_id=plugin_id,
        advisory_type=wanted_type,
        details=details,
        reason=reason,
        created_at=datetime.now(UTC),
    )
    combined = tuple(
        sorted(
            (*existing.overrides, new_override),
            key=lambda o: (o.plugin_id, o.advisory_type.value, o.details),
        )
    )
    registry.save_advisory_overrides(
        meta.profile, AdvisoryOverrideSet(overrides=combined)
    )
    console.print(Notice.info(f"Deferred {wanted_type.value} {details} on {plugin_id}"))
```

Add to top imports:

```python
from nexus.plugins.overrides import AdvisoryOverride, AdvisoryOverrideSet, apply_overrides
```

- [ ] **Step 3: Run tests + full suite + commit.**

```bash
git commit -m "$(cat <<'EOF'
feat(cli): plugins advisories defer subcommand

Adds a finding to the per-instance advisory-overrides.yaml. Validates
the advisory_type, requires a non-empty reason, requires a matching
finding currently in compute_advisories output, and rejects duplicates.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: CLI `plugins advisories undo-defer` subcommand

**Files:**
- Modify: `src/nexus/cli.py`
- Modify: `tests/test_cli_plugins_advisories_defer.py`

- [ ] **Step 1: Write failing tests:** undo an existing override -> file updated; undo nonexistent -> exit 1 (not_found).

- [ ] **Step 2: Add subcommand:**

```python
@plugins_app.command("undo-defer")
def plugins_advisories_undo_defer(
    plugin_id: Annotated[str, typer.Argument(help="SN plugin identifier")],
    advisory_type: Annotated[str, typer.Argument(help="eol | cve | license")],
    details: Annotated[str, typer.Argument(help="Exact finding details string")],
    instance: Annotated[
        str,
        typer.Option("--instance", help="Instance profile (default: configured default)"),
    ] = "",
) -> None:
    """Remove a previously deferred advisory finding."""
    try:
        wanted_type = AdvisoryType(advisory_type)
    except ValueError as exc:
        console.print(Notice.error(f"Unknown advisory type: {advisory_type}"))
        raise typer.Exit(1) from exc

    paths = NexusPaths.from_env()
    registry = InstanceRegistry(paths.instances_dir)
    meta, _ = _load_inventory_or_exit(instance)
    existing = registry.load_advisory_overrides(meta.profile)
    filtered = tuple(
        o
        for o in existing.overrides
        if not (
            o.plugin_id == plugin_id
            and o.advisory_type is wanted_type
            and o.details == details
        )
    )
    if len(filtered) == len(existing.overrides):
        console.print(Notice.error("No matching override found"))
        raise typer.Exit(1)
    registry.save_advisory_overrides(meta.profile, AdvisoryOverrideSet(overrides=filtered))
    console.print(Notice.info(f"Removed override for {wanted_type.value} {details} on {plugin_id}"))
```

- [ ] **Step 3: Run tests + commit.**

---

## Task 5: CLI `plugins advisories list-deferred` subcommand

**Files:**
- Modify: `src/nexus/cli.py`
- Modify: `tests/test_cli_plugins_advisories_defer.py`

- [ ] **Step 1: Tests:** empty list prints "No advisory overrides"; populated list renders table with plugin/type/details/reason/created.

- [ ] **Step 2: Add subcommand using DataTable + DataColumn:**

```python
@plugins_app.command("list-deferred")
def plugins_advisories_list_deferred(
    instance: Annotated[
        str,
        typer.Option("--instance", help="Instance profile (default: configured default)"),
    ] = "",
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: text | json (default: text)"),
    ] = "text",
) -> None:
    """List all deferred advisory findings for an instance."""
    _validate_format(output_format)
    paths = NexusPaths.from_env()
    registry = InstanceRegistry(paths.instances_dir)
    meta, _ = _load_inventory_or_exit(instance)
    overrides_set = registry.load_advisory_overrides(meta.profile)

    if output_format == "json":
        _emit_json(overrides_set)
        return
    if not overrides_set.overrides:
        console.print(Notice.info("No advisory overrides."))
        return

    rows: list[list[RenderableType]] = [
        [
            o.plugin_id,
            o.advisory_type.value,
            _trunc(o.details, 30),
            _trunc(o.reason, 40),
            str(o.created_at.date()),
        ]
        for o in overrides_set.overrides
    ]
    console.print(
        DataTable(
            title="Deferred advisories",
            columns=[
                DataColumn(header="Plugin", width=28),
                DataColumn(header="Type", width=8),
                DataColumn(header="Details", width=30),
                DataColumn(header="Reason", width=40),
                DataColumn(header="Created", width=12),
            ],
            rows=rows,
        )
    )
```

- [ ] **Step 3: Run tests + commit.**

---

## Task 6: `--include-deferred` flag on `advisories` + summary count

**Files:**
- Modify: `src/nexus/cli.py`
- Modify: `tests/test_cli_plugins_advisories.py`
- Modify: `tests/test_cli_plugins_advisories_defer.py`

- [ ] **Step 1: Tests:** default invocation excludes overridden findings; summary shows `; N deferred`; with `--include-deferred`, deferred findings appear with `[deferred]` prefix.

- [ ] **Step 2: Modify `plugins_advisories` in `cli.py`.** Add the option:

```python
    include_deferred: Annotated[
        bool,
        typer.Option(
            "--include-deferred",
            help="Include deferred findings in output (marked [deferred]).",
        ),
    ] = False,
```

Inside the function, after `result = compute_advisories(...)`, apply overrides:

```python
    paths = NexusPaths.from_env()
    registry = InstanceRegistry(paths.instances_dir)
    profile = instance if instance else _default_profile()
    overrides_set = registry.load_advisory_overrides(profile)
    remaining_set, deferred = apply_overrides(result, overrides_set)
    deferred_count = len(deferred)
    findings = remaining_set.findings
    if include_deferred:
        # Re-merge with [deferred] marker; preserve original sort.
        marked_deferred = tuple(
            f.model_copy(update={"summary": f"[deferred] {f.summary}"})
            for f in deferred
        )
        findings = tuple(
            sorted(
                (*findings, *marked_deferred),
                key=lambda f: (_SEV_ORDER[f.severity], f.plugin_id),
            )
        )
```

(`_SEV_ORDER` is imported from `nexus.plugins.advisories`.)

Then continue with the existing `--type` / `--severity` filters. Modify
the summary print to include the deferred count:

```python
    summary = _render_advisory_summary(findings, deferred_count=deferred_count)
```

Update `_render_advisory_summary` to accept the count and append `; N deferred`
when nonzero.

- [ ] **Step 3: Run tests + commit.**

---

## Task 7: Coverage ratchet bump

**Files:**
- Modify: `.ratchet.json`

- [ ] **Step 1: Run focused coverage:**

```
.venv/Scripts/pytest -q --cov=nexus.plugins.overrides --cov=nexus.plugins.errors --cov=nexus.instances.registry --cov=nexus.plugins.__init__ --cov-report=json --cov-fail-under=0 --ignore=tests/test_updater_runner.py
```

- [ ] **Step 2: Read new covered_lines from coverage.json** and update `.ratchet.json` for:
  - `nexus.plugins.overrides` (new module)
  - `nexus.plugins.errors` (new error class)
  - `nexus.plugins.__init__` (new re-exports)
  - `nexus.instances.registry` (two new methods)

- [ ] **Step 3: Run `pre-commit run --all-files`.** Fix any black/ruff/mypy/pyright/semgrep/pytest issues until all hooks pass.

- [ ] **Step 4: Commit.**

```bash
git add .ratchet.json
git commit -m "$(cat <<'EOF'
chore(ratchet): bump coverage baselines after sub-project K

Per-module covered_lines updated for nexus.plugins.overrides (new),
nexus.plugins.errors, nexus.plugins.__init__, and
nexus.instances.registry after the advisory-overrides feature landed.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

**Spec coverage:**
- AdvisoryOverride + AdvisoryOverrideSet -> Task 1
- apply_overrides pure function -> Task 1
- AdvisoryOverrideError -> Task 1
- Per-profile YAML persistence -> Task 2
- `defer` / `undo-defer` / `list-deferred` -> Tasks 3, 4, 5
- `--include-deferred` flag + deferred count in summary -> Task 6
- Ratchet bump -> Task 7

**Type consistency:** `AdvisoryOverride.advisory_type: AdvisoryType` (enum, not str). `apply_overrides -> tuple[AdvisorySet, tuple[AdvisoryFinding, ...]]`. Match key triple is `tuple[str, str, str]`.

**No placeholders:** every step has runnable code or commands.
