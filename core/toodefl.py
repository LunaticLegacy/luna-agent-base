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


class ToolDefinition(ABC):
    """Standard abstract base class for a runtime tool."""

    tool_name: str
    description: str = ""
    enabled: bool = True

    def __init__(self, tool_name: str, description: str = "") -> None:
        self.tool_name = tool_name
        self.description = description

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
