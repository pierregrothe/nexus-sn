# tests/fakes/fake_claude_config.py
# ClaudeCodeConfigReader test double. Returns a pre-built config.
# Author: Pierre Grothe
# Date: 2026-05-08
"""FakeClaudeCodeConfig: real fake (no mocks) for ClaudeCodeConfigReader."""

from dataclasses import dataclass

from nexus.capabilities.claude_config import ClaudeCodeConfig

__all__ = ["FakeClaudeCodeConfig"]


@dataclass(slots=True)
class FakeClaudeCodeConfig:
    """Returns a pre-built ClaudeCodeConfig from .read()."""

    config: ClaudeCodeConfig

    def read(self) -> ClaudeCodeConfig:
        """Return the stored config."""
        return self.config
