# src/nexus/templates/__init__.py
# Public re-exports for the templates subpackage.
# Author: Pierre Grothe
# Date: 2026-05-18
"""Template catalog sync and on-disk cache.

v1 scope: pull a manifest from a configured GitHub repo and cache it
locally. Per-template downloads, schema validation, and the apply
engine live in the 2026.06-template-library epic.
"""

from nexus.templates.errors import InvalidGitHubRepoError, TemplatesError
from nexus.templates.models import (
    CachedManifest,
    SyncSource,
    TemplateEntry,
    TemplateManifest,
)
from nexus.templates.registry import TemplateRegistry
from nexus.templates.repo_name import validate_github_repo
from nexus.templates.schemas.now_assist_skill import NowAssistSkill
from nexus.templates.schemas.workflow import Workflow, WorkflowInput, WorkflowLogic
from nexus.templates.sync import GitHubSync, GitHubTemplateClient, SyncReport

__all__ = [
    "CachedManifest",
    "GitHubSync",
    "GitHubTemplateClient",
    "InvalidGitHubRepoError",
    "NowAssistSkill",
    "SyncReport",
    "SyncSource",
    "TemplateEntry",
    "TemplateManifest",
    "TemplateRegistry",
    "TemplatesError",
    "Workflow",
    "WorkflowInput",
    "WorkflowLogic",
    "validate_github_repo",
]
