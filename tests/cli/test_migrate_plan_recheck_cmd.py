# tests/cli/test_migrate_plan_recheck_cmd.py
# Tests for `nexus migrate plan --recheck` (story 06c).
# Author: Pierre Grothe
# Date: 2026-07-02

"""End-to-end CliRunner tests for `nexus migrate plan --recheck`.

Monkeypatches ``commands_migrate.default_recheck_collaborators`` with a
fixture-driven ``RecheckCollaborators`` (same pattern as
``test_migrate_plan_cmd.py``'s ``default_plan_collaborators`` monkeypatching)
so no live ServiceNow call is ever made -- the production wiring itself is
``# pragma: no cover``.
"""

from pathlib import Path

import pytest
from click.testing import Result
from typer.testing import CliRunner

from nexus.cli import commands_migrate
from nexus.cli.apps import app
from nexus.cli.migrate_wiring import RecheckCollaborators
from nexus.connectors.servicenow.errors import SNClientError
from nexus.migrate.models import BaselineEntry, emit_plan_yaml
from tests.fakes.migrate import make_baseline_entry, make_migration_plan

_KEY_A = "x_acme_app|sys_script_include|helper a"
_KEY_B = "x_acme_app|sys_script_include|helper b"
_FP1 = "2026-07-01 10:00:00"
_FP2 = "2026-07-02 10:00:00"


def _write_plan(
    path: Path,
    *,
    source_baseline: tuple[BaselineEntry, ...] = (),
    target_baseline: tuple[BaselineEntry, ...] = (),
) -> bytes:
    plan = make_migration_plan(source_baseline=source_baseline, target_baseline=target_baseline)
    data = emit_plan_yaml(plan).encode("utf-8")
    path.write_bytes(data)
    return data


def _set_recheck_collaborators(
    monkeypatch: pytest.MonkeyPatch,
    *,
    source_entries: tuple[BaselineEntry, ...],
    target_entries: tuple[BaselineEntry, ...],
) -> None:
    def fake_factory() -> RecheckCollaborators:
        return RecheckCollaborators(
            build_listings=lambda _source, _target: (source_entries, target_entries)
        )

    monkeypatch.setattr(commands_migrate, "default_recheck_collaborators", fake_factory)


def _invoke_recheck(plan_path: Path, out_path: Path | None = None) -> Result:
    args = ["migrate", "plan", "--recheck", "--plan", str(plan_path)]
    if out_path is not None:
        args.extend(["--out", str(out_path)])
    return CliRunner().invoke(app, args)


# -- AC1: no-drift case --------------------------------------------------------


def test_migrate_plan_recheck_no_drift_exits_0_and_reports_no_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = (make_baseline_entry(key=_KEY_A, fingerprint=_FP1),)
    plan_path = tmp_path / "runbook.plan.yaml"
    _write_plan(plan_path, source_baseline=baseline, target_baseline=baseline)
    _set_recheck_collaborators(monkeypatch, source_entries=baseline, target_entries=baseline)

    result = _invoke_recheck(plan_path)

    assert result.exit_code == 0
    assert "no drift detected" in result.output


def test_migrate_plan_recheck_no_drift_leaves_runbook_bytes_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = (make_baseline_entry(key=_KEY_A, fingerprint=_FP1),)
    plan_path = tmp_path / "runbook.plan.yaml"
    _write_plan(plan_path, source_baseline=baseline, target_baseline=baseline)
    _set_recheck_collaborators(monkeypatch, source_entries=baseline, target_entries=baseline)
    runbook_path = tmp_path / "runbook.md"
    original_runbook = b"# Migration Runbook: alectri -> retail\n\npre-existing content\n"
    runbook_path.write_bytes(original_runbook)

    result = _invoke_recheck(plan_path)

    assert result.exit_code == 0
    assert runbook_path.read_bytes() == original_runbook


# -- AC2/AC4: drift-detected case ----------------------------------------------


