from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ToolContext:
    """Context passed into a tool execution."""

    agent_id: Optional[str] = None
    node_id: Optional[int] = None
    rounds: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    core: Optional[Any] = None
    graph: Optional[Any] = None


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
