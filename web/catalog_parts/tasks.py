"""Task 目录构建器。

将执行图中的每个节点视为一个“任务”，结合运行事件统计构建任务目录，
支持按状态、优先级、执行者与时间范围过滤。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .shared import (
    _build_activity_index,
    _entry_active_run_ids,
    _file_mtime_iso,
    _node_status,
    _normalize_priority,
    _parse_iso_timestamp,
    jsonable_text,
)


def _build_task_item(
    *,
    swarm_name: str,
    node: Any,
    entry: Dict[str, Any],
    reference_time: str,
) -> Dict[str, Any]:
    """将单个图节点与其运行统计组装为任务条目。

    Args:
        swarm_name: 所属 swarm 名称。
        node: 图节点实例（AgentNode / ToolNode / 其他）。
        entry: 该节点在 activity index 中的统计字典。
        reference_time: 用于填充 created_at 的基准时间。

    Returns:
        任务详情字典。
    """
    from core.policy import AgentNode

    executions = int(entry.get("executions", 0) or 0)
    completed = int(entry.get("completed", 0) or 0)
    failed = int(entry.get("failed", 0) or 0)
    active_run_ids = _entry_active_run_ids(entry)
    status = _node_status(entry)
    # AgentNode 有额外的状态语义：只要有活跃运行即 running；从未执行即 pending
    if isinstance(node, AgentNode) and active_run_ids:
        status = "running"
    elif isinstance(node, AgentNode) and executions == 0 and not active_run_ids:
        status = "pending"

    avg_duration_ms = 0
    if completed > 0:
        avg_duration_ms = int(round(float(entry.get("total_duration_ms", 0.0)) / completed))
    elif active_run_ids and entry.get("last_started"):
        # 当前仍在运行，按已耗时估算平均持续时间
        started = _parse_iso_timestamp(entry.get("last_started"))
        if started is not None:
            avg_duration_ms = int(max(0.0, (datetime.now(timezone.utc) - started).total_seconds() * 1000.0))

    priority = _normalize_priority(getattr(node, "metadata", {}).get("priority") if isinstance(getattr(node, "metadata", {}), dict) else None)
    # AgentNode 默认优先级提升为 high
    if isinstance(node, AgentNode) and priority == "medium":
        priority = "high"

    executor = getattr(node, "agent_id", None) or getattr(node, "tool_name", None) or "system"
    node_type_name = node.__class__.__name__
    detail_description = (node.metadata or {}).get("description") if isinstance(node.metadata, dict) else None
    detail_logs = [
        {
            "time": log.get("time"),
            "level": log.get("level", "info"),
            "message": log.get("message", ""),
        }
        for log in entry.get("logs", [])
    ]
    created_at = entry.get("last_started") or reference_time

    return {
        "id": f"{swarm_name}:{node.node_id}",
        "name": node.node_name,
        "status": status,
        "priority": priority,
        "executor": executor,
        "duration_ms": avg_duration_ms,
        "created_at": created_at,
        "description": str(detail_description) if detail_description is not None else f"{node_type_name} · {node.node_name}",
        "input": jsonable_text(entry.get("last_input")),
        "output": jsonable_text(entry.get("last_output")),
        "logs": detail_logs,
        "swarm": swarm_name,
        "failed_count": failed,
        "completed_count": completed,
        "executed_count": executions,
    }


def build_task_catalog(
    registry,
    *,
    swarm_name: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    executor: Optional[str] = None,
    from_time: Optional[str] = None,
    to_time: Optional[str] = None,
    q: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
) -> Dict[str, Any]:
    """构建跨 swarm 的任务目录。

    Args:
        registry: 运行时注册表。
        swarm_name: 仅查询指定 swarm；None 表示全部。
        status: 按任务状态过滤。
        priority: 按优先级过滤。
        executor: 按执行者名称过滤。
        from_time: 创建时间下限（ISO 格式）。
        to_time: 创建时间上限（ISO 格式）。
        q: 全文搜索关键词。
        page: 分页页码。
        limit: 每页数量。

    Returns:
        包含 total、page、limit、items 与 stats 的字典。
    """
    from_dt = _parse_iso_timestamp(from_time)
    to_dt = _parse_iso_timestamp(to_time)
    normalized_status = str(status or "").strip().lower()
    normalized_priority = str(priority or "").strip().lower()
    normalized_executor = str(executor or "").strip().lower()
    normalized_query = str(q or "").strip().lower()

    from core.policy import AgentNode

    items: List[Dict[str, Any]] = []
    for loaded_swarm in registry.swarms.values():
        if swarm_name and loaded_swarm.manifest.swarm_name != swarm_name:
            continue
        graph = loaded_swarm.core.get_execution_graph()
        if graph is None:
            continue
        runs = registry.runs.list_runs(loaded_swarm.manifest.swarm_name)
        activity = _build_activity_index(runs)
        reference_time = _file_mtime_iso(Path(loaded_swarm.package_path) / loaded_swarm.manifest.graph_file)
        for node in sorted(graph.nodes.values(), key=lambda item: item.node_id):
            entry = activity.get((loaded_swarm.manifest.swarm_name, node.node_id), {})
            item = _build_task_item(
                swarm_name=loaded_swarm.manifest.swarm_name,
                node=node,
                entry=entry,
                reference_time=reference_time,
            )
            item_time = _parse_iso_timestamp(item.get("created_at"))
            if from_dt is not None and (item_time is None or item_time < from_dt):
                continue
            if to_dt is not None and (item_time is None or item_time > to_dt):
                continue
            if normalized_status and item["status"] != normalized_status:
                continue
            if normalized_priority and item["priority"] != normalized_priority:
                continue
            if normalized_executor and normalized_executor not in str(item["executor"]).lower():
                continue
            if normalized_query:
                searchable = " ".join(
                    [
                        str(item.get("id", "")),
                        str(item.get("name", "")),
                        str(item.get("description", "")),
                        str(item.get("executor", "")),
                        jsonable_text(item.get("input")),
                        jsonable_text(item.get("output")),
                        " ".join(str(log.get("message", "")) for log in item.get("logs", [])),
                    ]
                ).lower()
                if normalized_query not in searchable:
                    continue
            items.append(item)

    total = len(items)
    page = max(1, int(page or 1))
    limit = max(1, int(limit or 20))
    start = (page - 1) * limit
    page_items = items[start : start + limit]
    stats = {
        "pending": sum(1 for item in items if item["status"] == "pending"),
        "running": sum(1 for item in items if item["status"] == "running"),
        "success": sum(1 for item in items if item["status"] == "success"),
        "failed": sum(1 for item in items if item["status"] == "failed"),
        "avg_duration_ms": int(round(sum(item["duration_ms"] for item in items) / total)) if total else 0,
    }
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "items": page_items,
        "stats": stats,
    }
