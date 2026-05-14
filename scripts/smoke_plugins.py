# scripts/smoke_plugins.py
# Comprehensive smoke test for `nexus plugins` CLI commands.
# Author: Pierre Grothe
# Date: 2026-05-14

"""Run every nexus plugins command and report pass/fail.

Requires:
- A registered nexus instance set as the default
- An OAuth token that can be refreshed (script will refresh if expired)
- Network access to the PDI

Tests cover: discovery, list/info/export, inventory, diff, promote, updates,
advisories, impact, orphans, drift, baselines, recommend, install, activate,
upgrade, apply -- both happy paths and error paths.

Destructive ops (install / activate / upgrade) are exercised with the
confirmation prompt rejected ("n") so they never actually mutate SN.

Usage:
    poetry run python scripts/smoke_plugins.py
    poetry run python scripts/smoke_plugins.py --filter list
"""

from __future__ import annotations

import argparse
import json
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
        """Print summary and return non-zero when any test failed."""
        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)
        print()
        print("=" * 70)
        print(f"SMOKE TEST SUMMARY: {passed} passed, {failed} failed")
        if failed:
            print("Failed tests:")
            for r in self.results:
                if not r.passed:
                    print(f"  - {r.name}: {r.summary}")
        return 0 if failed == 0 else 1


def _run(
    cmd: list[str], *, input_text: str | None = None, timeout_s: float = 30.0
) -> subprocess.CompletedProcess[str]:
    """Run a CLI command, capturing stdout+stderr as UTF-8.

    Force UTF-8 with errors='replace' so Windows' cp1252 default does not
    blow up on Rich's box-drawing characters.
    """
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


# ---------------------------------------------------------------------------
# Individual smoke tests
# ---------------------------------------------------------------------------


def t_bare_discovery() -> tuple[bool, str, str]:
    """`nexus plugins` shows the two-box discovery view including new commands."""
    proc = _run(_nexus("plugins"), timeout_s=20)
    ok = proc.returncode == 0
    text = proc.stdout
    for cmd in ("list", "info", "install", "activate", "upgrade", "apply"):
        if cmd not in text:
            ok = False
            return ok, f"missing '{cmd}' in discovery output", text[-400:]
    return ok, f"exit={proc.returncode}, len={len(text)}", text[-400:]


def t_help_for_each_leaf() -> tuple[bool, str, str]:
    """Each leaf command --help returns 0 with 'Usage'."""
    leaves = [
        "list",
        "info",
        "export",
        "diff",
        "promote",
        "updates",
        "advisories",
        "defer",
        "undo-defer",
        "list-deferred",
        "impact",
        "orphans",
        "drift",
        "explain",
        "roadmap",
        "baselines",
        "recommend",
        "install",
        "activate",
        "upgrade",
        "apply",
    ]
    missing = []
    for leaf in leaves:
        proc = _run(_nexus("plugins", leaf, "--help"), timeout_s=15)
        out = proc.stdout or ""
        if proc.returncode != 0 or "Usage" not in out:
            missing.append(f"{leaf} (exit={proc.returncode})")
    return (
        len(missing) == 0,
        f"checked {len(leaves)} leaves; failures: {missing or 'none'}",
        "\n".join(missing),
    )


def t_list_default() -> tuple[bool, str, str]:
    """`nexus plugins list` prints the inventory."""
    proc = _run(_nexus("plugins", "list"), timeout_s=20)
    ok = proc.returncode == 0 and "Plugin" in proc.stdout
    return ok, f"exit={proc.returncode}", proc.stdout[-200:]


def t_list_json() -> tuple[bool, str, str]:
    """`nexus plugins list --format json` emits parseable JSON."""
    proc = _run(_nexus("plugins", "list", "--format", "json"), timeout_s=20)
    if proc.returncode != 0:
        return False, f"exit={proc.returncode}", proc.stderr[-300:]
    last_line = proc.stdout.strip().splitlines()[-1]
    try:
        payload = json.loads(last_line)
        ok = "plugins" in payload
        return ok, f"JSON parsed, plugins count={len(payload.get('plugins', []))}", ""
    except json.JSONDecodeError as exc:
        return False, f"JSON parse failed: {exc}", last_line[:300]


def t_list_filter_product() -> tuple[bool, str, str]:
    """`--product ITSM` filters."""
    proc = _run(_nexus("plugins", "list", "--product", "ITSM"), timeout_s=20)
    ok = proc.returncode == 0
    return ok, f"exit={proc.returncode}", proc.stdout[-200:]


