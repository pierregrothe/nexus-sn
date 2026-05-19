# tests/test_ema_prior_store.py
# Tests for EmaPriorStore JSONL persistence + concurrent in-process writes.
# Author: Pierre Grothe
# Date: 2026-05-18

"""Tests for :mod:`nexus.ui.components.eta_store`.

Covers: JSONL append, mkdir-or-exist, family filtering, 1000-entry cap,
malformed-line tolerance, in-process multi-thread safety, frozen
Pydantic strictness.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from nexus.ui.components.eta_store import EmaPriorStore, EmaSample


def test_record_appends_jsonl_line_with_utc_timestamp(tmp_path: Path) -> None:
    store = EmaPriorStore(cache_path=tmp_path / "eta.jsonl")
    store.record("com.snc.x", duration_s=42.0)
    lines = (tmp_path / "eta.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["family"] == "com.snc.x"
    assert payload["duration_s"] == 42.0
    assert payload["ts"].endswith("Z") or "+00:00" in payload["ts"]


def test_record_creates_cache_dir_when_missing(tmp_path: Path) -> None:
    cache_path = tmp_path / "deep" / "nested" / "eta.jsonl"
    store = EmaPriorStore(cache_path=cache_path)
    store.record("com.snc.x", duration_s=1.0)
    assert cache_path.exists()
    assert cache_path.parent.is_dir()


def test_load_filters_by_family(tmp_path: Path) -> None:
    store = EmaPriorStore(cache_path=tmp_path / "eta.jsonl")
    store.record("A", duration_s=10.0)
    store.record("B", duration_s=20.0)
    store.record("A", duration_s=30.0)
    store.record("B", duration_s=40.0)
    store.record("A", duration_s=50.0)
    assert store.load("A") == (10.0, 30.0, 50.0)
    assert store.load("B") == (20.0, 40.0)


def test_load_returns_empty_tuple_when_file_missing(tmp_path: Path) -> None:
    store = EmaPriorStore(cache_path=tmp_path / "absent.jsonl")
    assert store.load("anything") == ()


def test_load_caps_at_1000_entries(tmp_path: Path) -> None:
    store = EmaPriorStore(cache_path=tmp_path / "eta.jsonl")
    for i in range(1500):
        store.record("A", duration_s=float(i))
    samples = store.load("A")
    assert len(samples) == 1000
    assert samples[0] == 500.0
    assert samples[-1] == 1499.0


def test_load_skips_malformed_jsonl_lines(tmp_path: Path) -> None:
    path = tmp_path / "eta.jsonl"
    path.write_text(
        '{"family":"A","duration_s":1.0,"ts":"2026-01-01T00:00:00Z"}\n'
        '{"family":"A","duration_s":2.0,"ts":"2026-01-01T00:00:01Z"}\n'
        "{partial truncated line\n",
        encoding="utf-8",
    )
    store = EmaPriorStore(cache_path=path)
    assert store.load("A") == (1.0, 2.0)


def test_load_skips_lines_failing_pydantic_validation(tmp_path: Path) -> None:
    path = tmp_path / "eta.jsonl"
    path.write_text(
        '{"family":"A","duration_s":1.0,"ts":"2026-01-01T00:00:00Z"}\n'
        '{"family":"A","unknown_field":"x","ts":"2026-01-01T00:00:01Z"}\n',
        encoding="utf-8",
    )
    store = EmaPriorStore(cache_path=path)
    assert store.load("A") == (1.0,)


def test_load_skips_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "eta.jsonl"
    path.write_text(
        '{"family":"A","duration_s":1.0,"ts":"2026-01-01T00:00:00Z"}\n'
        "\n"
        '{"family":"A","duration_s":2.0,"ts":"2026-01-01T00:00:02Z"}\n',
        encoding="utf-8",
    )
    store = EmaPriorStore(cache_path=path)
    assert store.load("A") == (1.0, 2.0)


def test_record_concurrent_threads_preserve_all_records(tmp_path: Path) -> None:
    store = EmaPriorStore(cache_path=tmp_path / "eta.jsonl")
    barrier = threading.Barrier(2)

    def worker(family: str) -> None:
        barrier.wait()
        for i in range(50):
            store.record(family, duration_s=float(i))

    threads = [
        threading.Thread(target=worker, args=("X",)),
        threading.Thread(target=worker, args=("X",)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(store.load("X")) == 100


def test_emasample_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        EmaSample.model_validate(
            {
                "family": "A",
                "duration_s": 1.0,
                "ts": datetime.now(UTC),
                "rogue_field": "x",
            }
        )


def test_emasample_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError):
        EmaSample(family="A", duration_s=1.0, ts=datetime(2026, 1, 1))


def test_emaprior_store_rejects_extra_fields(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        EmaPriorStore.model_validate({"cache_path": tmp_path / "eta.jsonl", "rogue_field": "x"})
