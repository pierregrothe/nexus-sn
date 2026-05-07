# src/nexus/api/logging_config.py
# Rotating log file setup for the NEXUS CLI session.
# Author: Pierre Grothe
# Date: 2026-05-07
"""configure_logging: attach TimedRotatingFileHandler to the root logger."""

import logging
import logging.handlers
from pathlib import Path

from nexus.config.paths import NexusPaths

__all__ = ["configure_logging"]

_FMT = "%(asctime)s %(levelname)-8s %(name)s -- %(message)s"


def configure_logging(paths: NexusPaths, level: int = logging.INFO) -> None:
    """Attach a rotating file handler and a stderr handler to the root logger.

    Creates the logs directory if it does not exist. Keeps 7 days of daily logs.
    No-op if the root logger already has handlers (safe to call multiple times).

    Args:
        paths: NexusPaths providing the runtime directory locations.
        level: Logging level applied to all handlers (default INFO).
    """
    root = logging.getLogger()
    if root.handlers:
        return
    logs_dir: Path = paths.logs_dir
    logs_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.TimedRotatingFileHandler(
        logs_dir / "nexus.log",
        when="midnight",
        backupCount=7,
        encoding="utf-8",
    )
    fmt = logging.Formatter(_FMT)
    file_handler.setFormatter(fmt)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(stream_handler)
