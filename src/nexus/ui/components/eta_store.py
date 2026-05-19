# src/nexus/ui/components/eta_store.py
# JSONL-backed history of per-family plugin-upgrade durations for ETA priors.
# Author: Pierre Grothe
# Date: 2026-05-18

"""Append-only JSONL store of completed-upgrade durations per plugin family.

Each successful ``PluginExecutor.upgrade`` records a sample. The CLI's
``WeightedETAColumn`` reads recent samples for the same family to seed
the EMA blend used by the in-flight progress bar.

In-process writes are serialised by a per-path module-level lock --
two threads writing to the same cache file always produce well-formed
lines. Cross-process atomicity is NOT guaranteed on Windows (POSIX
``O_APPEND`` semantics differ from Windows ``WriteFile``); two
concurrent ``nexus`` invocations on the same machine MAY interleave
JSONL lines. v1 covers the in-process case only; ADR can re-open if
production traffic warrants. Malformed lines (from a process killed
mid-write) are silently skipped on read.
"""

import json
import threading
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from nexus.config.types import UtcDatetime

__all__ = ["EmaPriorStore", "EmaSample"]

_MAX_ENTRIES = 1000
_PATH_LOCKS: dict[str, threading.Lock] = {}
_REGISTRY_LOCK = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    """Return the process-wide lock guarding writes to ``path``.

    Args:
        path: Cache file path used as the lock's identity key.

    Returns:
        A ``threading.Lock`` shared by all callers writing to ``path``.
    """
    key = str(path.resolve())
    with _REGISTRY_LOCK:
        lock = _PATH_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _PATH_LOCKS[key] = lock
        return lock


class EmaSample(BaseModel):
    """A single completed-upgrade duration record.

    Attributes:
        family: Plugin family identifier (e.g., ``com.snc.incident``).
        duration_s: Wall-clock seconds the upgrade took from submit to
            terminal SN poll cycle.
        ts: UTC timestamp the record was written.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    family: str
    duration_s: float
    ts: UtcDatetime


class EmaPriorStore(BaseModel):
    """JSONL-backed per-family duration history.

    Attributes:
        cache_path: Path to the ``eta_prior.jsonl`` file. Parent
            directory is created on first ``record()`` call.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    cache_path: Path

    def record(self, family: str, duration_s: float) -> None:
        """Append a sample for ``family`` to the JSONL store.

        Creates the parent directory if missing. Safe under in-process
        multi-threaded writes.

        Args:
            family: Plugin family identifier.
            duration_s: Measured upgrade duration in seconds.
        """
        sample = EmaSample(family=family, duration_s=duration_s, ts=datetime.now(UTC))
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        line = sample.model_dump_json() + "\n"
        with _lock_for(self.cache_path), self.cache_path.open("a", encoding="utf-8") as handle:
            handle.write(line)

    def load(self, family: str) -> tuple[float, ...]:
        """Return up to the 1000 most-recent durations for ``family``.

        Malformed JSONL lines are silently skipped. Missing file returns
        an empty tuple.

        Args:
            family: Plugin family identifier to filter on.

        Returns:
            Tuple of durations in file order, capped at the 1000 most
            recent entries for this family.
        """
        if not self.cache_path.exists():
            return ()
        durations: list[float] = []
        with self.cache_path.open("r", encoding="utf-8") as handle:
            for raw in handle:
                line = raw.strip()
                if not line:
                    continue
                try:
                    sample = EmaSample.model_validate_json(line)
                except json.JSONDecodeError, ValidationError:
                    continue
                if sample.family == family:
                    durations.append(sample.duration_s)
        return tuple(durations[-_MAX_ENTRIES:])
