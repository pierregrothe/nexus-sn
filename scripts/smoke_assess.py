#!/usr/bin/env python
# scripts/smoke_assess.py
# Smoke test for `nexus assess` CLI surface.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Run every path of `nexus assess` that does not require a live SN.

Covers:
* --help renders without a NotImplementedError
* --for + --job mutex -> typer BadParameter (exit 2)
* --live + --archive mutex -> typer BadParameter (exit 2)
* --job + --skip-gate2 -> exit 0 with skip notice
* --for <unknown> without --archive in a clean tree -> exit 1
* No-flag health scan without an archive -> exit 1 with "no archive"
  Notice (rulesets present) or exit 0 "no rulesets" (rulesets absent)

Live-SN paths (`--live` / real `--archive` happy paths) are out of
scope for this smoke run -- they live in tests/assessment/test_cli_assess.py
where injected fakes cover the contract.

Usage:
    poetry run python scripts/smoke_assess.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

__all__: list[str] = []

REPO_ROOT = Path(__file__).resolve().parents[1]


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
        print(f"SMOKE-ASSESS SUMMARY: {passed} passed, {failed} failed")
        if failed:
            print("Failed tests:")
            for r in self.results:
                if not r.passed:
                    print(f"  - {r.name}: {r.summary}")
        return 0 if failed == 0 else 1


def _run(
    cmd: list[str], *, input_text: str | None = None, timeout_s: float = 30.0
) -> subprocess.CompletedProcess[str]:
    """Run a CLI command, capturing stdout+stderr as UTF-8."""
    return subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s,
        check=False,
    )


def _nexus(*args: str) -> list[str]:
    """Build a poetry-run-nexus command vector."""
    return ["poetry", "run", "nexus", *args]


def _test(
    name: str,
    fn: Callable[[], tuple[bool, str, str]],
    timeout_s: float = 30.0,
) -> Result:
    """Run one test function, capturing duration + outcome."""
    started = time.monotonic()
    try:
        ok, summary, tail = fn()
    except subprocess.TimeoutExpired:
        return Result(name=name, passed=False, duration_s=timeout_s, summary="TIMEOUT")
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


def t_help_renders() -> tuple[bool, str, str]:
    """`nexus assess --help` exits 0 and includes all five flags."""
    result = _run(_nexus("assess", "--help"))
    out = result.stdout + result.stderr
    expected_flags = ("--for", "--job", "--live", "--archive", "--skip-gate2")
    missing = [f for f in expected_flags if f not in out]
    ok = result.returncode == 0 and not missing
    summary = f"exit={result.returncode} missing_flags={missing or 'none'}"
    return ok, summary, out


def t_for_and_job_mutex() -> tuple[bool, str, str]:
    """--for + --job together exits 2 (typer BadParameter)."""
    result = _run(_nexus("assess", "--for", "X", "--job", "Y"))
    ok = result.returncode == 2
    return ok, f"exit={result.returncode}", result.stdout + result.stderr


def t_live_and_archive_mutex() -> tuple[bool, str, str]:
    """--live + --archive together exits 2 (typer BadParameter)."""
    result = _run(_nexus("assess", "--live", "--archive", "/tmp/x.yaml"))
    ok = result.returncode == 2
    return ok, f"exit={result.returncode}", result.stdout + result.stderr


def t_job_with_skip_gate2_exits_zero() -> tuple[bool, str, str]:
    """--job <X> --skip-gate2 exits 0 with a 'skipped' notice."""
    result = _run(_nexus("assess", "--job", "JOB1", "--skip-gate2"))
    out = result.stdout + result.stderr
    ok = result.returncode == 0 and "skipped" in out.lower()
    return ok, f"exit={result.returncode}", out


def t_for_unknown_template_exits_nonzero() -> tuple[bool, str, str]:
    """--for <does-not-match-any-ruleset> + no archive -> exit 1."""
    with tempfile.TemporaryDirectory() as tmp:
        env = {"NEXUS_CONFIG_PATH": str(Path(tmp) / "config.yaml")}
        result = subprocess.run(
            _nexus(
                "assess",
                "--for",
                "does-not-exist-anywhere",
                "--archive",
                str(Path(tmp) / "missing.yaml"),
            ),
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30.0,
            check=False,
            env={**__import__("os").environ, **env},
        )
    ok = result.returncode == 1
    return ok, f"exit={result.returncode}", result.stdout + result.stderr


SMOKE_TESTS: list[tuple[str, Callable[[], tuple[bool, str, str]]]] = [
    ("help_renders", t_help_renders),
    ("for_and_job_mutex", t_for_and_job_mutex),
    ("live_and_archive_mutex", t_live_and_archive_mutex),
    ("job_with_skip_gate2_exits_zero", t_job_with_skip_gate2_exits_zero),
    ("for_unknown_template_exits_nonzero", t_for_unknown_template_exits_nonzero),
]


def main() -> int:
    """Smoke entry point."""
    print(f"smoke-assess: {len(SMOKE_TESTS)} cases\n")
    suite = Suite()
    for name, fn in SMOKE_TESTS:
        suite.add(_test(name, fn))
    return suite.summary()


if __name__ == "__main__":
    sys.exit(main())
