from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Set


@dataclass
class ToolContext:
    """Context passed into a tool execution."""

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
        return capability in self.capabilities


def require_tool_capability(context: Optional[ToolContext], capability: str, tool_name: str) -> None:
    """Reject a high-risk tool call unless its context explicitly grants a capability."""
    if context is not None and context.has_capability(capability):
        return
    raise PermissionError(f"Tool '{tool_name}' requires capability '{capability}'.")


def normalize_capabilities(raw: Iterable[str] | None) -> Set[str]:
    return {str(item).strip() for item in (raw or []) if str(item).strip()}


class ToolDefinition(ABC):
    """Standard abstract base class for a runtime tool."""

    tool_name: str
    description: str = ""
    enabled: bool = True
    schema: Optional[Dict[str, Any]] = None

    def __init__(self, tool_name: str, description: str = "", schema: Optional[Dict[str, Any]] = None) -> None:
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
        """Execute the tool with structured arguments."""

    def validate(self) -> None:
        """Hook for validating the tool definition before registration."""

    def is_available(self) -> bool:
        """Return whether the tool can currently be used."""
        return self.enabled

    def get_openai_schema(self) -> Optional[Dict[str, Any]]:
        """Return an OpenAI-compatible function schema for this tool."""
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
