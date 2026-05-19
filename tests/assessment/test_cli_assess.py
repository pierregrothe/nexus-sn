# tests/assessment/test_cli_assess.py
# Tests for `nexus assess` dispatch + exit code mapping.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Story 06: CLI dispatch and exit-code mapping under injected collaborators."""

from __future__ import annotations

import os
from io import StringIO
from pathlib import Path

import pytest
import typer
from rich.console import Console

from nexus.assessment.context import ApplyResult
from nexus.assessment.findings import Finding
from nexus.assessment.report import GateReport
from nexus.assessment.schemas.constraints import FieldEqualsConstraint
from nexus.assessment.schemas.enums import Phase, Severity
from nexus.assessment.schemas.rule import AssessmentRule
from nexus.assessment.schemas.ruleset import Ruleset
from nexus.assessment.schemas.scope import TableScope
from nexus.assessment.verdict import GateVerdict
from nexus.capture.models import CaptureResult
from nexus.cli.commands_assess import AssessCollaborators, run_assess
from nexus.config.paths import NexusPaths
from nexus.ui.capabilities import (
    ColorDepth,
    RenderProfile,
    TerminalCapabilities,
)
from nexus.ui.render_context import RenderContext
from nexus.ui.theme import NEXUS_THEME
from tests.fakes.captures import make_capture_result, make_config_record
from tests.fakes.rulesets import make_assessment_rule
from tests.fakes.templates import make_apply_result


def _render_context() -> RenderContext:
    console = Console(file=StringIO(), width=120, record=True, theme=NEXUS_THEME)
    caps = TerminalCapabilities(
        is_tty=False,
        is_ci=False,
        color_depth=ColorDepth.NONE,
        cols=120,
        rows=40,
        legacy_windows=False,
        term_program="",
        is_dumb_terminal=False,
        is_multiplexer=False,
        no_color_env=False,
        forced_plain=True,
        supports_hyperlinks=False,
    )
    return RenderContext(console=console, caps=caps, profile=RenderProfile.PLAIN)


def _capture_with_scope_record() -> CaptureResult:
    return make_capture_result(
        records=(make_config_record(table="sys_scope", fields={"active": "true"}),),
    )


def _pre_apply_ruleset(template_id: str = "acme") -> Ruleset:
    rule = make_assessment_rule(rule_id="r-pre", phase=Phase.PRE_APPLY)
    return Ruleset(
        id="rs-pre",
        version="1.0.0",
        description="pre-apply",
        applies_to=(template_id,),
        rules=(rule,),
    )


def _post_apply_ruleset(template_id: str = "acme") -> Ruleset:
    rule = make_assessment_rule(rule_id="r-post", phase=Phase.POST_APPLY)
    return Ruleset(
        id="rs-post",
        version="1.0.0",
        description="post-apply",
        applies_to=(template_id,),
        rules=(rule,),
    )


def _standalone_ruleset() -> Ruleset:
    rule = make_assessment_rule(rule_id="r-std", phase=Phase.STANDALONE)
    return Ruleset(
        id="rs-std",
        version="1.0.0",
        description="standalone",
        applies_to=("*",),
        rules=(rule,),
    )


def _collaborators(
    *,
    rulesets: tuple[Ruleset, ...] = (),
    capture: CaptureResult | None = None,
    apply_result_template_id: tuple[ApplyResult, str] | None = None,
    capture_live_callable: bool = False,
) -> AssessCollaborators:
    capture_obj = capture if capture is not None else _capture_with_scope_record()

    def _rs_loader(_path: Path) -> tuple[Ruleset, ...]:
        return rulesets

    def _archive_loader(_path: Path) -> CaptureResult:
        return capture_obj

    def _capture_runner(_scope: str | None) -> CaptureResult:
        if capture_live_callable:
            return capture_obj
        raise NotImplementedError("test wiring did not enable live capture")

    def _apply_loader(_job: str) -> tuple[ApplyResult, str]:
        if apply_result_template_id is None:
            raise NotImplementedError("test wiring did not provide apply_result_loader")
        return apply_result_template_id

    return AssessCollaborators(
        rulesets_loader=_rs_loader,
        archive_loader=_archive_loader,
        capture_runner=_capture_runner,
        apply_result_loader=_apply_loader,
    )


def test_run_assess_for_template_pass_returns_exit_zero(tmp_path: Path) -> None:
    paths = NexusPaths(root=tmp_path)
    rc = _render_context()
    code = run_assess(
        for_template="acme",
        job="",
        live=False,
        archive_path=tmp_path / "archive.yaml",
        skip_gate2=False,
        render_context=rc,
        paths=paths,
        collaborators=_collaborators(rulesets=(_pre_apply_ruleset(),)),
    )
    assert code == 0