def test_migrate_plan_recheck_drift_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_baseline = (make_baseline_entry(key=_KEY_A, fingerprint=_FP1),)
    plan_path = tmp_path / "runbook.plan.yaml"
    _write_plan(plan_path, source_baseline=source_baseline, target_baseline=())
    (tmp_path / "runbook.md").write_bytes(b"# Migration Runbook: alectri -> retail\n")
    fresh_source = (
        make_baseline_entry(key=_KEY_A, fingerprint=_FP1),
        make_baseline_entry(key=_KEY_B, fingerprint=_FP1),
    )
    _set_recheck_collaborators(monkeypatch, source_entries=fresh_source, target_entries=())

    result = _invoke_recheck(plan_path)

    assert result.exit_code == 2


def test_migrate_plan_recheck_drift_reports_grouped_by_instance_and_kind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_baseline = (
        make_baseline_entry(key=_KEY_A, fingerprint=_FP1),
        make_baseline_entry(key=_KEY_B, fingerprint=_FP1),
    )
    plan_path = tmp_path / "runbook.plan.yaml"
    _write_plan(plan_path, source_baseline=source_baseline, target_baseline=())
    (tmp_path / "runbook.md").write_bytes(b"# Migration Runbook: alectri -> retail\n")
    # KEY_A removed, KEY_B fingerprint changed -- source_removed + source_changed.
    fresh_source = (make_baseline_entry(key=_KEY_B, fingerprint=_FP2),)
    _set_recheck_collaborators(monkeypatch, source_entries=fresh_source, target_entries=())

    result = _invoke_recheck(plan_path)

    assert "source removed (1):" in result.output
    assert f"  {_KEY_A}" in result.output
    assert "source changed (1):" in result.output
    assert f"  {_KEY_B}" in result.output


def test_migrate_plan_recheck_drift_rewrites_runbook_with_stale_banner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_baseline = (make_baseline_entry(key=_KEY_A, fingerprint=_FP1),)
    plan_path = tmp_path / "runbook.plan.yaml"
    _write_plan(plan_path, source_baseline=source_baseline, target_baseline=())
    runbook_path = tmp_path / "runbook.md"
    runbook_path.write_bytes(b"# Migration Runbook: alectri -> retail\n\npre-existing content\n")
    _set_recheck_collaborators(monkeypatch, source_entries=(), target_entries=())

    result = _invoke_recheck(plan_path)

    assert result.exit_code == 2
    assert runbook_path.exists()
    text = runbook_path.read_text(encoding="utf-8")
    assert "STALE" in text
    assert "source removed: 1" in text


def test_migrate_plan_recheck_drift_leaves_plan_yaml_bytes_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_baseline = (make_baseline_entry(key=_KEY_A, fingerprint=_FP1),)
    plan_path = tmp_path / "runbook.plan.yaml"
    original_plan_bytes = _write_plan(
        plan_path, source_baseline=source_baseline, target_baseline=()
    )
    (tmp_path / "runbook.md").write_bytes(b"# Migration Runbook: alectri -> retail\n")
    _set_recheck_collaborators(monkeypatch, source_entries=(), target_entries=())

    result = _invoke_recheck(plan_path)

    assert result.exit_code == 2
    assert plan_path.read_bytes() == original_plan_bytes


# -- AC3: hard-error paths ------------------------------------------------------


def test_migrate_plan_recheck_without_plan_option_exits_1() -> None:
    result = CliRunner().invoke(app, ["migrate", "plan", "--recheck"])

    assert result.exit_code == 1
    assert "--recheck requires --plan" in result.stderr


def test_migrate_plan_recheck_unreadable_plan_exits_1(tmp_path: Path) -> None:
    missing = tmp_path / "absent.plan.yaml"

    result = _invoke_recheck(missing)

    assert result.exit_code == 1
    assert "cannot read plan" in result.stderr


