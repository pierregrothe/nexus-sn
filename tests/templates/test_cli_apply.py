# tests/templates/test_cli_apply.py
# Tests for the `nexus apply` CLI orchestrator.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Story 06 AC1-AC14: nexus apply dispatch + verdict-to-exit mapping."""

from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

from rich.console import Console

from nexus.assessment.context import GateContext
from nexus.assessment.report import GateReport
from nexus.assessment.schemas.constraints import FieldEqualsConstraint
from nexus.assessment.schemas.enums import Logic, Phase, Severity
from nexus.assessment.schemas.rule import AssessmentRule
from nexus.assessment.schemas.ruleset import Ruleset
from nexus.assessment.schemas.scope import TableScope
from nexus.capture.models import CaptureResult
from nexus.cli.commands_apply import ApplyCollaborators, run_apply
from nexus.config.paths import NexusPaths
from nexus.templates.apply import ApplyEngine
from nexus.ui.capabilities import (
    ColorDepth,
    RenderProfile,
    TerminalCapabilities,
)
from nexus.ui.render_context import RenderContext
from nexus.ui.theme import NEXUS_THEME
from tests.fakes.captures import make_capture_result, make_config_record
from tests.fakes.fake_sn_client import FakeServiceNowClient

_NOW = datetime(2026, 5, 19, 12, 0, tzinfo=UTC)


def _clock() -> datetime:
    return _NOW


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


def _seed_template(tmp_path: Path, template_id: str) -> Path:
    template_dir = tmp_path / "templates" / template_id
    template_dir.mkdir(parents=True, exist_ok=True)
    (template_dir / "template.yaml").write_text(
        f"""
kind: now_assist_skill
id: {template_id}
version: "1.0.0"
target_scope: global
name: Sample Skill
description: ""
instructions: Do the thing.
active: true
""",
        encoding="utf-8",
    )
    return template_dir / "template.yaml"


def _capture_with_scope_record() -> CaptureResult:
    return make_capture_result(
        records=(make_config_record(table="sys_scope", fields={"active": "true"}),)
    )


def _engine(tmp_path: Path) -> ApplyEngine:
    return ApplyEngine(
        sn_client=FakeServiceNowClient(),
        paths=NexusPaths(root=tmp_path),
        clock=_clock,
        instance_id="dev",
        nexus_version="0.0.test",
        git_sha="abc123",
    )


def _block_rule() -> AssessmentRule:
    return AssessmentRule(
        id="warn-rule",
        description="must be active",
        severity=Severity.WARNING,
        phase=Phase.PRE_APPLY,
        scope=TableScope(table="sys_scope"),
        required_tables=("sys_scope",),
        logic=Logic.AND_ALL,
        constraints=(FieldEqualsConstraint(table="sys_scope", field="active", expected="never"),),
    )


def _ruleset(*, template_id: str, rules: tuple[AssessmentRule, ...]) -> Ruleset:
    return Ruleset(
        id=f"rs-{template_id}",
        version="1.0.0",
        description="apply-test ruleset",
        applies_to=(template_id,),
        rules=rules,
    )


def _collaborators(
    *,
    rulesets: tuple[Ruleset, ...] = (),
    capture: CaptureResult | None = None,
    engine: ApplyEngine | None = None,
    capture_raises: bool = False,
) -> ApplyCollaborators:
    capture_obj = capture if capture is not None else _capture_with_scope_record()

    def _rs_loader(_path: Path) -> tuple[Ruleset, ...]:
        return rulesets

    def _capture_runner(_scope: str | None) -> CaptureResult:
        if capture_raises:
            raise NotImplementedError("test wiring disabled capture")
        return capture_obj

    def _factory() -> ApplyEngine:
        if engine is None:
            raise NotImplementedError("test wiring did not provide an engine")
        return engine

    return ApplyCollaborators(
        rulesets_loader=_rs_loader,
        capture_runner=_capture_runner,
        apply_engine_factory=_factory,
    )


def test_run_apply_happy_path_returns_zero(tmp_path: Path) -> None:
    _seed_template(tmp_path, "sample-skill")
    paths = NexusPaths(root=tmp_path)
    rc = _render_context()
    code = run_apply(
        template_id="sample-skill",
        scope_override="",
        force=False,
        skip_gate2=False,
        render_context=rc,
        paths=paths,
        collaborators=_collaborators(engine=_engine(tmp_path)),
    )
    assert code == 0