def t_list_unknown_format() -> tuple[bool, str, str]:
    """`--format xml` rejected."""
    proc = _run(_nexus("plugins", "list", "--format", "xml"), timeout_s=15)
    ok = proc.returncode == 1 and "Unknown --format" in proc.stdout
    return ok, f"exit={proc.returncode}", proc.stdout[-200:]


def t_info_known_plugin() -> tuple[bool, str, str]:
    """`info <plugin>` for an installed plugin."""
    proc = _run(_nexus("plugins", "info", "com.glideapp.knowledge"), timeout_s=15)
    ok = proc.returncode == 0 and "com.glideapp.knowledge" in proc.stdout
    return ok, f"exit={proc.returncode}", proc.stdout[-200:]


def t_info_unknown_plugin() -> tuple[bool, str, str]:
    """`info <fake>` exits non-zero."""
    proc = _run(_nexus("plugins", "info", "com.fake.does-not-exist"), timeout_s=15)
    ok = proc.returncode != 0
    return ok, f"exit={proc.returncode}", proc.stdout[-200:]


def t_export_yaml() -> tuple[bool, str, str]:
    """`export --format yaml` writes a file."""
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as tmp:
        out = Path(tmp.name)
    try:
        proc = _run(
            _nexus("plugins", "export", "--format", "yaml", "--out", str(out)), timeout_s=20
        )
        ok = proc.returncode == 0 and out.exists() and out.stat().st_size > 100
        return ok, f"exit={proc.returncode}, size={out.stat().st_size if out.exists() else 0}", ""
    finally:
        out.unlink(missing_ok=True)


def t_export_csv() -> tuple[bool, str, str]:
    """`export --format csv` writes a file."""
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        out = Path(tmp.name)
    try:
        proc = _run(_nexus("plugins", "export", "--format", "csv", "--out", str(out)), timeout_s=20)
        ok = (
            proc.returncode == 0 and out.exists() and "plugin_id" in out.read_text(encoding="utf-8")
        )
        return ok, f"exit={proc.returncode}, size={out.stat().st_size if out.exists() else 0}", ""
    finally:
        out.unlink(missing_ok=True)


def t_export_unknown_format() -> tuple[bool, str, str]:
    """`export --format xml` rejected."""
    proc = _run(_nexus("plugins", "export", "--format", "xml", "--out", "/tmp/x"), timeout_s=15)
    ok = proc.returncode != 0
    return ok, f"exit={proc.returncode}", proc.stdout[-150:]


def t_diff_same_profile() -> tuple[bool, str, str]:
    """`diff` with same profile twice -- shows zero entries cleanly."""
    proc = _run(_nexus("plugins", "diff", "alectri", "alectri"), timeout_s=20)
    ok = proc.returncode == 0
    return ok, f"exit={proc.returncode}", proc.stdout[-200:]


def t_updates_lists_available() -> tuple[bool, str, str]:
    """`updates` shows available updates from cached inventory."""
    proc = _run(_nexus("plugins", "updates"), timeout_s=30)
    ok = proc.returncode == 0 and (
        "Updates available" in proc.stdout or "No updates" in proc.stdout
    )
    return ok, f"exit={proc.returncode}", proc.stdout[-200:]


def t_advisories_lists() -> tuple[bool, str, str]:
    """`advisories` runs and prints something."""
    proc = _run(_nexus("plugins", "advisories"), timeout_s=20)
    ok = proc.returncode in (0, 1)  # 1 if strict and findings exist
    return ok, f"exit={proc.returncode}", proc.stdout[-200:]


def t_list_deferred_works() -> tuple[bool, str, str]:
    """`list-deferred` (top-level plugins command) runs cleanly."""
    proc = _run(_nexus("plugins", "list-deferred"), timeout_s=15)
    ok = proc.returncode == 0
    return ok, f"exit={proc.returncode}", proc.stdout[-200:]


def t_impact_known_plugin() -> tuple[bool, str, str]:
    """`impact <plugin>` runs against a real installed plugin."""
    proc = _run(_nexus("plugins", "impact", "com.glideapp.knowledge"), timeout_s=60)
    ok = proc.returncode == 0
    return ok, f"exit={proc.returncode}", proc.stdout[-200:]


