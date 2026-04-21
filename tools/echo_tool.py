from __future__ import annotations

from typing import Any, Dict, Optional

from core.toodefl import ToolContext, ToolDefinition


class EchoTool(ToolDefinition):
    """Return the received payload for debugging and wiring checks."""

    def __init__(self) -> None:
        super().__init__(tool_name="echo", description="Echo the input payload.")

    async def execute(
        self,
        arguments: Dict[str, Any],
        *,
        context: Optional[ToolContext] = None,
    ) -> Any:
        return {
            "echo": arguments,
            "context": {
                "agent_id": context.agent_id if context else None,
                "node_id": context.node_id if context else None,
                "rounds": context.rounds if context else None,
            },
        }


TOOL = EchoTool()