def test_run_apply_template_not_found_exits_one(tmp_path: Path) -> None:
    paths = NexusPaths(root=tmp_path)
    rc = _render_context()
    code = run_apply(
        template_id="does-not-exist",
        scope_override="",
        force=False,
        skip_gate2=False,
        render_context=rc,
        paths=paths,
        collaborators=_collaborators(engine=_engine(tmp_path)),
    )
    assert code == 1
    assert "not found" in rc.console.export_text()


def test_run_apply_gate1_block_without_force_exits_two(tmp_path: Path) -> None:
    _seed_template(tmp_path, "sample-skill")
    paths = NexusPaths(root=tmp_path)
    rc = _render_context()
    code = run_apply(
        template_id="sample-skill",
        scope_override="",
        force=False,
        skip_gate2=False,
        render_context=rc,
        paths=paths,
        collaborators=_collaborators(
            rulesets=(_ruleset(template_id="sample-skill", rules=(_block_rule(),)),),
            engine=_engine(tmp_path),
        ),
    )
    assert code == 2


def test_run_apply_gate1_block_with_force_proceeds_to_apply(tmp_path: Path) -> None:
    _seed_template(tmp_path, "sample-skill")
    paths = NexusPaths(root=tmp_path)
    rc = _render_context()
    code = run_apply(
        template_id="sample-skill",
        scope_override="",
        force=True,
        skip_gate2=True,
        render_context=rc,
        paths=paths,
        collaborators=_collaborators(
            rulesets=(_ruleset(template_id="sample-skill", rules=(_block_rule(),)),),
            engine=_engine(tmp_path),
        ),
    )
    assert code == 0
    assert "Gate 2 skipped" in rc.console.export_text()


def test_run_apply_capture_failure_exits_one(tmp_path: Path) -> None:
    _seed_template(tmp_path, "sample-skill")
    paths = NexusPaths(root=tmp_path)
    rc = _render_context()
    code = run_apply(
        template_id="sample-skill",
        scope_override="",
        force=False,
        skip_gate2=False,
        render_context=rc,
        paths=paths,
        collaborators=_collaborators(engine=_engine(tmp_path), capture_raises=True),
    )
    assert code == 1
    assert "live capture" in rc.console.export_text().lower()


def test_run_apply_skip_gate2_exits_zero(tmp_path: Path) -> None:
    _seed_template(tmp_path, "sample-skill")
    paths = NexusPaths(root=tmp_path)
    rc = _render_context()
    code = run_apply(
        template_id="sample-skill",
        scope_override="",
        force=False,
        skip_gate2=True,
        render_context=rc,
        paths=paths,
        collaborators=_collaborators(engine=_engine(tmp_path)),
    )
    assert code == 0


def test_run_apply_scope_override_passed_to_capture(tmp_path: Path) -> None:
    _seed_template(tmp_path, "sample-skill")
    paths = NexusPaths(root=tmp_path)
    rc = _render_context()
    seen_scopes: list[str | None] = []

    def _capture_runner(scope: str | None) -> CaptureResult:
        seen_scopes.append(scope)
        return _capture_with_scope_record()

    collaborators = ApplyCollaborators(
        rulesets_loader=lambda _p: (),
        capture_runner=_capture_runner,
        apply_engine_factory=lambda: _engine(tmp_path),
    )
    code = run_apply(
        template_id="sample-skill",
        scope_override="x_my_app",
        force=False,
        skip_gate2=False,
        render_context=rc,
        paths=paths,
        collaborators=collaborators,
    )
    assert code == 0
    assert seen_scopes[0] == "x_my_app"


def test_run_apply_engine_factory_not_implemented_exits_one(tmp_path: Path) -> None:
    _seed_template(tmp_path, "sample-skill")
    paths = NexusPaths(root=tmp_path)
    rc = _render_context()
    code = run_apply(
        template_id="sample-skill",
        scope_override="",
        force=False,
        skip_gate2=False,
        render_context=rc,
        paths=paths,
        collaborators=_collaborators(engine=None),
    )
    assert code == 1


