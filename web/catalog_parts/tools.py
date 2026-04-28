"""Tool 目录构建器。

从 swarm 的工具注册表与运行事件中提取每个工具的类型、调用次数、
平均耗时与成功率，生成前端 Tool Catalog 所需的结构化数据。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .shared import _build_activity_index, _tool_schema, _tool_source_mtime, _tool_type, jsonable_text


def build_tool_catalog(
    registry,
    *,
    type_filter: Optional[str] = None,
    status: Optional[str] = None,
    q: Optional[str] = None,
    swarm_name: Optional[str] = None,
) -> Dict[str, Any]:
    """构建跨 swarm 的 Tool 目录。

    Args:
        registry: 运行时注册表。
        type_filter: 按工具类型过滤（如 "API" / "本地"）。
        status: 按状态过滤。
        q: 全文搜索关键词。
        swarm_name: 仅查询指定 swarm；None 表示全部。

    Returns:
        包含 tools 列表与 stats 聚合指标的字典。
    """
    normalized_type = str(type_filter or "").strip().lower()
    normalized_status = str(status or "").strip().lower()
    normalized_query = str(q or "").strip().lower()

    items: List[Dict[str, Any]] = []
    for loaded_swarm in registry.swarms.values():
        if swarm_name and loaded_swarm.manifest.swarm_name != swarm_name:
            continue
        graph = loaded_swarm.core.get_execution_graph()
        runs = registry.runs.list_runs(loaded_swarm.manifest.swarm_name)
        activity = _build_activity_index(runs)
        for tool_name, tool in loaded_swarm.core.tools.items():
            tool_nodes = []
            if graph is not None:
                from core.policy import ToolNode

                tool_nodes = [
                    node
                    for node in graph.nodes.values()
                    if isinstance(node, ToolNode) and node.tool_name == tool_name
                ]
            # 取第一个匹配的 ToolNode 用于关联运行统计；若无匹配则使用 -1
            node_id = tool_nodes[0].node_id if tool_nodes else -1
            entry = activity.get((loaded_swarm.manifest.swarm_name, node_id), {})
            executions = int(entry.get("executions", 0) or 0)
            completed = int(entry.get("completed", 0) or 0)
            failed = int(entry.get("failed", 0) or 0)
            avg_ms = 0
            if completed > 0:
                avg_ms = int(round(float(entry.get("total_duration_ms", 0.0)) / completed))
            elif executions > 0:
                # 有调用但未完成时，按调用次数做经验估算
                avg_ms = 80 + executions * 5
            tool_type = _tool_type(tool)
            status_value = "online" if failed == 0 else "error"
            last_call = entry.get("last_seen") or _tool_source_mtime(tool)
            item = {
                "id": f"{loaded_swarm.manifest.swarm_name}:{tool_name}",
                "name": getattr(tool, "tool_name", tool_name),
                "swarm": loaded_swarm.manifest.swarm_name,
                "type": tool_type,
                "status": status_value,
                "description": getattr(tool, "description", ""),
                "calls": executions,
                "avg_ms": avg_ms,
                "last_call": last_call,
                "success_rate": 100.0 if executions == 0 else round((completed / max(executions, 1)) * 100.0, 1),
                "error_rate": 0.0 if executions == 0 else round((failed / max(executions, 1)) * 100.0, 1),
                "created_at": _tool_source_mtime(tool),
                "schema": _tool_schema(tool),
            }
            if normalized_type and item["type"].lower() != normalized_type:
                continue
            if normalized_status and item["status"].lower() != normalized_status:
                continue
            if normalized_query:
                searchable = " ".join(
                    [
                        item["id"],
                        item["name"],
                        item["description"],
                        jsonable_text(item["schema"]),
                        item["swarm"],
                    ]
                ).lower()
                if normalized_query not in searchable:
                    continue
            items.append(item)

    stats = {
        "total": len(items),
        "available": sum(1 for item in items if item["status"] == "online"),
        "api": sum(1 for item in items if item["type"] == "API"),
        "local": sum(1 for item in items if item["type"] == "本地"),
        "today_calls": sum(int(item["calls"]) for item in items),
    }
    return {
        "tools": items,
        "stats": stats,
    }
