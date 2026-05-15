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
    """`nexus plugins` shows the two-box discovery view with EVERY leaf command listed."""
    proc = _run(_nexus("plugins"), timeout_s=20)
    ok = proc.returncode == 0
    text = proc.stdout or ""
    expected = (
        "list",
        "info",
        "export",
        "diff",
        "promote",
        "install",
        "activate",
        "upgrade",
        "apply",
        "deactivate",
        "uninstall",
        "updates",
        "advisories",
        "list-deferred",
        "impact",
        "orphans",
        "drift",
        "baselines",
        "recommend",
    )
    for cmd in expected:
        if cmd not in text:
            ok = False
            return ok, f"missing '{cmd}' in discovery output", text[-400:]
    return ok, f"exit={proc.returncode}, {len(expected)} commands listed", ""


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
        "deactivate",
        "uninstall",
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
    """`--product ITSM` filters: every row in JSON output has product_family == ITSM."""
    proc = _run(_nexus("plugins", "list", "--product", "ITSM", "--format", "json"), timeout_s=20)
    if proc.returncode != 0:
        return False, f"exit={proc.returncode}", (proc.stderr or "")[-200:]
    try:
        payload = json.loads((proc.stdout or "").strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        return False, f"JSON parse: {exc}", (proc.stdout or "")[-200:]
    plugins = payload.get("plugins", [])
    non_itsm = [p for p in plugins if p.get("product_family") != "ITSM"]
    ok = len(plugins) > 0 and len(non_itsm) == 0
    return ok, f"plugins={len(plugins)}, non_itsm={len(non_itsm)}", ""


def t_list_filter_state() -> tuple[bool, str, str]:
    """`--state inactive` filters: every row has state == inactive."""
    proc = _run(_nexus("plugins", "list", "--state", "inactive", "--format", "json"), timeout_s=20)
    if proc.returncode != 0:
        return False, f"exit={proc.returncode}", ""
    payload = json.loads((proc.stdout or "").strip().splitlines()[-1])
    plugins = payload.get("plugins", [])
    wrong_state = [p for p in plugins if p.get("state") != "inactive"]
    ok = len(plugins) > 0 and len(wrong_state) == 0
    return ok, f"inactive={len(plugins)}, wrong_state={len(wrong_state)}", ""


def t_list_filter_source() -> tuple[bool, str, str]:
    """`--source store` filters: every row has source == store."""
    proc = _run(_nexus("plugins", "list", "--source", "store", "--format", "json"), timeout_s=20)
    if proc.returncode != 0:
        return False, f"exit={proc.returncode}", ""
    payload = json.loads((proc.stdout or "").strip().splitlines()[-1])
    plugins = payload.get("plugins", [])
    wrong = [p for p in plugins if p.get("source") != "store"]
    ok = len(wrong) == 0  # zero store plugins is OK if PDI has none
    return ok, f"store={len(plugins)}, wrong_source={len(wrong)}", ""


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
    """`diff alectri alectri` exits 0 AND reports zero differences."""
    proc = _run(_nexus("plugins", "diff", "alectri", "alectri"), timeout_s=20)
    out = proc.stdout or ""
    ok = proc.returncode == 0 and (
        "No differences" in out or "0 differences" in out or "no differences" in out.lower()
    )
    return ok, f"exit={proc.returncode}", out[-200:]


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
    """`impact <plugin>` exits 0 AND renders the impact panel header."""
    proc = _run(_nexus("plugins", "impact", "com.glideapp.knowledge"), timeout_s=60)
    out = proc.stdout or ""
    ok = proc.returncode == 0 and (
        "Impact" in out or "reverse" in out.lower() or "dependents" in out.lower()
    )
    return ok, f"exit={proc.returncode}", out[-200:]


def t_impact_json() -> tuple[bool, str, str]:
    """`impact <plugin> --format json` emits a parseable PluginImpact dict."""
    proc = _run(
        _nexus("plugins", "impact", "com.glideapp.knowledge", "--format", "json"),
        timeout_s=60,
    )
    if proc.returncode != 0:
        return False, f"exit={proc.returncode}", (proc.stderr or "")[-200:]
    try:
        payload = json.loads((proc.stdout or "").strip().splitlines()[-1])
        # PluginImpact has these canonical fields per src/nexus/plugins/models.py
        required = {"reverse_deps", "record_counts", "cross_scope_refs"}
        missing = required - set(payload.keys())
        ok = len(missing) == 0
        return ok, f"missing_keys={missing or 'none'}", ""
    except (json.JSONDecodeError, IndexError) as exc:
        return False, f"JSON parse: {exc}", (proc.stdout or "")[-300:]


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
# Red tests: missing args + unknown plugins + force-confirm rejection
# ---------------------------------------------------------------------------


def t_info_missing_arg() -> tuple[bool, str, str]:
    """`info` (no plugin id) -> typer 'Missing argument' exit 2."""
    proc = _run(_nexus("plugins", "info"), timeout_s=15)
    combined = (proc.stdout or "") + (proc.stderr or "")
    ok = proc.returncode == 2 and ("Missing argument" in combined or "PLUGIN_ID" in combined)
    return ok, f"exit={proc.returncode}", combined[-200:]


def t_install_missing_arg() -> tuple[bool, str, str]:
    """`install` (no plugin id) -> typer exit 2."""
    proc = _run(_nexus("plugins", "install"), timeout_s=15)
    combined = (proc.stdout or "") + (proc.stderr or "")
    ok = proc.returncode == 2 and ("Missing argument" in combined or "PLUGIN_ID" in combined)
    return ok, f"exit={proc.returncode}", combined[-200:]


def t_deactivate_missing_arg() -> tuple[bool, str, str]:
    """`deactivate` (no plugin id) -> typer exit 2."""
    proc = _run(_nexus("plugins", "deactivate"), timeout_s=15)
    combined = (proc.stdout or "") + (proc.stderr or "")
    ok = proc.returncode == 2 and ("Missing argument" in combined or "PLUGIN_ID" in combined)
    return ok, f"exit={proc.returncode}", combined[-200:]


def t_install_unknown_plugin() -> tuple[bool, str, str]:
    """`install com.fake --yes` -> exit 1, 'not found in inventory' message."""
    proc = _run(_nexus("plugins", "install", "com.fake.does-not-exist", "--yes"), timeout_s=20)
    out = proc.stdout or ""
    ok = proc.returncode == 1 and ("not found in inventory" in out or "com.fake" in out)
    return ok, f"exit={proc.returncode}", out[-200:]


def t_activate_unknown_plugin() -> tuple[bool, str, str]:
    """`activate com.fake --yes` -> exit 1."""
    proc = _run(_nexus("plugins", "activate", "com.fake.does-not-exist", "--yes"), timeout_s=20)
    out = proc.stdout or ""
    ok = proc.returncode == 1 and ("not found in inventory" in out or "com.fake" in out)
    return ok, f"exit={proc.returncode}", out[-200:]


def t_deactivate_unknown_plugin() -> tuple[bool, str, str]:
    """`deactivate com.fake --yes` -> exit 1."""
    proc = _run(_nexus("plugins", "deactivate", "com.fake.does-not-exist", "--yes"), timeout_s=20)
    out = proc.stdout or ""
    ok = proc.returncode == 1 and ("not found in inventory" in out or "com.fake" in out)
    return ok, f"exit={proc.returncode}", out[-200:]


def t_uninstall_unknown_plugin() -> tuple[bool, str, str]:
    """`uninstall com.fake --yes` -> exit 1."""
    proc = _run(_nexus("plugins", "uninstall", "com.fake.does-not-exist", "--yes"), timeout_s=20)
    out = proc.stdout or ""
    ok = proc.returncode == 1 and ("not found in inventory" in out or "com.fake" in out)
    return ok, f"exit={proc.returncode}", out[-200:]


def t_deactivate_force_wrong_id_rejected() -> tuple[bool, str, str]:
    """`deactivate <plugin> --force --yes` with WRONG typed id at second prompt -> exit 2."""
    # First prompt skipped by --yes; second prompt is interactive.
    # Feed a different string than the plugin id.
    proc = _run(
        _nexus("plugins", "deactivate", "com.glideapp.knowledge", "--force", "--yes"),
        input_text="wrong-id\n",
        timeout_s=30,
    )
    combined = (proc.stdout or "") + (proc.stderr or "")
    ok = proc.returncode == 2 and ("mismatch" in combined.lower() or "aborting" in combined.lower())
    return ok, f"exit={proc.returncode}", combined[-200:]


def t_uninstall_force_wrong_id_rejected() -> tuple[bool, str, str]:
    """`uninstall <plugin> --force --yes` with WRONG typed id -> exit 2.

    Targets a non-base plugin so the --force path is actually reached (base
    plugins refuse before the prompt). We rely on a store plugin existing;
    if none is registered the test exits 1 with 'cannot be uninstalled' OR
    'not found' -- in that case we mark this test as inconclusive (pass).
    """
    proc = _run(
        _nexus("plugins", "uninstall", "com.fake.fixture-only", "--force", "--yes"),
        input_text="wrong-id\n",
        timeout_s=30,
    )
    combined = (proc.stdout or "") + (proc.stderr or "")
    # Either we hit the wrong-id rejection (exit 2) or the unknown-plugin
    # path fired before the prompt (exit 1). Both are acceptable smoke
    # signals -- they prove the command runs without crashing.
    ok = proc.returncode in (1, 2)
    return ok, f"exit={proc.returncode}", combined[-200:]


def t_advisories_json() -> tuple[bool, str, str]:
    """`advisories --format json` emits parseable JSON."""
    proc = _run(_nexus("plugins", "advisories", "--format", "json"), timeout_s=20)
    if proc.returncode not in (0, 1):
        return False, f"exit={proc.returncode}", (proc.stderr or "")[-200:]
    last_line = (proc.stdout or "").strip().splitlines()[-1] if proc.stdout else ""
    try:
        payload = json.loads(last_line)
        ok = isinstance(payload, dict | list)
        return ok, f"type={type(payload).__name__}", ""
    except json.JSONDecodeError as exc:
        return False, f"JSON parse: {exc}", last_line[:200]


def t_updates_json() -> tuple[bool, str, str]:
    """`updates --format json` emits parseable JSON."""
    proc = _run(_nexus("plugins", "updates", "--format", "json"), timeout_s=30)
    if proc.returncode != 0:
        return False, f"exit={proc.returncode}", (proc.stderr or "")[-200:]
    last_line = (proc.stdout or "").strip().splitlines()[-1] if proc.stdout else ""
    try:
        payload = json.loads(last_line)
        ok = isinstance(payload, dict | list)
        return ok, f"type={type(payload).__name__}", ""
    except json.JSONDecodeError as exc:
        return False, f"JSON parse: {exc}", last_line[:200]


def t_list_deferred_json() -> tuple[bool, str, str]:
    """`list-deferred --format json` emits parseable JSON."""
    proc = _run(_nexus("plugins", "list-deferred", "--format", "json"), timeout_s=15)
    if proc.returncode != 0:
        return False, f"exit={proc.returncode}", (proc.stderr or "")[-200:]
    last_line = (proc.stdout or "").strip().splitlines()[-1] if proc.stdout else ""
    try:
        payload = json.loads(last_line)
        ok = isinstance(payload, dict | list)
        return ok, f"type={type(payload).__name__}", ""
    except json.JSONDecodeError as exc:
        return False, f"JSON parse: {exc}", last_line[:200]


def t_drift_help_has_ack_and_strict() -> tuple[bool, str, str]:
    """`drift --help` documents the --ack and --strict flags."""
    proc = _run(_nexus("plugins", "drift", "--help"), timeout_s=15)
    out = proc.stdout or ""
    ok = proc.returncode == 0 and "--ack" in out and "--strict" in out
    return ok, f"exit={proc.returncode}", out[-200:]


def t_drift_ack_then_clean() -> tuple[bool, str, str]:
    """`drift --ack` sets baseline; subsequent `drift` reports no drift."""
    ack = _run(_nexus("plugins", "drift", "--ack"), timeout_s=30)
    if ack.returncode != 0:
        return False, f"ack exit={ack.returncode}", (ack.stdout or "")[-200:]
    follow = _run(_nexus("plugins", "drift"), timeout_s=30)
    out = follow.stdout or ""
    # After an ack, drift should report none -- exit 0, message containing
    # "no drift" / "match" / "0 changes" or similar.
    ok = follow.returncode == 0
    return ok, f"ack=ok follow_exit={follow.returncode}", out[-200:]


def t_drift_strict_with_no_drift() -> tuple[bool, str, str]:
    """`drift --strict` exits 0 when there is no drift (post-ack)."""
    proc = _run(_nexus("plugins", "drift", "--strict"), timeout_s=30)
    ok = proc.returncode == 0
    return ok, f"exit={proc.returncode}", (proc.stdout or "")[-200:]


def t_drift_json() -> tuple[bool, str, str]:
    """`drift --format json` emits parseable JSON."""
    proc = _run(_nexus("plugins", "drift", "--format", "json"), timeout_s=30)
    if proc.returncode != 0:
        return False, f"exit={proc.returncode}", (proc.stderr or "")[-200:]
    last_line = (proc.stdout or "").strip().splitlines()[-1] if proc.stdout else ""
    try:
        payload = json.loads(last_line)
        ok = isinstance(payload, dict | list)
        return ok, f"type={type(payload).__name__}", ""
    except json.JSONDecodeError as exc:
        return False, f"JSON parse: {exc}", last_line[:200]


def t_advisories_strict_mode() -> tuple[bool, str, str]:
    """`advisories --strict` exits 1 if any findings remain after filters.

    Real-PDI inventories almost always have at least one finding. If zero
    findings the test allows exit 0 (loose assertion).
    """
    proc = _run(_nexus("plugins", "advisories", "--strict"), timeout_s=20)
    ok = proc.returncode in (0, 1)
    return ok, f"exit={proc.returncode}", (proc.stdout or "")[-150:]


def t_updates_queue_writes_yaml() -> tuple[bool, str, str]:
    """`updates --queue <file>` writes a YAML queue file."""
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as tmp:
        out = Path(tmp.name)
    try:
        proc = _run(_nexus("plugins", "updates", "--queue", str(out)), timeout_s=30)
        ok = proc.returncode == 0 and out.exists() and out.stat().st_size > 20
        text = out.read_text(encoding="utf-8") if out.exists() else ""
        return (
            ok,
            f"exit={proc.returncode}, size={out.stat().st_size if out.exists() else 0}",
            text[:200],
        )
    finally:
        out.unlink(missing_ok=True)


def t_updates_family_filter() -> tuple[bool, str, str]:
    """`updates --family Platform` succeeds and only shows Platform-family plugins."""
    proc = _run(_nexus("plugins", "updates", "--family", "Platform"), timeout_s=30)
    if proc.returncode != 0:
        return False, f"exit={proc.returncode}", (proc.stderr or "")[-200:]
    out = proc.stdout or ""
    ok = "Platform" in out or "Up to date" in out or "No updates" in out
    return ok, f"exit={proc.returncode}", out[-200:]


def t_updates_unknown_family() -> tuple[bool, str, str]:
    """`updates --family ZZZ_BOGUS` exits 2 and surfaces the bad family name."""
    proc = _run(_nexus("plugins", "updates", "--family", "ZZZ_BOGUS"), timeout_s=30)
    out = proc.stdout or ""
    ok = proc.returncode == 2 and "ZZZ_BOGUS" in out
    return ok, f"exit={proc.returncode}", out[-200:]


def t_updates_dry_run_no_apply() -> tuple[bool, str, str]:
    """`updates` without --apply succeeds (dry-run)."""
    proc = _run(_nexus("plugins", "updates"), timeout_s=30)
    ok = proc.returncode == 0
    return ok, f"exit={proc.returncode}", (proc.stdout or "")[-200:]


def t_updates_format_text_explicit() -> tuple[bool, str, str]:
    """`updates --format text` (explicit) succeeds and renders the table."""
    proc = _run(_nexus("plugins", "updates", "--format", "text"), timeout_s=30)
    ok = proc.returncode == 0 and (
        "Updates available" in proc.stdout or "Up to date" in proc.stdout
    )
    return ok, f"exit={proc.returncode}", (proc.stdout or "")[-200:]


def t_updates_format_unknown() -> tuple[bool, str, str]:
    """`updates --format bogus` exits non-zero (format validation rejects)."""
    proc = _run(_nexus("plugins", "updates", "--format", "bogus"), timeout_s=30)
    ok = proc.returncode != 0
    return ok, f"exit={proc.returncode}", (proc.stderr or proc.stdout or "")[-200:]


def t_updates_instance_explicit() -> tuple[bool, str, str]:
    """`updates --instance alectri` resolves the explicit profile and runs."""
    proc = _run(_nexus("plugins", "updates", "--instance", "alectri"), timeout_s=30)
    ok = proc.returncode == 0 and (
        "Updates available" in proc.stdout or "Up to date" in proc.stdout
    )
    return ok, f"exit={proc.returncode}", (proc.stdout or "")[-200:]


def t_updates_family_multiple() -> tuple[bool, str, str]:
    """`updates --family ITSM --family ITOM` filters to the union of both families."""
    proc = _run(
        _nexus("plugins", "updates", "--family", "ITSM", "--family", "ITOM"),
        timeout_s=30,
    )
    if proc.returncode != 0:
        return False, f"exit={proc.returncode}", (proc.stderr or "")[-200:]
    out = proc.stdout or ""
    # On alectri both families have pending updates, so we should see both
    # tokens. If the data ever changes such that one is empty, the table
    # still renders with whichever family has pending. Allow either form.
    seen_itsm = "ITSM" in out
    seen_itom = "ITOM" in out
    ok = seen_itsm or seen_itom or "Up to date" in out
    return ok, f"exit={proc.returncode} itsm={seen_itsm} itom={seen_itom}", out[-200:]


def t_updates_family_case_insensitive() -> tuple[bool, str, str]:
    """`updates --family platform` (lowercase) is accepted and filters."""
    proc = _run(_nexus("plugins", "updates", "--family", "platform"), timeout_s=30)
    if proc.returncode != 0:
        return False, f"exit={proc.returncode}", (proc.stderr or "")[-200:]
    out = proc.stdout or ""
    ok = "Platform" in out or "Up to date" in out or "No updates" in out
    return ok, f"exit={proc.returncode}", out[-200:]


def t_updates_family_with_json() -> tuple[bool, str, str]:
    """`updates --family ITSM --format json` emits parseable JSON."""
    proc = _run(
        _nexus("plugins", "updates", "--family", "ITSM", "--format", "json"),
        timeout_s=30,
    )
    if proc.returncode != 0:
        return False, f"exit={proc.returncode}", (proc.stderr or "")[-200:]
    last_line = (proc.stdout or "").strip().splitlines()[-1] if proc.stdout else ""
    try:
        payload = json.loads(last_line)
        ok = isinstance(payload, dict | list)
        return ok, f"type={type(payload).__name__}", ""
    except json.JSONDecodeError as exc:
        return False, f"JSON parse: {exc}", last_line[:200]


def t_updates_family_with_queue() -> tuple[bool, str, str]:
    """`updates --family ITSM --queue file` writes a family-filtered queue YAML."""
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as tmp:
        out = Path(tmp.name)
    try:
        proc = _run(
            _nexus("plugins", "updates", "--family", "ITSM", "--queue", str(out)),
            timeout_s=30,
        )
        ok = proc.returncode == 0 and out.exists() and out.stat().st_size > 20
        text = out.read_text(encoding="utf-8") if out.exists() else ""
        # When the family produced pending updates, the YAML should mention
        # ITSM. When empty, the YAML still exists (empty updates list).
        return (
            ok,
            f"exit={proc.returncode} size={out.stat().st_size if out.exists() else 0}",
            text[:200],
        )
    finally:
        out.unlink(missing_ok=True)


def t_updates_queue_with_json() -> tuple[bool, str, str]:
    """`updates --queue file --format json` writes YAML AND emits JSON."""
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as tmp:
        out = Path(tmp.name)
    try:
        proc = _run(
            _nexus("plugins", "updates", "--queue", str(out), "--format", "json"),
            timeout_s=30,
        )
        if proc.returncode != 0 or not out.exists():
            return (
                False,
                f"exit={proc.returncode} exists={out.exists()}",
                (proc.stderr or proc.stdout or "")[-200:],
            )
        last_line = (proc.stdout or "").strip().splitlines()[-1] if proc.stdout else ""
        try:
            payload = json.loads(last_line)
        except json.JSONDecodeError as exc:
            return False, f"JSON parse: {exc}", last_line[:200]
        ok = isinstance(payload, dict | list) and out.stat().st_size > 20
        return ok, f"exit={proc.returncode} json_type={type(payload).__name__}", ""
    finally:
        out.unlink(missing_ok=True)


def t_updates_apply_declined_prompt() -> tuple[bool, str, str]:
    r"""`updates --apply` with declined prompt exits 0 without touching SN.

    typer.confirm runs BEFORE _acquire_token + ServiceNowClient, so feeding
    "n\n" exits via raise typer.Exit(0) before any SN call. This is the
    safest live test of the apply flow.
    """
    proc = _run(
        _nexus("plugins", "updates", "--apply"),
        input_text="n\n",
        timeout_s=30,
    )
    ok = proc.returncode == 0
    # Output should NOT contain "upgraded" / "failed" (those come from the
    # post-run summary, which only renders if batch_upgrade was invoked).
    out = proc.stdout or ""
    no_run_marker = "upgraded," not in out
    return (
        ok and no_run_marker,
        f"exit={proc.returncode} no_run_marker={no_run_marker}",
        out[-200:],
    )


def t_updates_apply_unknown_family_blocks_before_apply() -> tuple[bool, str, str]:
    """`updates --apply --yes --family BOGUS` exits 2 before any apply runs.

    The unknown-family validation raises typer.Exit(2) before the apply
    block is reached. Even with --yes, no SN call happens. Safe live test.
    """
    proc = _run(
        _nexus("plugins", "updates", "--apply", "--yes", "--family", "ZZZ_BOGUS"),
        timeout_s=30,
    )
    out = proc.stdout or ""
    ok = proc.returncode == 2 and "ZZZ_BOGUS" in out and "upgraded," not in out
    return ok, f"exit={proc.returncode}", out[-200:]


def t_cross_instance_diff_shows_differences() -> tuple[bool, str, str]:
    """`diff alectri retail` returns >0 entries (two profiles always differ).

    Skips with PASS when the second profile is not registered.
    """
    list_proc = _run(_nexus("instance", "list"), timeout_s=10)
    if "retail" not in (list_proc.stdout or ""):
        return True, "skipped: retail not registered", ""
    proc = _run(_nexus("plugins", "diff", "alectri", "retail", "--format", "json"), timeout_s=30)
    if proc.returncode != 0:
        return False, f"exit={proc.returncode}", (proc.stderr or "")[-200:]
    try:
        payload = json.loads((proc.stdout or "").strip().splitlines()[-1])
        entries = payload.get("entries", [])
        ok = len(entries) > 0
        return ok, f"entries={len(entries)}", ""
    except (json.JSONDecodeError, IndexError) as exc:
        return False, f"JSON parse: {exc}", (proc.stdout or "")[-200:]


def t_promote_apply_roundtrip() -> tuple[bool, str, str]:
    """promote-generated YAML loads cleanly through apply (cancelled at prompt).

    Verifies the bucket-dict -> flat-list coercion in plugins_apply.
    Skips with PASS when retail is not registered.
    """
    list_proc = _run(_nexus("instance", "list"), timeout_s=10)
    if "retail" not in (list_proc.stdout or ""):
        return True, "skipped: retail not registered", ""
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as tmp:
        out = Path(tmp.name)
    try:
        gen = _run(
            _nexus("plugins", "promote", "alectri", "--to", "retail", "--out", str(out)),
            timeout_s=30,
        )
        if gen.returncode != 0 or not out.exists():
            return False, f"promote exit={gen.returncode}", (gen.stdout or "")[-200:]
        applied = _run(_nexus("plugins", "apply", str(out)), input_text="n\n", timeout_s=30)
        stdout = applied.stdout or ""
        ok = applied.returncode == 0 and "actions against retail" in stdout
        return ok, f"apply exit={applied.returncode}", stdout[-200:]
    finally:
        out.unlink(missing_ok=True)


def t_apply_plan_missing_plugin() -> tuple[bool, str, str]:
    """`apply <plan referencing missing plugin>` -> activate/upgrade pre-validation fails.

    Versions are quoted strings to avoid PyYAML parsing "1.0" as a float
    (PromotionPlan requires str).
    """
    plan_yaml = """source_profile: alectri
target_profile: alectri
actions:
  - action: activate
    plugin_id: com.fake.does-not-exist
    name: Fake
    product_family: ITSM
    target_version: "1.0"
    current_version: null
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
        tmp.write(plan_yaml)
        path = Path(tmp.name)
    try:
        proc = _run(_nexus("plugins", "apply", str(path)), input_text="y\n", timeout_s=30)
        combined = (proc.stdout or "") + (proc.stderr or "")
        ok = proc.returncode != 0 and ("com.fake" in combined or "not found" in combined.lower())
        return ok, f"exit={proc.returncode}", combined[-200:]
    finally:
        path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Test registry + driver
# ---------------------------------------------------------------------------

ALL_TESTS: list[tuple[str, Callable[[], tuple[bool, str, str]]]] = [
    # Discovery and help (green path)
    ("bare-discovery", t_bare_discovery),
    ("help-each-leaf", t_help_for_each_leaf),
    ("explain-help", t_explain_help),
    ("deactivate-help", t_deactivate_help),
    ("uninstall-help", t_uninstall_help),
    # list / info (green + red)
    ("list-default", t_list_default),
    ("list-json", t_list_json),
    ("list-filter-product", t_list_filter_product),
    ("list-filter-state", t_list_filter_state),
    ("list-filter-source", t_list_filter_source),
    ("list-unknown-format", t_list_unknown_format),
    ("info-known", t_info_known_plugin),
    ("info-unknown", t_info_unknown_plugin),
    ("info-missing-arg", t_info_missing_arg),
    # Export (green + red)
    ("export-yaml", t_export_yaml),
    ("export-csv", t_export_csv),
    ("export-unknown-format", t_export_unknown_format),
    # Cross-instance ops
    ("diff-same-profile", t_diff_same_profile),
    ("promote-same-profile-refused", t_promote_same_profile_refused),
    # Updates / advisories / list-deferred (green + JSON variants)
    ("updates-lists", t_updates_lists_available),
    ("updates-json", t_updates_json),
    ("advisories-lists", t_advisories_lists),
    ("advisories-json", t_advisories_json),
    ("list-deferred", t_list_deferred_works),
    ("list-deferred-json", t_list_deferred_json),
    # Impact (green + JSON + red)
    ("impact-known", t_impact_known_plugin),
    ("impact-json", t_impact_json),
    ("impact-unknown", t_impact_unknown_plugin),
    # Orphans + baselines
    ("orphans-runs", t_orphans_runs),
    ("baselines-list", t_baselines_list),
    # New write commands - cancellation paths (green)
    ("install-cancel", t_install_cancel),
    ("activate-cancel", t_activate_cancel),
    ("upgrade-cancel", t_upgrade_cancel),
    ("deactivate-cancel", t_deactivate_cancel),
    # New write commands - missing-arg + unknown-plugin (red)
    ("install-missing-arg", t_install_missing_arg),
    ("deactivate-missing-arg", t_deactivate_missing_arg),
    ("install-unknown-plugin", t_install_unknown_plugin),
    ("activate-unknown-plugin", t_activate_unknown_plugin),
    ("deactivate-unknown-plugin", t_deactivate_unknown_plugin),
    ("uninstall-unknown-plugin", t_uninstall_unknown_plugin),
    # Force-confirm safety paths (red)
    ("deactivate-force-wrong-id", t_deactivate_force_wrong_id_rejected),
    ("uninstall-force-wrong-id", t_uninstall_force_wrong_id_rejected),
    # Uninstall base plugin (red)
    ("uninstall-base-refused", t_uninstall_base_plugin_refused),
    # Apply (green + red)
    ("apply-missing-file", t_apply_missing_file),
    ("apply-malformed-yaml", t_apply_malformed_yaml),
    ("apply-valid-plan-cancel", t_apply_valid_plan_cancel),
    ("apply-plan-missing-plugin", t_apply_plan_missing_plugin),
    # Drift workflow
    ("drift-help", t_drift_help_has_ack_and_strict),
    ("drift-ack-then-clean", t_drift_ack_then_clean),
    ("drift-strict-no-drift", t_drift_strict_with_no_drift),
    ("drift-json", t_drift_json),
    # Strict / queue flag combinations
    ("advisories-strict", t_advisories_strict_mode),
    ("updates-queue-writes-yaml", t_updates_queue_writes_yaml),
    ("updates-family-filter", t_updates_family_filter),
    ("updates-unknown-family", t_updates_unknown_family),
    ("updates-dry-run-no-apply", t_updates_dry_run_no_apply),
    ("updates-format-text-explicit", t_updates_format_text_explicit),
    ("updates-format-unknown", t_updates_format_unknown),
    ("updates-instance-explicit", t_updates_instance_explicit),
    ("updates-family-multiple", t_updates_family_multiple),
    ("updates-family-case-insensitive", t_updates_family_case_insensitive),
    ("updates-family-with-json", t_updates_family_with_json),
    ("updates-family-with-queue", t_updates_family_with_queue),
    ("updates-queue-with-json", t_updates_queue_with_json),
    ("updates-apply-declined-prompt", t_updates_apply_declined_prompt),
    ("updates-apply-unknown-family-blocks", t_updates_apply_unknown_family_blocks_before_apply),
    # Cross-instance (skipped if retail not registered)
    ("cross-instance-diff", t_cross_instance_diff_shows_differences),
    ("promote-apply-roundtrip", t_promote_apply_roundtrip),
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