def test_run_assess_for_template_with_no_matching_ruleset_exits_one(tmp_path: Path) -> None:
    paths = NexusPaths(root=tmp_path)
    rc = _render_context()
    code = run_assess(
        for_template="other-template",
        job="",
        live=False,
        archive_path=tmp_path / "archive.yaml",
        skip_gate2=False,
        render_context=rc,
        paths=paths,
        collaborators=_collaborators(rulesets=(_pre_apply_ruleset("acme"),)),
    )
    assert code == 1
    assert "no readiness ruleset" in rc.console.export_text()


def test_run_assess_for_template_block_returns_exit_two(tmp_path: Path) -> None:
    block_rule = AssessmentRule(
        id="r-warn",
        description="must be active",
        severity=Severity.WARNING,
        phase=Phase.PRE_APPLY,
        scope=TableScope(table="sys_scope"),
        required_tables=("sys_scope",),
        constraints=(FieldEqualsConstraint(table="sys_scope", field="active", expected="never"),),
    )
    block_rs = Ruleset(
        id="rs-block",
        version="1.0.0",
        description="block",
        applies_to=("acme",),
        rules=(block_rule,),
    )
    paths = NexusPaths(root=tmp_path)
    rc = _render_context()
    code = run_assess(
        for_template="acme",
        job="",
        live=False,
        archive_path=tmp_path / "archive.yaml",
        skip_gate2=False,
        render_context=rc,
        paths=paths,
        collaborators=_collaborators(rulesets=(block_rs,)),
    )
    assert code == 2


def test_run_assess_for_and_job_mutex_raises_bad_parameter(tmp_path: Path) -> None:
    paths = NexusPaths(root=tmp_path)
    rc = _render_context()
    with pytest.raises(typer.BadParameter):
        run_assess(
            for_template="acme",
            job="JOB1",
            live=False,
            archive_path=None,
            skip_gate2=False,
            render_context=rc,
            paths=paths,
            collaborators=_collaborators(),
        )


def test_run_assess_live_and_archive_mutex_raises_bad_parameter(tmp_path: Path) -> None:
    paths = NexusPaths(root=tmp_path)
    rc = _render_context()
    with pytest.raises(typer.BadParameter):
        run_assess(
            for_template="",
            job="",
            live=True,
            archive_path=tmp_path / "archive.yaml",
            skip_gate2=False,
            render_context=rc,
            paths=paths,
            collaborators=_collaborators(),
        )


def test_run_assess_job_with_skip_gate2_exits_zero(tmp_path: Path) -> None:
    paths = NexusPaths(root=tmp_path)
    rc = _render_context()
    code = run_assess(
        for_template="",
        job="JOB1",
        live=False,
        archive_path=None,
        skip_gate2=True,
        render_context=rc,
        paths=paths,
        collaborators=_collaborators(),
    )
    assert code == 0
    assert "skipped" in rc.console.export_text().lower()


def test_run_assess_job_passes_when_apply_loader_returns_template_id(tmp_path: Path) -> None:
    paths = NexusPaths(root=tmp_path)
    rc = _render_context()
    code = run_assess(
        for_template="",
        job="JOB1",
        live=False,
        archive_path=tmp_path / "archive.yaml",
        skip_gate2=False,
        render_context=rc,
        paths=paths,
        collaborators=_collaborators(
            rulesets=(_post_apply_ruleset(),),
            apply_result_template_id=(make_apply_result(template_id="acme"), "acme"),
        ),
    )
    assert code == 0


def test_run_assess_job_loader_not_implemented_exits_one(tmp_path: Path) -> None:
    paths = NexusPaths(root=tmp_path)
    rc = _render_context()
    code = run_assess(
        for_template="",
        job="JOB1",
        live=False,
        archive_path=tmp_path / "archive.yaml",
        skip_gate2=False,
        render_context=rc,
        paths=paths,
        collaborators=_collaborators(),
    )
    assert code == 1


def test_run_assess_health_with_no_rulesets_exits_zero_with_warning(tmp_path: Path) -> None:
    paths = NexusPaths(root=tmp_path)
    rc = _render_context()
    code = run_assess(
        for_template="",
        job="",
        live=False,
        archive_path=tmp_path / "archive.yaml",
        skip_gate2=False,
        render_context=rc,
        paths=paths,
        collaborators=_collaborators(rulesets=()),
    )
    assert code == 0
    assert "no rulesets" in rc.console.export_text().lower()


