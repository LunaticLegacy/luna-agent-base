"""Runtime execution graph editing tool.

Modify the live execution graph of a specific swarm.
"""

from __future__ import annotations

from typing import Any, Dict, List

from modules.llm_fetcher.swarm.swarm import AgentSwarm
from modules.llm_fetcher.tool import Tool


def create_graph_editor_tools(swarm: AgentSwarm) -> List[Tool]:
    """Create graph editor tools bound to an :class:`AgentSwarm`.

    Args:
        swarm: The swarm whose execution graph will be edited.
    """

    async def _graph_editor(**kwargs: Any) -> Any:
        graph = swarm.execution_graph
        action = str(kwargs.get("action", "")).strip().lower()
        if not action:
            raise ValueError("graph_editor requires an 'action'.")

        if action == "connect" or action == "add_edge":
            source_id = str(kwargs.get("source_id", kwargs.get("from_node_id", "")))
            target_id = str(kwargs.get("target_id", kwargs.get("to_node_id", "")))
            label = kwargs.get("label")
            graph.connect(source_id, target_id, label)
            return {
                "success": True,
                "action": "connect",
                "source_id": source_id,
                "target_id": target_id,
                "label": label,
            }

        if action == "disconnect" or action == "remove_edge":
            source_id = str(kwargs.get("source_id", kwargs.get("from_node_id", "")))
            target_id = str(kwargs.get("target_id", kwargs.get("to_node_id", "")))
            label = kwargs.get("label")
            graph.disconnect(source_id, target_id, label)
            return {
                "success": True,
                "action": "disconnect",
                "source_id": source_id,
                "target_id": target_id,
                "label": label,
            }

        if action == "remove_node":
            node_id = str(kwargs.get("node_id", ""))
            graph.remove_node(node_id)
            return {
                "success": True,
                "action": "remove_node",
                "node_id": node_id,
            }

        if action == "update_agent_prompt":
            node_id = str(kwargs.get("node_id", ""))
            system_prompt = str(kwargs.get("system_prompt", ""))
            graph.update_agent_prompt(node_id, system_prompt)
            return {
                "success": True,
                "action": "update_agent_prompt",
                "node_id": node_id,
            }

        if action == "add_tool_to_agent":
            node_id = str(kwargs.get("node_id", ""))
            tool_name = str(kwargs.get("tool_name", ""))
            graph.add_tool_to_agent(node_id, tool_name)
            return {
                "success": True,
                "action": "add_tool_to_agent",
                "node_id": node_id,
                "tool_name": tool_name,
            }

        if action == "remove_tool_from_agent":
            node_id = str(kwargs.get("node_id", ""))
            tool_name = str(kwargs.get("tool_name", ""))
            graph.remove_tool_from_agent(node_id, tool_name)
            return {
                "success": True,
                "action": "remove_tool_from_agent",
                "node_id": node_id,
                "tool_name": tool_name,
            }

        raise ValueError(f"Unknown graph_editor action: {action}")

    return [
        Tool(
            name="graph_editor",
            description="Modify the live execution graph (connect, disconnect, remove node, update prompt, manage agent tools).",
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "connect",
                            "disconnect",
                            "remove_node",
                            "update_agent_prompt",
                            "add_tool_to_agent",
                            "remove_tool_from_agent",
                        ],
                        "description": "Graph mutation action.",
                    },
                    "source_id": {"type": "string"},
                    "target_id": {"type": "string"},
                    "from_node_id": {"type": "string"},
                    "to_node_id": {"type": "string"},
                    "node_id": {"type": "string"},
                    "label": {"type": "string"},
                    "system_prompt": {"type": "string"},
                    "tool_name": {"type": "string"},
                },
                "required": ["action"],
            },
            handler=_graph_editor,
        ),
    ]
