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
    from core.policy import AgentNode

    executions = int(entry.get("executions", 0) or 0)
    completed = int(entry.get("completed", 0) or 0)
    failed = int(entry.get("failed", 0) or 0)
    active_run_ids = _entry_active_run_ids(entry)
    status = _node_status(entry)
    if isinstance(node, AgentNode) and active_run_ids:
        status = "running"
    elif isinstance(node, AgentNode) and executions == 0 and not active_run_ids:
        status = "pending"

    avg_duration_ms = 0
    if completed > 0:
        avg_duration_ms = int(round(float(entry.get("total_duration_ms", 0.0)) / completed))
    elif active_run_ids and entry.get("last_started"):
        started = _parse_iso_timestamp(entry.get("last_started"))
        if started is not None:
            avg_duration_ms = int(max(0.0, (datetime.now(timezone.utc) - started).total_seconds() * 1000.0))

    priority = _normalize_priority(getattr(node, "metadata", {}).get("priority") if isinstance(getattr(node, "metadata", {}), dict) else None)
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
    from_dt = _parse_iso_timestamp(from_time)
    to_dt = _parse_iso_timestamp(to_time)
    normalized_status = str(status or "").strip().lower()
    normalized_priority = str(priority or "").strip().lower()
    normalized_executor = str(executor or "").strip().lower()
    normalized_query = str(q or "").strip().lower()

    try:
        from web.task_store import TaskStore

        data_dir = getattr(registry, "config_path", None)
        if data_dir is not None:
            data_dir = Path(data_dir).parent / "data"
        else:
            data_dir = Path("data")
        task_store = TaskStore(data_dir=data_dir)
        payload = task_store.list_tasks(
            swarm_name=swarm_name,
            status=status,
            agent_id=executor,
            page=page,
            limit=limit,
        )
        items = payload["items"]
        filtered: List[Dict[str, Any]] = []
        for item in items:
            item_time = _parse_iso_timestamp(item.get("created_at"))
            if from_dt is not None and (item_time is None or item_time < from_dt):
                continue
            if to_dt is not None and (item_time is None or item_time > to_dt):
                continue
            if normalized_query:
                searchable = " ".join(
                    [
                        str(item.get("task_id", "")),
                        str(item.get("name", "")),
                        str(item.get("description", "")),
                        str(item.get("agent_id", "")),
                        jsonable_text(item.get("input")),
                        jsonable_text(item.get("output")),
                    ]
                ).lower()
                if normalized_query not in searchable:
                    continue
            filtered.append(
                {
                    "id": item["task_id"],
                    "name": item["name"],
                    "status": item["status"],
                    "priority": item["priority"],
                    "executor": item.get("agent_id") or "system",
                    "duration_ms": 0,
                    "created_at": item.get("created_at", ""),
                    "description": item.get("description", ""),
                    "input": item.get("input"),
                    "output": item.get("output"),
                    "logs": item.get("metadata", {}).get("logs", []),
                    "swarm": item.get("swarm_name", ""),
                    "failed_count": item.get("failed_count", 0),
                    "completed_count": item.get("completed_count", 0),
                    "executed_count": item.get("executed_count", 0),
                }
            )
        total = len(filtered)
        start = (page - 1) * limit
        page_items = filtered[start : start + limit]
        return {
            "total": total,
            "page": page,
            "limit": limit,
            "items": page_items,
            "stats": {
                "pending": sum(1 for i in filtered if i["status"] == "pending"),
                "running": sum(1 for i in filtered if i["status"] == "running"),
                "success": sum(1 for i in filtered if i["status"] == "success"),
                "failed": sum(1 for i in filtered if i["status"] == "failed"),
                "avg_duration_ms": 0,
            },
        }
    except Exception:
        pass

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