def t_impact_unknown_plugin() -> tuple[bool, str, str]:
    """`impact <fake>` errors gracefully."""
    proc = _run(_nexus("plugins", "impact", "com.fake.does-not-exist"), timeout_s=15)
    ok = proc.returncode != 0
    return ok, f"exit={proc.returncode}", proc.stdout[-200:]


def t_orphans_runs() -> tuple[bool, str, str]:
    """`orphans` exits cleanly."""
    proc = _run(_nexus("plugins", "orphans"), timeout_s=20)
    ok = proc.returncode == 0
    return ok, f"exit={proc.returncode}", proc.stdout[-200:]


def t_baselines_list() -> tuple[bool, str, str]:
    """`baselines list` runs."""
    proc = _run(_nexus("plugins", "baselines", "list"), timeout_s=15)
    ok = proc.returncode == 0
    return ok, f"exit={proc.returncode}", proc.stdout[-200:]


def t_install_cancel() -> tuple[bool, str, str]:
    """`install <plugin>` cancelled at prompt -> exit 0."""
    proc = _run(
        _nexus("plugins", "install", "com.glideapp.knowledge"), input_text="n\n", timeout_s=60
    )
    ok = proc.returncode == 0 and "Dependency cascade" in proc.stdout
    return ok, f"exit={proc.returncode}", proc.stdout[-200:]


def t_activate_cancel() -> tuple[bool, str, str]:
    """`activate <plugin>` cancelled at prompt -> exit 0."""
    proc = _run(
        _nexus("plugins", "activate", "com.glideapp.knowledge"), input_text="n\n", timeout_s=30
    )
    ok = proc.returncode == 0
    return ok, f"exit={proc.returncode}", proc.stdout[-200:]


def t_upgrade_cancel() -> tuple[bool, str, str]:
    """`upgrade <plugin>` cancelled at prompt -> exit 0."""
    proc = _run(
        _nexus("plugins", "upgrade", "sn_fsm_ext_mobile", "--to", "4.6.1"),
        input_text="n\n",
        timeout_s=60,
    )
    ok = proc.returncode == 0 and "Dependency cascade" in proc.stdout
    return ok, f"exit={proc.returncode}", proc.stdout[-200:]


def t_apply_missing_file() -> tuple[bool, str, str]:
    """`apply <missing>` exits with code 2 + error notice on stderr."""
    proc = _run(_nexus("plugins", "apply", "/tmp/does-not-exist.yaml"), timeout_s=15)
    combined = (proc.stdout or "") + (proc.stderr or "")
    ok = proc.returncode == 2 and "not found" in combined.lower()
    return ok, f"exit={proc.returncode}", combined[-200:]


def t_apply_valid_plan_cancel() -> tuple[bool, str, str]:
    """`apply <valid plan>` reaches the confirmation prompt, then cancel -> exit 0."""
    plan_yaml = """source_profile: alectri
target_profile: alectri
actions:
  - action: upgrade
    plugin_id: sn_fsm_ext_mobile
    name: Field Service Contractor for mobile
    product_family: FSM
    target_version: 4.6.1
    current_version: 4.6.0
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
        tmp.write(plan_yaml)
        path = Path(tmp.name)
    try:
        proc = _run(_nexus("plugins", "apply", str(path)), input_text="n\n", timeout_s=30)
        ok = proc.returncode == 0 and "1 actions" in proc.stdout
        return ok, f"exit={proc.returncode}", proc.stdout[-200:]
    finally:
        path.unlink(missing_ok=True)


def t_apply_malformed_yaml() -> tuple[bool, str, str]:
    """`apply <malformed>` exits non-zero with a useful error."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
        tmp.write("not: a valid plan\nblah:\n  - 1\n  - 2\n")
        path = Path(tmp.name)
    try:
        proc = _run(_nexus("plugins", "apply", str(path)), timeout_s=15)
        combined = (proc.stdout or "") + (proc.stderr or "")
        ok = proc.returncode != 0
        return ok, f"exit={proc.returncode}", combined[-200:]
    finally:
        path.unlink(missing_ok=True)


def t_promote_same_profile_refused() -> tuple[bool, str, str]:
    """`promote alectri --to alectri` refuses (same profile)."""
    proc = _run(_nexus("plugins", "promote", "alectri", "--to", "alectri"), timeout_s=15)
    ok = proc.returncode != 0 or "nothing to promote" in proc.stdout.lower()
    return ok, f"exit={proc.returncode}", proc.stdout[-200:]


