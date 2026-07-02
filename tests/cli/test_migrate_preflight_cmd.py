# tests/cli/test_migrate_preflight_cmd.py
# Tests for `nexus migrate preflight` (story 07b).
# Author: Pierre Grothe
# Date: 2026-07-02

"""End-to-end CliRunner tests for `nexus migrate preflight`.

Monkeypatches ``commands_migrate_preflight.default_preflight_collaborators``
with a fixture-driven ``PreflightCollaborators`` (same pattern
``test_migrate_plan_cmd.py`` uses for ``default_plan_collaborators``) so no
live ServiceNow call is ever made -- the production wiring itself is
``# pragma: no cover``.
"""

from collections.abc import Callable

import pytest
from click.testing import Result
from typer.testing import CliRunner

from nexus.cli import commands_migrate_preflight
from nexus.cli.apps import app
from nexus.cli.commands_migrate_preflight import PreflightCollaborators
from nexus.connectors.servicenow.errors import SNClientError
from nexus.migrate.models import PreflightItemResult, PreflightReport, PreflightStatus

__all__: list[str] = []


def _row(
    *, item: str, instance: str, status: PreflightStatus, detail: str = ""
) -> PreflightItemResult:
    return PreflightItemResult(
        item=item,
        instance=instance,
        status=status,
        purpose=f"purpose for {item}",
        remediation=f"remediation for {item}",
        detail=detail,
    )


def _mixed_report() -> PreflightReport:
    items = tuple(
        sorted(
            (
                _row(item="cicd-plugin", instance="old", status=PreflightStatus.PASS),
                # sn-cicd-role maps 403 -> UNKNOWN (AC1 override), so its only
                # reachable statuses are PASS/UNKNOWN; FAIL lives on app-repo.
                _row(
                    item="sn-cicd-role",
                    instance="old",
                    status=PreflightStatus.UNKNOWN,
                    detail="verify manually",
                ),
                _row(
                    item="app-repo-entitlement",
                    instance="old",
                    status=PreflightStatus.FAIL,
                    detail="needs admin",
                ),
                _row(item="auth-mode", instance="old", status=PreflightStatus.PASS, detail="oauth"),
                _row(item="cicd-plugin", instance="new", status=PreflightStatus.PASS),
                _row(item="sn-cicd-role", instance="new", status=PreflightStatus.PASS),
                _row(item="app-repo-entitlement", instance="new", status=PreflightStatus.PASS),
                _row(
                    item="auth-mode",
                    instance="new",
                    status=PreflightStatus.UNKNOWN,
                    detail="basic",
                ),
            ),
            key=lambda row: (row.instance, row.item),
        )
    )
    return PreflightReport(items=items)


def _all_pass_report() -> PreflightReport:
    items = tuple(
        sorted(
            (
                _row(item="cicd-plugin", instance="old", status=PreflightStatus.PASS),
                _row(item="sn-cicd-role", instance="old", status=PreflightStatus.PASS),
                _row(item="app-repo-entitlement", instance="old", status=PreflightStatus.PASS),
                _row(item="auth-mode", instance="old", status=PreflightStatus.PASS),
                _row(item="cicd-plugin", instance="new", status=PreflightStatus.PASS),
                _row(item="sn-cicd-role", instance="new", status=PreflightStatus.PASS),
                _row(item="app-repo-entitlement", instance="new", status=PreflightStatus.PASS),
                _row(item="auth-mode", instance="new", status=PreflightStatus.PASS),
            ),
            key=lambda row: (row.instance, row.item),
        )
    )
    return PreflightReport(items=items)


def _set_collaborators(
    monkeypatch: pytest.MonkeyPatch, run: Callable[[str, str], PreflightReport]
) -> None:
    # A wide COLUMNS keeps Rich from truncating/dropping table cells under
    # CliRunner's non-tty stdout (which otherwise falls back to an 80-col
    # default too narrow for this table's five columns).
    monkeypatch.setenv("COLUMNS", "220")

    def fake_factory() -> PreflightCollaborators:
        return PreflightCollaborators(run=run)

    monkeypatch.setattr(commands_migrate_preflight, "default_preflight_collaborators", fake_factory)


def _invoke(from_profile: str = "alectri", to_profile: str = "retail") -> Result:
    args = ["migrate", "preflight"]
    if from_profile:
        args += ["--from", from_profile]
    if to_profile:
        args += ["--to", to_profile]
    return CliRunner().invoke(app, args)


# -- AC3/AC4: rendered table mirrors diagnose-roles shape, grouped per instance --


def test_migrate_preflight_renders_both_instance_tables_and_exits_0(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEXUS_AUTO_UPDATE", "0")
    _set_collaborators(monkeypatch, lambda _from, _to: _mixed_report())

    result = _invoke(from_profile="alectri", to_profile="retail")

    assert result.exit_code == 0
    assert "Preflight -- alectri" in result.output
    assert "Preflight -- retail" in result.output
    assert "cicd-plugin" in result.output
    assert "sn-cicd-role" in result.output
    assert "app-repo-entitlement" in result.output
    assert "auth-mode" in result.output
    assert "PASS" in result.output
    assert "FAIL" in result.output
    assert "UNKNOWN" in result.output


def test_migrate_preflight_shows_purpose_and_remediation_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEXUS_AUTO_UPDATE", "0")
    _set_collaborators(monkeypatch, lambda _from, _to: _mixed_report())

    result = _invoke()

    assert "purpose for sn-cicd-role" in result.output
    assert "remediation for sn-cicd-role" in result.output
    assert "needs admin" in result.output


# -- AC8 resolution: exit 0 even with FAIL/UNKNOWN rows present ---------------


def test_migrate_preflight_happy_path_exits_0_with_fail_rows_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEXUS_AUTO_UPDATE", "0")
    _set_collaborators(monkeypatch, lambda _from, _to: _mixed_report())

    result = _invoke()

    assert result.exit_code == 0
    assert "not PASS" in result.output


def test_migrate_preflight_all_pass_prints_all_pass_notice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEXUS_AUTO_UPDATE", "0")
    _set_collaborators(monkeypatch, lambda _from, _to: _all_pass_report())

    result = _invoke()

    assert result.exit_code == 0
    assert "All preflight probes returned PASS." in result.output


# -- Missing --from/--to exit 1 with stderr message ---------------------------


def test_migrate_preflight_missing_from_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_AUTO_UPDATE", "0")
    _set_collaborators(monkeypatch, lambda _from, _to: _all_pass_report())

    result = _invoke(from_profile="", to_profile="retail")

    assert result.exit_code == 1
    assert "--from is required" in result.stderr


def test_migrate_preflight_missing_to_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_AUTO_UPDATE", "0")
    _set_collaborators(monkeypatch, lambda _from, _to: _all_pass_report())

    result = _invoke(from_profile="alectri", to_profile="")

    assert result.exit_code == 1
    assert "--to is required" in result.stderr


# -- Hard-error path (collaborator failure) exits 1 with stderr message ------


def test_migrate_preflight_collaborator_failure_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_AUTO_UPDATE", "0")

    def _raise(_from: str, _to: str) -> PreflightReport:
        raise SNClientError("boom", status_code=500)

    _set_collaborators(monkeypatch, _raise)

    result = _invoke()

    assert result.exit_code == 1
    assert "failed to probe instances for preflight" in result.stderr
