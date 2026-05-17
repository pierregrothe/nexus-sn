# tests/test_check_file_sizes.py
# Tests for scripts/check_file_sizes.py -- the ADR-023 enforcement script.
# Author: Pierre Grothe
# Date: 2026-05-16
"""Tests for the file-size enforcement script.

Drives the script via its public functions (``_check``, ``_load_baseline``)
rather than through ``main()``+sys.argv so the tests stay deterministic
and do not depend on the repository's current file layout.
"""

import json
from pathlib import Path

import pytest

from scripts.check_file_sizes import _check, _load_baseline

__all__: list[str] = []


def _write(path: Path, lines: int) -> None:
    """Write ``lines`` newline-separated stub lines to ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(f"line {i}" for i in range(lines)), encoding="utf-8")


def test_check_files_under_limit_produces_no_violations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A file at or below the limit is silently accepted."""
    monkeypatch.setattr("scripts.check_file_sizes.REPO_ROOT", tmp_path)
    src = tmp_path / "src" / "nexus" / "ok.py"
    _write(src, 100)
    violations = _check(tmp_path / "src" / "nexus", limit=800, baseline={})
    assert violations == []


def test_check_files_over_limit_flagged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A file above the limit and absent from baseline is reported."""
    monkeypatch.setattr("scripts.check_file_sizes.REPO_ROOT", tmp_path)
    src = tmp_path / "src" / "nexus" / "big.py"
    _write(src, 900)
    violations = _check(tmp_path / "src" / "nexus", limit=800, baseline={})
    assert len(violations) == 1
    assert "big.py" in violations[0]
    assert "900" in violations[0]
    assert "ADR-023" in violations[0]


def test_check_baselined_file_within_baseline_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A grandfathered file at or below its recorded baseline is accepted."""
    monkeypatch.setattr("scripts.check_file_sizes.REPO_ROOT", tmp_path)
    src = tmp_path / "src" / "nexus" / "cli.py"
    _write(src, 1500)
    baseline = {"src/nexus/cli.py": 1500}
    violations = _check(tmp_path / "src" / "nexus", limit=800, baseline=baseline)
    assert violations == []


def test_check_baselined_file_growing_past_baseline_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A grandfathered file that exceeds its baseline is reported."""
    monkeypatch.setattr("scripts.check_file_sizes.REPO_ROOT", tmp_path)
    src = tmp_path / "src" / "nexus" / "cli.py"
    _write(src, 1501)
    baseline = {"src/nexus/cli.py": 1500}
    violations = _check(tmp_path / "src" / "nexus", limit=800, baseline=baseline)
    assert len(violations) == 1
    assert "1501" in violations[0]
    assert "baseline 1500" in violations[0]


def test_check_baselined_file_shrinking_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A grandfathered file is free to shrink below its baseline."""
    monkeypatch.setattr("scripts.check_file_sizes.REPO_ROOT", tmp_path)
    src = tmp_path / "src" / "nexus" / "cli.py"
    _write(src, 1200)
    baseline = {"src/nexus/cli.py": 1500}
    violations = _check(tmp_path / "src" / "nexus", limit=800, baseline=baseline)
    assert violations == []


def test_load_baseline_returns_empty_when_file_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing baseline file yields an empty mapping, not an error."""
    monkeypatch.setattr("scripts.check_file_sizes.BASELINE_PATH", tmp_path / "absent.json")
    assert _load_baseline() == {}


def test_load_baseline_parses_well_formed_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A well-formed baseline file is read back as ``str -> int``."""
    path = tmp_path / ".file-size-baseline.json"
    path.write_text(
        json.dumps({"version": "1", "files": {"src/nexus/cli.py": 4478}}),
        encoding="utf-8",
    )
    monkeypatch.setattr("scripts.check_file_sizes.BASELINE_PATH", path)
    assert _load_baseline() == {"src/nexus/cli.py": 4478}


def test_load_baseline_rejects_missing_files_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A baseline JSON without ``files`` key fails loud."""
    path = tmp_path / ".file-size-baseline.json"
    path.write_text(json.dumps({"version": "1"}), encoding="utf-8")
    monkeypatch.setattr("scripts.check_file_sizes.BASELINE_PATH", path)
    with pytest.raises(ValueError, match="files"):
        _load_baseline()


def test_check_excludes_pycache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``__pycache__`` directories are skipped even if they contain .py files."""
    monkeypatch.setattr("scripts.check_file_sizes.REPO_ROOT", tmp_path)
    cache_file = tmp_path / "src" / "nexus" / "__pycache__" / "x.py"
    _write(cache_file, 5000)
    violations = _check(tmp_path / "src" / "nexus", limit=800, baseline={})
    assert violations == []
