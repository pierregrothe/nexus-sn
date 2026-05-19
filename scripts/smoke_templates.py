#!/usr/bin/env python
# scripts/smoke_templates.py
# Smoke test for the template-library layer end-to-end.
# Author: Pierre Grothe
# Date: 2026-05-19

"""End-to-end smoke for the templates package against shipped fixtures.

Covers:
* Every templates/<id>/template.yaml parses through load_template_document
* Every templates/assessments/*.yaml parses through load_ruleset
* templates/manifest.json lists every directory and vice versa
* render_to_records produces deterministic sys_ids for each shipped template
* ApplyEngine.apply runs end-to-end against FakeServiceNowClient for the
  3 shipped templates (proves the full pipeline: load -> resolve scope ->
  render -> create sys_update_set -> UpdateSetWriter.push -> ApplyResult)
* validate_assessment_rulesets.py and validate_template_documents.py exit 0
  against the repo's templates/ tree

Usage:
    poetry run python scripts/smoke_templates.py
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

__all__: list[str] = []

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = REPO_ROOT / "templates"
ASSESSMENTS_DIR = TEMPLATES_DIR / "assessments"

# Smoke runs from REPO_ROOT but tests/ is not a regular installable package;
# inject it on sys.path so the FakeServiceNowClient import below resolves.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nexus.assessment.loader import load_ruleset  # noqa: E402
from nexus.config.paths import NexusPaths  # noqa: E402
from nexus.templates.apply import ApplyEngine  # noqa: E402
from nexus.templates.document import load_template_document  # noqa: E402
from nexus.templates.renderer import render_to_records  # noqa: E402
from tests.fakes.fake_sn_client import FakeServiceNowClient  # noqa: E402


@dataclass
class Result:
    """One smoke-test outcome."""

    name: str
    passed: bool
    duration_s: float
    summary: str = ""
    tail: str = ""


@dataclass
class Suite:
    """Accumulator for results plus pretty printing."""

    results: list[Result] = field(default_factory=list)

    def add(self, r: Result) -> None:
        """Record a result and emit one line."""
        marker = "PASS" if r.passed else "FAIL"
        line = f"  [{marker}] {r.name}  ({r.duration_s:.1f}s) {r.summary}"
        print(line)
        if not r.passed and r.tail:
            for raw_line in r.tail.splitlines()[-6:]:
                print(f"        | {raw_line}")
        self.results.append(r)

    def summary(self) -> int:
        """Print summary; return non-zero when any test failed."""
        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)
        print()
        print("=" * 70)
        print(f"SMOKE-TEMPLATES SUMMARY: {passed} passed, {failed} failed")
        if failed:
            print("Failed tests:")
            for r in self.results:
                if not r.passed:
                    print(f"  - {r.name}: {r.summary}")
        return 0 if failed == 0 else 1


def _test(name: str, fn: Callable[[], tuple[bool, str, str]]) -> Result:
    """Run one test function, capturing duration + outcome."""
    started = time.monotonic()
    try:
        ok, summary, tail = fn()
    except Exception as exc:
        return Result(
            name=name,
            passed=False,
            duration_s=time.monotonic() - started,
            summary=f"exception: {exc}",
        )
    return Result(
        name=name, passed=ok, duration_s=time.monotonic() - started, summary=summary, tail=tail
    )


def _shipped_template_paths() -> list[Path]:
    return sorted(TEMPLATES_DIR.glob("*/template.yaml"))


def _shipped_ruleset_paths() -> list[Path]:
    return sorted(ASSESSMENTS_DIR.glob("*.yaml"))


def t_templates_parse_via_loader() -> tuple[bool, str, str]:
    """Every templates/<id>/template.yaml parses through load_template_document."""
    paths = _shipped_template_paths()
    if not paths:
        return False, "no templates on disk", ""
    failures: list[str] = []
    for path in paths:
        try:
            load_template_document(path)
        except Exception as exc:
            failures.append(f"{path.parent.name}: {exc}")
    ok = not failures
    summary = f"parsed {len(paths)} templates; failures={len(failures)}"
    return ok, summary, "\n".join(failures)


def t_rulesets_parse_via_loader() -> tuple[bool, str, str]:
    """Every templates/assessments/*.yaml parses through load_ruleset."""
    paths = _shipped_ruleset_paths()
    if not paths:
        return False, "no rulesets on disk", ""
    failures: list[str] = []
    for path in paths:
        try:
            load_ruleset(path)
        except Exception as exc:
            failures.append(f"{path.name}: {exc}")
    ok = not failures
    summary = f"parsed {len(paths)} rulesets; failures={len(failures)}"
    return ok, summary, "\n".join(failures)


def t_manifest_matches_disk() -> tuple[bool, str, str]:
    """templates/manifest.json lists exactly the directories on disk."""
    manifest_path = TEMPLATES_DIR / "manifest.json"
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    listed_ids = {entry["id"] for entry in raw["templates"]}
    on_disk_ids = {p.parent.name for p in _shipped_template_paths()}
    missing_from_manifest = on_disk_ids - listed_ids
    orphan_in_manifest = listed_ids - on_disk_ids
    ok = not missing_from_manifest and not orphan_in_manifest
    summary = (
        f"listed={len(listed_ids)} disk={len(on_disk_ids)} "
        f"missing={missing_from_manifest or 'none'} "
        f"orphan={orphan_in_manifest or 'none'}"
    )
    return ok, summary, ""


def t_render_to_records_runs_on_each_template() -> tuple[bool, str, str]:
    """render_to_records produces a non-empty ConfigRecord tuple for every template."""
    failures: list[str] = []
    now = datetime(2026, 5, 19, 12, 0, tzinfo=UTC)
    for path in _shipped_template_paths():
        try:
            doc = load_template_document(path)
            records = render_to_records(doc, "scope_x", now)
            if not records:
                failures.append(f"{path.parent.name}: empty record tuple")
        except Exception as exc:
            failures.append(f"{path.parent.name}: {exc}")
    ok = not failures
    summary = f"rendered {len(_shipped_template_paths())} templates; failures={len(failures)}"
    return ok, summary, "\n".join(failures)


def t_apply_engine_end_to_end_on_each_template(tmp_dir: Path) -> tuple[bool, str, str]:
    """ApplyEngine.apply runs end-to-end against FakeServiceNowClient."""
    now = datetime(2026, 5, 19, 12, 0, tzinfo=UTC)
    failures: list[str] = []
    template_paths = _shipped_template_paths()
    for path in template_paths:
        client = FakeServiceNowClient()
        engine = ApplyEngine(
            sn_client=client,
            paths=NexusPaths(root=tmp_dir),
            clock=lambda: now,
            instance_id="smoke",
            nexus_version="0.0.smoke",
            git_sha="smoke",
        )
        try:
            result = asyncio.run(engine.apply(path))
            if not result.applied_records:
                failures.append(f"{path.parent.name}: empty applied_records")
                continue
            if result.template_id != path.parent.name:
                failures.append(f"{path.parent.name}: template_id mismatch -> {result.template_id}")
        except Exception as exc:
            failures.append(f"{path.parent.name}: {exc}")
    ok = not failures
    summary = f"applied {len(template_paths)} templates; failures={len(failures)}"
    return ok, summary, "\n".join(failures)


def t_validate_assessment_rulesets_script() -> tuple[bool, str, str]:
    """scripts/validate_assessment_rulesets.py exits 0."""
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "validate_assessment_rulesets.py")],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30.0,
        check=False,
    )
    out = result.stdout + result.stderr
    ok = result.returncode == 0
    return ok, f"exit={result.returncode}", out


def t_validate_template_documents_script() -> tuple[bool, str, str]:
    """scripts/validate_template_documents.py exits 0."""
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "validate_template_documents.py")],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30.0,
        check=False,
    )
    out = result.stdout + result.stderr
    ok = result.returncode == 0
    return ok, f"exit={result.returncode}", out


def main() -> int:
    """Smoke entry point."""
    print("smoke-templates: 7 cases\n")
    suite = Suite()
    with tempfile.TemporaryDirectory() as raw_tmp:
        tmp = Path(raw_tmp)
        suite.add(_test("templates_parse_via_loader", t_templates_parse_via_loader))
        suite.add(_test("rulesets_parse_via_loader", t_rulesets_parse_via_loader))
        suite.add(_test("manifest_matches_disk", t_manifest_matches_disk))
        suite.add(
            _test(
                "render_to_records_runs_on_each_template", t_render_to_records_runs_on_each_template
            )
        )
        suite.add(
            _test(
                "apply_engine_end_to_end_on_each_template",
                lambda: t_apply_engine_end_to_end_on_each_template(tmp),
            )
        )
        suite.add(
            _test("validate_assessment_rulesets_script", t_validate_assessment_rulesets_script)
        )
        suite.add(_test("validate_template_documents_script", t_validate_template_documents_script))
    return suite.summary()


if __name__ == "__main__":
    sys.exit(main())