def test_run_apply_gate2_with_empty_ruleset_passes(tmp_path: Path) -> None:
    """No POST_APPLY rules -> placeholder rule -> PASS."""
    _seed_template(tmp_path, "sample-skill")
    paths = NexusPaths(root=tmp_path)
    rc = _render_context()
    code = run_apply(
        template_id="sample-skill",
        scope_override="",
        force=False,
        skip_gate2=False,
        render_context=rc,
        paths=paths,
        collaborators=_collaborators(engine=_engine(tmp_path)),
    )
    assert code == 0


def test_run_apply_detects_target_scope_from_template_file(tmp_path: Path) -> None:
    # Template declares target_scope: x_custom
    template_dir = tmp_path / "templates" / "scoped"
    template_dir.mkdir(parents=True)
    (template_dir / "template.yaml").write_text(
        """
kind: now_assist_skill
id: scoped
version: "1.0.0"
target_scope: x_custom
name: Scoped Skill
description: ""
instructions: Do x_custom things.
active: true
""",
        encoding="utf-8",
    )
    paths = NexusPaths(root=tmp_path)
    rc = _render_context()
    seen_scopes: list[str | None] = []

    def _capture_runner(scope: str | None) -> CaptureResult:
        seen_scopes.append(scope)
        return _capture_with_scope_record()

    # ApplyEngine needs to resolve x_custom in sys_scope
    sn_client = FakeServiceNowClient(
        initial_records={"sys_scope": [{"sys_id": "scope-xyz", "scope": "x_custom"}]}
    )
    engine = ApplyEngine(
        sn_client=sn_client,
        paths=paths,
        clock=_clock,
        instance_id="dev",
        nexus_version="0.0.test",
        git_sha="abc",
    )
    collaborators = ApplyCollaborators(
        rulesets_loader=lambda _p: (),
        capture_runner=_capture_runner,
        apply_engine_factory=lambda: engine,
    )
    code = run_apply(
        template_id="scoped",
        scope_override="",
        force=False,
        skip_gate2=False,
        render_context=rc,
        paths=paths,
        collaborators=collaborators,
    )
    assert code == 0
    assert seen_scopes[0] == "x_custom"


def test_run_apply_unreadable_template_falls_back_to_global_scope(
    tmp_path: Path,
) -> None:
    template_dir = tmp_path / "templates" / "broken"
    template_dir.mkdir(parents=True)
    # write broken yaml so _detect_target_scope falls back to "global"
    (template_dir / "template.yaml").write_text(
        "kind: now_assist_skill\n: bad\n[unclosed", encoding="utf-8"
    )
    paths = NexusPaths(root=tmp_path)
    rc = _render_context()
    seen_scopes: list[str | None] = []

    def _capture_runner(scope: str | None) -> CaptureResult:
        seen_scopes.append(scope)
        return _capture_with_scope_record()

    collaborators = ApplyCollaborators(
        rulesets_loader=lambda _p: (),
        capture_runner=_capture_runner,
        apply_engine_factory=lambda: _engine(tmp_path),
    )
    code = run_apply(
        template_id="broken",
        scope_override="",
        force=False,
        skip_gate2=False,
        render_context=rc,
        paths=paths,
        collaborators=collaborators,
    )
    # _detect_target_scope returns "global"; ApplyEngine then fails parsing
    # the broken YAML and surfaces via TemplateLoadError -> exit 1
    assert seen_scopes[0] == "global"
    assert code == 1
    # GateContext etc. work but ApplyEngine fails template load:
    assert "template load failed" in rc.console.export_text().lower()


# These three keep the GateContext import live for test wiring readers.
def test_gate_context_is_constructible_via_test_helpers() -> None:
    ctx = GateContext(
        capture=_capture_with_scope_record(), apply_result=None, phase=Phase.PRE_APPLY
    )
    assert ctx.phase is Phase.PRE_APPLY


def test_gate_report_from_findings_factory_passes_through() -> None:
    report = GateReport.from_findings(
        (),
        rules_evaluated=0,
        ruleset_id="rs",
        template_id="t",
        phase=Phase.PRE_APPLY,
    )
    assert report.verdict.value == "PASS"
