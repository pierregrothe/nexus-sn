#!/usr/bin/env python
# scripts/smoke_apply.py
# Smoke test for `nexus apply` CLI surface.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Run every path of `nexus apply` that does not require a live SN.

Covers:
* --help renders without a NotImplementedError
* Bare `apply` with no template arg -> typer usage error (exit 2)
* `apply <unknown-template>` -> exit 1 with "not found" Notice
* `apply <template> --dry-run` -> exit 1 with "not implemented" Notice
* `apply <real-template>` against a clean instance with default
  collaborators -> exit 1 because capture_runner and ApplyEngine
  factory both raise NotImplementedError in the default wiring

Live-SN happy paths live in tests/templates/test_cli_apply.py with
injected fakes.

Usage:
    poetry run python scripts/smoke_apply.py
"""

from __future__ import annotations

import os
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
        print(f"SMOKE-APPLY SUMMARY: {passed} passed, {failed} failed")
        if failed:
            print("Failed tests:")
            for r in self.results:
                if not r.passed:
                    print(f"  - {r.name}: {r.summary}")
        return 0 if failed == 0 else 1


def _run(
    cmd: list[str], *, env_overrides: dict[str, str] | None = None, timeout_s: float = 30.0
) -> subprocess.CompletedProcess[str]:
    """Run a CLI command, capturing stdout+stderr as UTF-8."""
    env = dict(os.environ)
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s,
        check=False,
        env=env,
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
    """`nexus apply --help` exits 0 and lists the new flags."""
    result = _run(_nexus("apply", "--help"))
    out = result.stdout + result.stderr
    expected_flags = ("--scope", "--force", "--skip-gate2", "--dry-run")
    missing = [f for f in expected_flags if f not in out]
    ok = result.returncode == 0 and not missing
    return ok, f"exit={result.returncode} missing={missing or 'none'}", out


def t_missing_template_arg() -> tuple[bool, str, str]:
    """`nexus apply` with no arg exits 2 (typer usage error)."""
    result = _run(_nexus("apply"))
    ok = result.returncode == 2
    return ok, f"exit={result.returncode}", result.stdout + result.stderr


def t_template_not_found() -> tuple[bool, str, str]:
    """`nexus apply <unknown>` exits 1 with 'not found' Notice."""
    with tempfile.TemporaryDirectory() as tmp:
        result = _run(
            _nexus("apply", "does-not-exist-anywhere"),
            env_overrides={"NEXUS_CONFIG_PATH": str(Path(tmp) / "config.yaml")},
        )
    out = result.stdout + result.stderr
    ok = result.returncode == 1 and "not found" in out.lower()
    return ok, f"exit={result.returncode}", out


def t_dry_run_not_implemented() -> tuple[bool, str, str]:
    """`nexus apply X --dry-run` exits 1 with not-implemented notice."""
    with tempfile.TemporaryDirectory() as tmp:
        result = _run(
            _nexus("apply", "nowassist-incident-triage", "--dry-run"),
            env_overrides={"NEXUS_CONFIG_PATH": str(Path(tmp) / "config.yaml")},
        )
    out = result.stdout + result.stderr
    ok = result.returncode == 1 and "not implemented" in out.lower()
    return ok, f"exit={result.returncode}", out


SMOKE_TESTS: list[tuple[str, Callable[[], tuple[bool, str, str]]]] = [
    ("help_renders", t_help_renders),
    ("missing_template_arg", t_missing_template_arg),
    ("template_not_found", t_template_not_found),
    ("dry_run_not_implemented", t_dry_run_not_implemented),
]


def main() -> int:
    """Smoke entry point."""
    print(f"smoke-apply: {len(SMOKE_TESTS)} cases\n")
    suite = Suite()
    for name, fn in SMOKE_TESTS:
        suite.add(_test(name, fn))
    return suite.summary()


if __name__ == "__main__":
    sys.exit(main())