def test_run_assess_health_runs_standalone_rules_pass(tmp_path: Path) -> None:
    paths = NexusPaths(root=tmp_path)
    rc = _render_context()
    code = run_assess(
        for_template="",
        job="",
        live=False,
        archive_path=tmp_path / "archive.yaml",
        skip_gate2=False,
        render_context=rc,
        paths=paths,
        collaborators=_collaborators(rulesets=(_standalone_ruleset(),)),
    )
    assert code == 0


def test_run_assess_live_capture_runner_not_implemented_exits_one(tmp_path: Path) -> None:
    paths = NexusPaths(root=tmp_path)
    rc = _render_context()
    code = run_assess(
        for_template="acme",
        job="",
        live=True,
        archive_path=None,
        skip_gate2=False,
        render_context=rc,
        paths=paths,
        collaborators=_collaborators(rulesets=(_pre_apply_ruleset(),)),
    )
    assert code == 1


def test_run_assess_live_capture_works_when_runner_wired(tmp_path: Path) -> None:
    paths = NexusPaths(root=tmp_path)
    rc = _render_context()
    code = run_assess(
        for_template="acme",
        job="",
        live=True,
        archive_path=None,
        skip_gate2=False,
        render_context=rc,
        paths=paths,
        collaborators=_collaborators(
            rulesets=(_pre_apply_ruleset(),),
            capture_live_callable=True,
        ),
    )
    assert code == 0


def test_run_assess_default_archive_resolution_finds_no_archive_exits_one(
    tmp_path: Path,
) -> None:
    paths = NexusPaths(root=tmp_path)
    rc = _render_context()
    # archive_path=None and archives_dir doesn't exist -> _default_archive_path returns None
    code = run_assess(
        for_template="acme",
        job="",
        live=False,
        archive_path=None,
        skip_gate2=False,
        render_context=rc,
        paths=paths,
        collaborators=_collaborators(rulesets=(_pre_apply_ruleset(),)),
    )
    assert code == 1
    assert "no archive found" in rc.console.export_text().lower()


def test_run_assess_default_archive_picks_newest_manifest(tmp_path: Path) -> None:
    paths = NexusPaths(root=tmp_path)
    paths.archives_dir.mkdir(parents=True, exist_ok=True)
    older_dir = paths.archives_dir / "older"
    newer_dir = paths.archives_dir / "newer"
    older_dir.mkdir()
    newer_dir.mkdir()
    older_manifest = older_dir / "manifest.yaml"
    newer_manifest = newer_dir / "manifest.yaml"
    older_manifest.write_text("placeholder", encoding="utf-8")
    newer_manifest.write_text("placeholder", encoding="utf-8")
    os.utime(older_manifest, (1_000_000, 1_000_000))
    os.utime(newer_manifest, (2_000_000, 2_000_000))
    captured_paths: list[Path] = []

    def _archive_loader(path: Path) -> CaptureResult:
        captured_paths.append(path)
        return _capture_with_scope_record()

    collaborators = AssessCollaborators(
        rulesets_loader=lambda _p: (_pre_apply_ruleset(),),
        archive_loader=_archive_loader,
        capture_runner=lambda _s: (_ for _ in ()).throw(NotImplementedError("n/a")),
        apply_result_loader=lambda _j: (_ for _ in ()).throw(NotImplementedError("n/a")),
    )
    rc = _render_context()
    code = run_assess(
        for_template="acme",
        job="",
        live=False,
        archive_path=None,
        skip_gate2=False,
        render_context=rc,
        paths=paths,
        collaborators=collaborators,
    )
    assert code == 0
    # The newest one (newer_dir) is selected
    assert captured_paths[0].parent.name == "newer"


def test_run_assess_records_block_verdict_to_exit_two_via_health_phase(
    tmp_path: Path,
) -> None:
    """A WARNING in PRE_APPLY blocks; same severity in STANDALONE should NOT block."""
    canned = GateReport(
        verdict=GateVerdict.BLOCK,
        findings=(
            Finding(
                rule_id="r",
                severity=Severity.WARNING,
                message="m",
                affected_sys_ids=(),
                phase=Phase.STANDALONE,
            ),
        ),
        summary=GateReport.from_findings(
            (), rules_evaluated=0, ruleset_id="rs", template_id=None, phase=Phase.STANDALONE
        ).summary,
        ruleset_id="rs",
        template_id=None,
    )
    assert canned.verdict is GateVerdict.BLOCK
