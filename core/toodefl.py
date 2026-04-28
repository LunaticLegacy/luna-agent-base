"""Abstract tool definition and runtime context for Angelus.

This module defines the contract that every tool must fulfil
(:class:`ToolDefinition`) and the context object that is passed into each
tool execution (:class:`ToolContext`).  It also provides helpers for
capability-based access control and capability normalisation.

Exports:
    - :class:`ToolContext`
    - :class:`ToolDefinition`
    - :func:`require_tool_capability`
    - :func:`normalize_capabilities`
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Set


@dataclass
class ToolContext:
    """Context passed into a tool execution.

    Attributes:
        agent_id: The agent that triggered this tool call.
        node_id: The execution-graph node that triggered this tool call.
        rounds: Current round counter for the active run.
        workspace_mode: Access level (``"workspace"`` or ``"full_access"``).
        workspace_root: Filesystem root for the agent's workspace.
        metadata: Free-form metadata injected by the runtime.
        core: Reference to the runtime :class:`Core` (typed loosely to avoid circular imports).
        graph: Reference to the active :class:`ExecutionGraph` (typed loosely).
        capabilities: Set of capability strings granted to this call.
    """

    agent_id: Optional[str] = None
    node_id: Optional[int] = None
    rounds: int = 0
    workspace_mode: str = "workspace"
    workspace_root: Optional[Path] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    core: Optional[Any] = None
    graph: Optional[Any] = None
    capabilities: Set[str] = field(default_factory=set)

    def has_capability(self, capability: str) -> bool:
        """Check whether *capability* was explicitly granted for this call.

        Args:
            capability: The capability string to test.

        Returns:
            ``True`` if the capability is present in :attr:`capabilities`.
        """
        return capability in self.capabilities


def require_tool_capability(context: Optional[ToolContext], capability: str, tool_name: str) -> None:
    """Reject a high-risk tool call unless its context explicitly grants a capability.

    This is the capability-gate helper used by sensitive tools (e.g. file deletion,
    network access) to enforce least-privilege execution.

    Args:
        context: The tool context for the current call.
        capability: The required capability string.
        tool_name: Human-readable tool name used in the error message.

    Raises:
        PermissionError: If *context* is ``None`` or does not contain *capability*.
    """
    if context is not None and context.has_capability(capability):
        return
    raise PermissionError(f"Tool '{tool_name}' requires capability '{capability}'.")


def normalize_capabilities(raw: Iterable[str] | None) -> Set[str]:
    """Normalise an iterable of capability strings into a clean set.

    Args:
        raw: Iterable of capability strings (may contain empty items).

    Returns:
        A set of non-empty, stripped capability strings.
    """
    return {str(item).strip() for item in (raw or []) if str(item).strip()}


class ToolDefinition(ABC):
    """Standard abstract base class for a runtime tool.

    Subclasses must implement :meth:`execute` and may override :meth:`validate`
    to perform registration-time checks.

    Attributes:
        tool_name: Unique identifier for this tool.
        description: Human-readable description shown to agents.
        enabled: Whether the tool is currently available.
        schema: JSON-Schema dictionary describing the tool's parameters.
    """

    tool_name: str
    description: str = ""
    enabled: bool = True
    schema: Optional[Dict[str, Any]] = None

    def __init__(self, tool_name: str, description: str = "", schema: Optional[Dict[str, Any]] = None) -> None:
        """Initialise the tool with its identifying metadata.

        Args:
            tool_name: Unique identifier for this tool.
            description: Human-readable description shown to agents.
            schema: JSON-Schema dictionary describing the tool's parameters.
        """
        self.tool_name = tool_name
        self.description = description
        if schema is not None:
            self.schema = schema

    @abstractmethod
    async def execute(
        self,
        arguments: Dict[str, Any],
        *,
        context: Optional[ToolContext] = None,
    ) -> Any:
        """Execute the tool with structured arguments.

        Args:
            arguments: Parsed keyword arguments matching the tool's schema.
            context: Runtime context providing workspace, capabilities, and core access.

        Returns:
            Tool-specific result (any JSON-serialisable value).
        """

    def validate(self) -> None:
        """Hook for validating the tool definition before registration.

        Raises:
            ValueError: If the tool definition is malformed.
        """

    def is_available(self) -> bool:
        """Return whether the tool can currently be used.

        Returns:
            ``True`` if :attr:`enabled` is ``True``.
        """
        return self.enabled

    def get_openai_schema(self) -> Optional[Dict[str, Any]]:
        """Return an OpenAI-compatible function schema for this tool.

        Returns:
            A dictionary in the ``{type: "function", function: {...}}`` shape,
            or ``None`` if :attr:`schema` is not set.
        """
        if self.schema is None:
            return None
        return {
            "type": "function",
            "function": {
                "name": self.tool_name,
                "description": self.description,
                "parameters": self.schema,
            },
        }