def test_migrate_plan_recheck_malformed_plan_yaml_exits_1(tmp_path: Path) -> None:
    plan_path = tmp_path / "runbook.plan.yaml"
    plan_path.write_text("- a\n- b\n", encoding="utf-8")

    result = _invoke_recheck(plan_path)

    assert result.exit_code == 1
    assert "not valid YAML" in result.stderr


def test_migrate_plan_recheck_plan_failing_validation_exits_1(tmp_path: Path) -> None:
    plan_path = tmp_path / "runbook.plan.yaml"
    plan_path.write_text("not_a_plan: true\n", encoding="utf-8")

    result = _invoke_recheck(plan_path)

    assert result.exit_code == 1
    assert "failed validation" in result.stderr


def test_migrate_plan_recheck_plan_without_baseline_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan_path = tmp_path / "runbook.plan.yaml"
    _write_plan(plan_path, source_baseline=(), target_baseline=())
    _set_recheck_collaborators(monkeypatch, source_entries=(), target_entries=())

    result = _invoke_recheck(plan_path)

    assert result.exit_code == 1
    assert "no recheck baseline" in result.stderr


def test_migrate_plan_recheck_collaborator_listing_failure_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_baseline = (make_baseline_entry(key=_KEY_A, fingerprint=_FP1),)
    plan_path = tmp_path / "runbook.plan.yaml"
    _write_plan(plan_path, source_baseline=source_baseline, target_baseline=())

    def fake_factory() -> RecheckCollaborators:
        def _raise(
            _source: str, _target: str
        ) -> tuple[tuple[BaselineEntry, ...], tuple[BaselineEntry, ...]]:
            raise SNClientError("instance unreachable", status_code=503)

        return RecheckCollaborators(build_listings=_raise)

    monkeypatch.setattr(commands_migrate, "default_recheck_collaborators", fake_factory)

    result = _invoke_recheck(plan_path)

    assert result.exit_code == 1
    assert "failed to re-inventory instances for recheck" in result.stderr


def test_migrate_plan_recheck_non_plan_yaml_suffix_without_out_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_baseline = (make_baseline_entry(key=_KEY_A, fingerprint=_FP1),)
    plan_path = tmp_path / "myplan.yaml"
    _write_plan(plan_path, source_baseline=source_baseline, target_baseline=())
    _set_recheck_collaborators(monkeypatch, source_entries=(), target_entries=())

    result = _invoke_recheck(plan_path)

    assert result.exit_code == 1
    assert "does not end in .plan.yaml" in result.stderr


def test_migrate_plan_recheck_missing_derived_runbook_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Finding 1b: no --out given, and the derived runbook.md was never
    # created (or lives elsewhere) -- rechecking must never write a STALE
    # runbook to a path that was never the plan's own runbook.
    source_baseline = (make_baseline_entry(key=_KEY_A, fingerprint=_FP1),)
    plan_path = tmp_path / "runbook.plan.yaml"
    _write_plan(plan_path, source_baseline=source_baseline, target_baseline=())
    _set_recheck_collaborators(monkeypatch, source_entries=(), target_entries=())

    result = _invoke_recheck(plan_path)

    assert result.exit_code == 1
    assert "derived runbook path" in result.stderr
    assert "runbook.md" in result.stderr
    assert "does not exist" in result.stderr
    assert "pass --out" in result.stderr
    assert not (tmp_path / "runbook.md").exists()


def test_migrate_plan_recheck_non_plan_yaml_suffix_with_out_override_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_baseline = (make_baseline_entry(key=_KEY_A, fingerprint=_FP1),)
    plan_path = tmp_path / "myplan.yaml"
    _write_plan(plan_path, source_baseline=source_baseline, target_baseline=())
    _set_recheck_collaborators(monkeypatch, source_entries=(), target_entries=())
    out_path = tmp_path / "custom_runbook.md"

    result = _invoke_recheck(plan_path, out_path=out_path)

    assert result.exit_code == 2
    assert out_path.exists()
    assert "STALE" in out_path.read_text(encoding="utf-8")
