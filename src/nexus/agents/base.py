# nexus/agents/base.py
# AgentProtocol and shared agent types.
# Author: Pierre Grothe
# Date: 2026-05-07

"""Base types for the agent orchestration layer."""

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

__all__ = ["AgentProtocol", "AgentResult", "ExecutionContext"]


@dataclass(slots=True, frozen=True)
class ExecutionContext:
    """Immutable context passed to every agent.

    Attributes:
        project_name: Human-readable project identifier.
        instance_url: Target ServiceNow instance URL.
        job_id: Unique identifier for this execution job.
        task_id: Identifier for the specific task being executed.
        inputs: Outputs from upstream tasks (sys_ids, etc.).
        dry_run: When True, agents plan but do not create records.
    """

    project_name: str
    instance_url: str
    job_id: str
    task_id: str
    inputs: dict[str, Any] = field(default_factory=dict[str, Any])
    dry_run: bool = False


@dataclass(slots=True)
class AgentResult:
    """Output returned by a specialist agent after completing its task.

    Attributes:
        task_id: The task this result corresponds to.
        success: True when the agent completed without errors.
        outputs: Named outputs (sys_ids, counts, etc.) for downstream tasks.
        errors: List of error messages if success is False.
        summary: Human-readable completion summary.
    """

    task_id: str
    success: bool
    outputs: dict[str, Any] = field(default_factory=dict[str, Any])
    errors: list[str] = field(default_factory=list[str])
    summary: str = ""


@runtime_checkable
class AgentProtocol(Protocol):
    """Interface every specialist agent must implement."""

    @property
    def name(self) -> str:
        """Agent identifier, e.g. 'itsm'."""
        ...

    @property
    def domain(self) -> str:
        """Product domain, e.g. 'ITSM', 'ITOM'."""
        ...

    async def run(self, context: ExecutionContext) -> AgentResult:
        """Execute the agent's task.

        Args:
            context: Immutable execution context with inputs and config.

        Returns:
            AgentResult with outputs for downstream tasks.
        """
        ...
