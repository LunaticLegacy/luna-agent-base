from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from core import AgentNode, ExecutionGraph, Node, ToolNode
from core.toodefl import ToolContext, ToolDefinition


class GraphEditorTool(ToolDefinition):
    """Edit the live execution graph during runtime."""

    def __init__(self) -> None:
        super().__init__(
            tool_name="graph_editor",
            description="Modify the live execution graph.",
        )

    async def execute(
        self,
        arguments: Dict[str, Any],
        *,
        context: Optional[ToolContext] = None,
    ) -> Any:
        if context is None or context.graph is None:
            raise ValueError("graph_editor requires a runtime graph context.")

        graph = context.graph
        if not isinstance(graph, ExecutionGraph):
            raise ValueError("graph_editor received an invalid graph object.")

        normalized = self._normalize_arguments(arguments)
        action = str(normalized.get("action", "")).strip()
        if not action:
            raise ValueError("graph_editor requires an 'action'.")

        if action == "add_agent_node":
            node = AgentNode(
                node_id=int(normalized["node_id"]),
                node_name=str(normalized["node_name"]),
                agent_id=str(normalized["agent_id"]),
                additional_prompt=normalized.get("additional_prompt"),
                next_node_ids=list(normalized.get("next_node_ids", [])),
            )
            graph.add_node(node)
        elif action == "add_tool_node":
            node = ToolNode(
                node_id=int(normalized["node_id"]),
                node_name=str(normalized["node_name"]),
                tool_name=str(normalized["tool_name"]),
                input_mapping=dict(normalized.get("input_mapping", {})),
                next_node_ids=list(normalized.get("next_node_ids", [])),
            )
            graph.add_node(node)
        elif action == "remove_node":
            graph.remove_node(int(normalized["node_id"]))
        elif action == "replace_next":
            graph.replace_next(
                int(normalized["from_node_id"]),
                [int(item) for item in normalized.get("to_node_ids", [])],
            )
        elif action == "add_edge":
            graph.add_edge(int(normalized["from_node_id"]), int(normalized["to_node_id"]))
        elif action == "remove_edge":
            graph.remove_edge(int(normalized["from_node_id"]), int(normalized["to_node_id"]))
        elif action == "set_entry":
            graph.set_entry(int(normalized["node_id"]))
        elif action == "set_exit":
            graph.set_exit(int(normalized["node_id"]))
        else:
            raise ValueError(f"Unknown graph_editor action: {action}")

        return {
            "success": True,
            "action": action,
            "graph_name": graph.graph_name,
            "node_count": len(graph.nodes),
            "entry_node_id": graph.entry_node_id,
            "exit_node_id": graph.exit_node_id,
            "next_node_id": normalized.get("next_node_id"),
        }

    def _normalize_arguments(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if "action" in arguments:
            return dict(arguments)

        raw_input = arguments.get("input")
        if isinstance(raw_input, dict):
            return dict(raw_input)
        if isinstance(raw_input, str) and raw_input.strip():
            try:
                parsed = json.loads(raw_input)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "graph_editor expected JSON input when no direct action was provided."
                ) from exc
            if not isinstance(parsed, dict):
                raise ValueError("graph_editor JSON input must decode to an object.")
            return parsed
        raise ValueError("graph_editor requires either direct arguments or JSON input.")


TOOL = GraphEditorTool()
