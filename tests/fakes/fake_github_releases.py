# tests/fakes/fake_github_releases.py
# Test double for GitHubReleasesClient.
# Author: Pierre Grothe
# Date: 2026-05-08
"""FakeGitHubReleasesClient: returns a configured ReleaseInfo or None."""

from dataclasses import dataclass

from nexus.updater.client import ReleaseInfo

__all__ = ["FakeGitHubReleasesClient"]


@dataclass(slots=True)
class FakeGitHubReleasesClient:
    """Returns a pre-built ReleaseInfo (or None) from .fetch_latest()."""

    info: ReleaseInfo | None = None

    def fetch_latest(self) -> ReleaseInfo | None:
        """Return the stored info."""
        return self.info