def t_explain_help() -> tuple[bool, str, str]:
    """`explain --help` shows usage."""
    proc = _run(_nexus("plugins", "explain", "--help"), timeout_s=15)
    out = proc.stdout or ""
    ok = proc.returncode == 0 and "Usage" in out
    return ok, f"exit={proc.returncode}", out[-200:]


def t_deactivate_help() -> tuple[bool, str, str]:
    """`deactivate --help` shows --force option."""
    proc = _run(_nexus("plugins", "deactivate", "--help"), timeout_s=15)
    out = proc.stdout or ""
    ok = proc.returncode == 0 and "--force" in out
    return ok, f"exit={proc.returncode}", out[-200:]


def t_uninstall_help() -> tuple[bool, str, str]:
    """`uninstall --help` shows --force option."""
    proc = _run(_nexus("plugins", "uninstall", "--help"), timeout_s=15)
    out = proc.stdout or ""
    ok = proc.returncode == 0 and "--force" in out
    return ok, f"exit={proc.returncode}", out[-200:]


def t_deactivate_cancel() -> tuple[bool, str, str]:
    """`deactivate <plugin>` cancelled at action prompt -> exit 0."""
    proc = _run(
        _nexus("plugins", "deactivate", "com.glideapp.knowledge"),
        input_text="n\n",
        timeout_s=30,
    )
    ok = proc.returncode == 0
    return ok, f"exit={proc.returncode}", proc.stdout[-200:]


def t_uninstall_base_plugin_refused() -> tuple[bool, str, str]:
    """`uninstall <base-plugin>` with --yes immediately refuses (no force escape).

    Uses a known base plugin (source=='servicenow') from the inventory.
    The executor refuses with PluginUnsupportedError; CLI returns exit 1.
    """
    proc = _run(
        _nexus("plugins", "uninstall", "com.glideapp.knowledge", "--yes"),
        timeout_s=20,
    )
    out = proc.stdout or ""
    ok = proc.returncode == 1 and "cannot be uninstalled" in out
    return ok, f"exit={proc.returncode}", out[-200:]


# ---------------------------------------------------------------------------
# Test registry + driver
# ---------------------------------------------------------------------------

ALL_TESTS: list[tuple[str, Callable[[], tuple[bool, str, str]]]] = [
    ("bare-discovery", t_bare_discovery),
    ("help-each-leaf", t_help_for_each_leaf),
    ("list-default", t_list_default),
    ("list-json", t_list_json),
    ("list-filter-product", t_list_filter_product),
    ("list-unknown-format", t_list_unknown_format),
    ("info-known", t_info_known_plugin),
    ("info-unknown", t_info_unknown_plugin),
    ("export-yaml", t_export_yaml),
    ("export-csv", t_export_csv),
    ("export-unknown-format", t_export_unknown_format),
    ("explain-help", t_explain_help),
    ("diff-same-profile", t_diff_same_profile),
    ("promote-same-profile-refused", t_promote_same_profile_refused),
    ("updates-lists", t_updates_lists_available),
    ("advisories-lists", t_advisories_lists),
    ("list-deferred", t_list_deferred_works),
    ("impact-known", t_impact_known_plugin),
    ("impact-unknown", t_impact_unknown_plugin),
    ("orphans-runs", t_orphans_runs),
    ("baselines-list", t_baselines_list),
    ("install-cancel", t_install_cancel),
    ("activate-cancel", t_activate_cancel),
    ("upgrade-cancel", t_upgrade_cancel),
    ("apply-missing-file", t_apply_missing_file),
    ("apply-malformed-yaml", t_apply_malformed_yaml),
    ("apply-valid-plan-cancel", t_apply_valid_plan_cancel),
    ("deactivate-help", t_deactivate_help),
    ("uninstall-help", t_uninstall_help),
    ("deactivate-cancel", t_deactivate_cancel),
    ("uninstall-base-refused", t_uninstall_base_plugin_refused),
]


def main() -> int:
    """Run the smoke suite and print a final summary."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--filter", help="Only run tests whose name contains this substring")
    args = parser.parse_args()

    suite = Suite()
    print(f"Running {len(ALL_TESTS)} smoke tests against the default nexus instance.")
    print("Destructive ops (install/activate/upgrade) are exercised with rejection at the prompt.")
    print("=" * 70)
    for name, fn in ALL_TESTS:
        if args.filter and args.filter not in name:
            continue
        suite.add(_test(name, fn))
    return suite.summary()


if __name__ == "__main__":
    sys.exit(main())
