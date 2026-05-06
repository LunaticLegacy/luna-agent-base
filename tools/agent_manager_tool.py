"""Runtime agent lifecycle management tool.

Create or destroy agents inside a specific swarm.
"""

from __future__ import annotations

from typing import Any, Dict, List

from modules.llm_fetcher.swarm.swarm import AgentSwarm
from modules.llm_fetcher.tool import Tool


def create_agent_manager_tools(swarm: AgentSwarm) -> List[Tool]:
    """Create agent manager tools bound to an :class:`AgentSwarm`.

    Args:
        swarm: The swarm whose agents will be managed.
    """

    async def _agent_manager(**kwargs: Any) -> Any:
        action = str(kwargs.get("action", "")).strip().lower()
        if not action:
            raise ValueError("agent_manager requires an 'action'.")

        if action in {"create", "create_agent", "spawn", "spawn_agent"}:
            node_id = str(kwargs.get("node_id", "")).strip()
            if not node_id:
                raise ValueError("agent_manager create requires 'node_id'.")
            system_prompt = str(kwargs.get("system_prompt", kwargs.get("character_prompt", ""))).strip()
            if not system_prompt:
                raise ValueError("agent_manager create requires 'system_prompt' (or 'character_prompt').")

            tool_names = kwargs.get("tool_names", [])
            extra_tools = []
            if isinstance(tool_names, list):
                for tn in tool_names:
                    if tn in swarm.tool_registry._tools:
                        extra_tools.append(swarm.tool_registry._tools[tn])

            swarm.add_agent(
                node_id=node_id,
                system_prompt=system_prompt,
                extra_tools=extra_tools,
            )
            return {
                "success": True,
                "action": "create_agent",
                "node_id": node_id,
            }

        if action in {"destroy", "destroy_agent", "remove", "remove_agent", "delete", "delete_agent"}:
            node_id = str(kwargs.get("node_id", kwargs.get("agent_id", ""))).strip()
            if not node_id:
                raise ValueError("agent_manager destroy requires 'node_id' (or 'agent_id').")
            swarm.remove_agent(node_id)
            return {
                "success": True,
                "action": "destroy_agent",
                "node_id": node_id,
            }

        raise ValueError(f"Unknown agent_manager action: {action}")

    return [
        Tool(
            name="agent_manager",
            description="Create or destroy agents inside the current swarm.",
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["create_agent", "destroy_agent"],
                        "description": "Action to perform.",
                    },
                    "node_id": {"type": "string", "description": "Unique node ID for the agent in the swarm graph."},
                    "agent_id": {"type": "string", "description": "Alias for node_id (legacy)."},
                    "system_prompt": {"type": "string"},
                    "character_prompt": {"type": "string", "description": "Alias for system_prompt."},
                    "tool_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Names of global tools to attach to the new agent.",
                    },
                },
                "required": ["action"],
            },
            handler=_agent_manager,
        ),
    ]
