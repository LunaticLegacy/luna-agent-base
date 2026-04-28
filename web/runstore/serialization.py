"""图结构与 swarm 元信息的序列化工具。

将 ExecutionGraph、Node、Edge 以及 swarm 的运行时摘要转换为
JSON-safe 的字典，供路由响应与快照持久化使用。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from core.policy import AgentNode, Edge, ExecutionGraph, Node, ToolNode
from web.utils import to_jsonable


def _utc_now_iso() -> str:
    """返回当前 UTC 时间的 ISO 格式字符串。"""
    return datetime.now(timezone.utc).isoformat()


def _event_name(event: Dict[str, Any]) -> str:
    """将事件类型中的空格替换为点号，生成 SSE 事件名。

    Args:
        event: 包含 event_type 字段的事件字典。

    Returns:
        规范化的事件名。
    """
    event_type = str(event.get("event_type") or "message").strip()
    return event_type.replace(" ", ".")


def serialize_node(node: Node) -> Dict[str, Any]:
    """将单个节点序列化为字典，保留类型特定字段。

    对 AgentNode 补充 blueprint_ref、agent_id 等；
    对 ToolNode 补充 tool_name 与 input_mapping。

    Args:
        node: 执行图中的节点实例。

    Returns:
        节点字典。
    """
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
                "blueprint_ref": node.blueprint_ref,
                "agent_id": node.agent_id,
                "additional_prompt": node.additional_prompt,
                "instance_policy": node.instance_policy,
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
    """将边序列化为字典。

    Args:
        edge: 执行图中的边实例。

    Returns:
        边字典。
    """
    return {
        "from_node_id": edge.from_node_id,
        "to_node_id": edge.to_node_id,
        "label": edge.label,
        "condition": edge.condition,
        "priority": edge.priority,
    }


def serialize_graph_snapshot(graph: ExecutionGraph) -> Dict[str, Any]:
    """将整张执行图序列化为快照字典。

    节点按 node_id 排序，边按 (from, priority, to, label, condition) 排序，
    确保输出稳定，便于前端做差异比对。

    Args:
        graph: 执行图实例。

    Returns:
        图快照字典。
    """
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
    """生成 swarm 的运行时摘要。

    Args:
        swarm: 已加载的 swarm 实例。

    Returns:
        包含基本信息与图校验结果的字典。
    """
    validation = swarm.core.check_execution_graph_available()
    return {
        "swarm_name": swarm.manifest.swarm_name,
        "package_path": str(swarm.package_path),
        "manifest_path": str(swarm.manifest_path),
        "graph_file": swarm.manifest.graph_file,
        "agent_count": len(swarm.core.list_agents()),
        "skill_count": len(swarm.core.list_skills()),
        "tool_count": len(swarm.core.tools),
        "api_count": len(getattr(swarm.core, "apis", {})),
        "graph_attached": swarm.core.get_execution_graph() is not None,
        "graph_valid": validation.is_valid,
        "graph_errors": validation.errors,
        "graph_warnings": validation.warnings,
    }


def serialize_swarm_detail(swarm) -> Dict[str, Any]:
    """生成 swarm 的详细视图，包含全局变量与图快照。

    Args:
        swarm: 已加载的 swarm 实例。

    Returns:
        在 summary 基础上追加 agent_files、global_variables 与 graph 的字典。
    """
    payload = serialize_swarm_summary(swarm)
    payload["agent_files"] = list(swarm.manifest.agent_files)
    globals_config = getattr(swarm.manifest, "global_variables", None)
    globals_values = getattr(globals_config, "values", {}) if globals_config is not None else {}
    globals_visibility = getattr(globals_config, "visibility", {}) if globals_config is not None else {}
    payload["global_variables"] = {
        "values": to_jsonable(dict(globals_values)),
        "visibility": {
            key: list(value)
            for key, value in globals_visibility.items()
        },
    }
    graph_getter = getattr(swarm.core, "get_agent_graph", None)
    graph = graph_getter() if callable(graph_getter) else swarm.core.get_execution_graph()
    payload["graph"] = serialize_graph_snapshot(graph) if graph is not None else None
    return payload
