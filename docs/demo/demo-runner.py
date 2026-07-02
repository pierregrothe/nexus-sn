# docs/demo/demo-runner.py
# Two-phase asciinema v2 .cast generator: capture then assemble.
# Author: Pierre Grothe
# Date: 2026-06-11
"""Build one .cast file per act of the Core SC pre-demo briefing.

Phase 1 (capture): run nexus commands in the current shell, save raw
output to docs/demo/capture/<act>/<cmd>.txt.

Phase 2 (assemble): read captured outputs, build per-act .cast files
with simulated typing and section banners.

Usage:
    # Capture outputs for all acts (run with fresh tokens)
    python docs/demo/demo-runner.py capture

    # Capture a single act
    python docs/demo/demo-runner.py capture --story 2

    # Assemble cast files from captures
    python docs/demo/demo-runner.py assemble

    # Assemble a single act
    python docs/demo/demo-runner.py assemble --story 2

    # Capture then assemble in one go
    python docs/demo/demo-runner.py all
    python docs/demo/demo-runner.py all --story 2
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

WIDTH = 180
HEIGHT = 40
TYPING_CPS = 20
PROMPT = "\r\n\033[1;32mnexus-sc\033[0m \033[36m>\033[0m "

OUT_DIR = Path("docs/demo/cast")
CAP_DIR = Path("docs/demo/capture")

ACTS: list[tuple[str, str]] = [
    ("act1-know-your-environment",   "Act 1 -- Know Your Environment"),
    ("act2-pick-the-right-instance", "Act 2 -- Pick the Right Instance"),
    ("act3-answer-hard-questions",   "Act 3 -- Answer the Hard Questions Live"),
    ("act4-data-model-question",     "Act 4 -- Answer the Data Model Question"),
    ("act5-leave-a-baseline",        "Act 5 -- Leave a Documented Baseline"),
]

# (act_index, command, display_override_or_None, post_pause)
SCRIPT: list[tuple[int, str, str | None, float]] = [
    # Act 1
    (0, "nexus status",                                         None,  3.0),
    (0, "nexus instance list",                                  None,  2.0),
    # Act 2
    (1, "nexus instance list",                                  None,  2.0),
    (1, "nexus instance use alectri",                           None,  1.5),
    (1, "nexus plugins outdated",                               None,  3.0),
    # Act 3
    (2, "nexus plugins advisories",                             None,  3.0),
    (2, "nexus plugins explain com.snc.itam",                   None,  5.0),
    (2, "nexus plugins orphans",                                None,  3.0),
    (2, "nexus plugins recommend",                              None,  5.0),
    # Act 4
    (3, "nexus schema products",                                None,  2.0),
    (3, "nexus schema erd doc-designer --profile alectri",      None,  5.0),
    # Act 5
    (4, "nexus plugins export --format yaml",                   None,  3.0),
    (4, "nexus plugins drift",                                  None,  3.0),
    (4, "nexus plugins roadmap",                                None,  5.0),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cmd_slug(cmd: str) -> str:
    """Convert a command string to a filesystem-safe filename."""
    return cmd.replace(" ", "_").replace("/", "-").replace(".", "-")[:60]


def _preflight() -> bool:
    """Return False and print guidance if any instance token is expired."""
    r = subprocess.run(
        "nexus instance list", shell=True,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if "EXPIRED" in (r.stdout + r.stderr):
        print("ERROR: instance token is EXPIRED.", flush=True)
        print("Run: nexus instance connect alectri", flush=True)
        print("     nexus instance connect retail", flush=True)
        print("Then retry immediately.", flush=True)
        return False
    return True


# ---------------------------------------------------------------------------
# Phase 1: capture
# ---------------------------------------------------------------------------


def capture_cmd(act_idx: int, cmd: str) -> Path:
    """Run one command and save its raw output to a capture file.

    Args:
        act_idx: 0-based act index.
        cmd: The command to run.

    Returns:
        Path to the written capture file.
    """
    slug, _ = ACTS[act_idx]
    dest = CAP_DIR / slug / f"{_cmd_slug(cmd)}.txt"
    dest.parent.mkdir(parents=True, exist_ok=True)

    print(f"  running: {cmd}", flush=True)
    t0 = time.monotonic()
    r = subprocess.run(
        cmd, shell=True,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=300,
    )
    elapsed = time.monotonic() - t0
    output = r.stdout + r.stderr
    dest.write_text(output, encoding="utf-8")
    print(f"  -> {elapsed:.1f}s  {len(output)} chars  saved to {dest}", flush=True)
    return dest


def capture_act(index: int) -> None:
    """Capture all commands for one act.

    Args:
        index: 0-based act index.
    """
    if not _preflight():
        raise SystemExit(1)
    _, title = ACTS[index]
    print(f"\nCapturing {title}...", flush=True)
    for act_idx, cmd, _disp, _post in SCRIPT:
        if act_idx == index:
            capture_cmd(act_idx, cmd)


def capture_all() -> None:
    """Capture all acts sequentially."""
    if not _preflight():
        raise SystemExit(1)
    for i in range(len(ACTS)):
        capture_act(i)


# ---------------------------------------------------------------------------
# Phase 2: assemble
# ---------------------------------------------------------------------------


class CastWriter:
    """Builds an asciinema v2 .cast file."""

    def __init__(self, title: str) -> None:
        """Initialise with zero clock."""
        self._events: list[tuple[float, str, str]] = []
        self._t: float = 0.0
        self._title = title

    def _emit(self, data: str, kind: str = "o") -> None:
        self._events.append((round(self._t, 4), kind, data))

    def pause(self, seconds: float) -> None:
        """Advance clock."""
        self._t += seconds

    def banner(self, title: str) -> None:
        """Emit a styled act title banner."""
        bar = "=" * (WIDTH - 4)
        text = (
            f"\r\n\033[1;38;2;0;104;177m{bar}\033[0m\r\n"
            f"  \033[1;38;2;103;178;85m{title}\033[0m\r\n"
            f"\033[1;38;2;0;104;177m{bar}\033[0m\r\n"
        )
        self._emit(text)
        self.pause(1.5)

    def type_command(self, cmd: str) -> None:
        """Simulate character-by-character typing."""
        self._emit(f"\r\n{PROMPT}")
        self.pause(0.4)
        for ch in cmd:
            self._emit(ch, "i")
            self._t += 1.0 / TYPING_CPS
        self._emit("\r\n")
        self.pause(0.3)

    def replay(self, cmd: str, display: str | None, post: float, act_idx: int) -> None:
        """Type the command, stream its captured output, then pause.

        Args:
            cmd: Actual command (used to find the capture file).
            display: Text shown while typing (defaults to cmd).
            post: Pause after output.
            act_idx: Act index for the capture file path.
        """
        slug, _ = ACTS[act_idx]
        cap_file = CAP_DIR / slug / f"{_cmd_slug(cmd)}.txt"
        self.type_command(display or cmd)

        if cap_file.exists():
            raw = cap_file.read_text(encoding="utf-8", errors="replace")
            # Stream line by line over a synthetic 2-second window
            lines = raw.splitlines(keepends=True)
            per_line = 2.0 / max(len(lines), 1)
            for line in lines:
                self._emit(line.replace("\n", "\r\n"))
                self._t += per_line
        else:
            self._emit(f"\r\n\033[33m[capture missing: {cap_file}]\033[0m\r\n")
            self._t += 0.5

        self.pause(post)

    def write(self, path: Path) -> None:
        """Write the .cast file.

        Args:
            path: Destination.
        """
        header = {
            "version": 2, "width": WIDTH, "height": HEIGHT,
            "timestamp": int(time.time()), "title": self._title,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps(header) + "\n")
            for t, kind, data in self._events:
                fh.write(json.dumps([t, kind, data]) + "\n")
        print(f"  wrote {path}  ({len(self._events)} events, {self._t:.0f}s)", flush=True)


def assemble_act(index: int) -> None:
    """Build the cast file for one act from captured outputs.

    Args:
        index: 0-based act index.
    """
    slug, title = ACTS[index]
    print(f"\nAssembling {title}...", flush=True)
    cast = CastWriter(f"NEXUS Demo -- {title}")
    cast.banner(title)
    cast.pause(0.5)
    for act_idx, cmd, disp, post in SCRIPT:
        if act_idx == index:
            cast.replay(cmd, disp, post, act_idx)
    cast.write(OUT_DIR / f"{slug}.cast")


def assemble_all() -> None:
    """Assemble all acts."""
    for i in range(len(ACTS)):
        assemble_act(i)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Dispatch capture / assemble / all."""
    parser = argparse.ArgumentParser(
        description="Generate per-act nexus demo .cast files (two-phase)"
    )
    parser.add_argument(
        "phase",
        choices=["capture", "assemble", "all"],
        help="capture: run commands; assemble: build cast files; all: both",
    )
    parser.add_argument(
        "--story", type=int, choices=[1, 2, 3, 4, 5], default=None,
        help="Act number (1-5). Omit for all acts.",
    )
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CAP_DIR.mkdir(parents=True, exist_ok=True)

    do_capture = args.phase in ("capture", "all")
    do_assemble = args.phase in ("assemble", "all")

    if do_capture:
        print("=== CAPTURE ===", flush=True)
        if args.story:
            capture_act(args.story - 1)
        else:
            capture_all()

    if do_assemble:
        print("\n=== ASSEMBLE ===", flush=True)
        if args.story:
            assemble_act(args.story - 1)
        else:
            assemble_all()

    if do_assemble:
        print("\nDone. Serve with:", flush=True)
        print("  python -m http.server 8000 --directory docs/demo", flush=True)
        print("  open http://localhost:8000/player.html", flush=True)


if __name__ == "__main__":
    main()
