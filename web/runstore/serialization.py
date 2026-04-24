from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from core.policy import AgentNode, Edge, ExecutionGraph, Node, ToolNode
from web.utils import to_jsonable


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event_name(event: Dict[str, Any]) -> str:
    event_type = str(event.get("event_type") or "message").strip()
    return event_type.replace(" ", ".")


def serialize_node(node: Node) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "node_id": node.node_id,
        "node_name": node.node_name,
        "node_type": node.__class__.__name__,
        "next_node_ids": list(node.next_node_ids),
        "metadata": to_jsonable(node.metadata),
    }
    if isinstance(node, AgentNode):
        payload.update(
            {
                "agent_id": node.agent_id,
                "additional_prompt": node.additional_prompt,
            }
        )
    elif isinstance(node, ToolNode):
        payload.update(
            {
                "tool_name": node.tool_name,
                "input_mapping": to_jsonable(node.input_mapping),
            }
        )
    return payload


def serialize_edge(edge: Edge) -> Dict[str, Any]:
    return {
        "from_node_id": edge.from_node_id,
        "to_node_id": edge.to_node_id,
        "label": edge.label,
        "condition": edge.condition,
        "priority": edge.priority,
    }


def serialize_graph_snapshot(graph: ExecutionGraph) -> Dict[str, Any]:
    return {
        "graph_name": graph.graph_name,
        "graph_kind": getattr(graph, "graph_kind", "execution"),
        "entry_node_id": graph.entry_node_id,
        "exit_node_id": graph.exit_node_id,
        "node_count": len(graph.nodes),
        "edge_count": len(graph.edges),
        "nodes": [serialize_node(node) for node in sorted(graph.nodes.values(), key=lambda item: item.node_id)],
        "edges": [serialize_edge(edge) for edge in sorted(
            graph.edges,
            key=lambda item: (item.from_node_id, item.priority, item.to_node_id, item.label or "", item.condition or ""),
        )],
    }


def serialize_swarm_summary(swarm) -> Dict[str, Any]:
    validation = swarm.core.check_execution_graph_available()
    return {
        "swarm_name": swarm.manifest.swarm_name,
        "package_path": str(swarm.package_path),
        "manifest_path": str(swarm.manifest_path),
        "graph_file": swarm.manifest.graph_file,
        "agent_count": len(swarm.core.list_agents()),
        "skill_count": len(swarm.core.list_skills()),
        "tool_count": len(swarm.core.tools),
        "graph_attached": swarm.core.get_execution_graph() is not None,
        "graph_valid": validation.is_valid,
        "graph_errors": validation.errors,
        "graph_warnings": validation.warnings,
    }


def serialize_swarm_detail(swarm) -> Dict[str, Any]:
    payload = serialize_swarm_summary(swarm)
    payload["agent_files"] = list(swarm.manifest.agent_files)
    graph_getter = getattr(swarm.core, "get_agent_graph", None)
    graph = graph_getter() if callable(graph_getter) else swarm.core.get_execution_graph()
    payload["graph"] = serialize_graph_snapshot(graph) if graph is not None else None
    return payload
