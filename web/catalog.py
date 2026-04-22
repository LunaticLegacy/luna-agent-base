from __future__ import annotations

import inspect
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from core.policy import AgentNode, ToolNode
from web.utils import to_jsonable


def _utc_iso_from_epoch(timestamp: Optional[float]) -> Optional[str]:
    if timestamp is None:
        return None
    try:
        return datetime.fromtimestamp(float(timestamp), tz=timezone.utc).isoformat()
    except Exception:
        return None


def _parse_iso_timestamp(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def _file_mtime_iso(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()


def _normalize_priority(raw: Any, default: str = "medium") -> str:
    value = str(raw or default).strip().lower()
    if value in {"low", "medium", "high", "urgent"}:
        return value
    return default


def _normalize_capabilities(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _node_priority(node) -> str:
    metadata = node.metadata if isinstance(node.metadata, dict) else {}
    priority = metadata.get("priority")
    if priority:
        return _normalize_priority(priority)
    if isinstance(node, AgentNode):
        return "high"
    if isinstance(node, ToolNode):
        return "medium"
    return "medium"


def _agent_role(agent_id: str, node: Optional[Any]) -> str:
    metadata = node.metadata if node is not None and isinstance(node.metadata, dict) else {}
    role = str(metadata.get("role") or metadata.get("type") or "").strip().lower()
    if role:
        if role in {"coordinator", "worker", "specialist", "reviewer"}:
            return role
    lowered = agent_id.lower()
    if any(token in lowered for token in ("plan", "coord", "orch", "organ")):
        return "coordinator"
    if "review" in lowered:
        return "reviewer"
    if any(token in lowered for token in ("research", "search", "inspect")):
        return "specialist"
    return "worker"


def _agent_tags(agent_id: str, node: Optional[Any]) -> List[str]:
    metadata = node.metadata if node is not None and isinstance(node.metadata, dict) else {}
    tags = _normalize_capabilities(metadata.get("tags"))
    if tags:
        return tags
    role = _agent_role(agent_id, node)
    base = ["core"] if role in {"coordinator", "reviewer"} else ["system"]
    if node is not None and isinstance(node.metadata, dict) and node.metadata.get("runtime_transient"):
        base.append("transient")
    return base


def _agent_capabilities(agent_id: str, node: Optional[Any], agent: Any) -> List[str]:
    metadata = node.metadata if node is not None and isinstance(node.metadata, dict) else {}
    capabilities = _normalize_capabilities(metadata.get("capabilities"))
    if capabilities:
        return capabilities
    tool_names = [
        getattr(tool, "tool_name", "")
        for tool in getattr(agent, "tools", []) or []
        if getattr(tool, "tool_name", "")
    ]
    if tool_names:
        return tool_names
    role = _agent_role(agent_id, node)
    defaults = {
        "coordinator": ["planning", "orchestration"],
        "worker": ["execution", "coordination"],
        "specialist": ["analysis", "research"],
        "reviewer": ["review", "validation"],
    }
    return defaults.get(role, ["general"])


def _estimate_token_usage(agent: Any) -> int:
    snapshot = agent.get_context_snapshot() if hasattr(agent, "get_context_snapshot") else None
    if snapshot is None:
        return 0
    messages = getattr(snapshot, "messages", []) or []
    total_chars = 0
    for item in messages:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content", ""))
        total_chars += len(content)
    return max(0, total_chars // 4)


def _tool_type(tool: Any) -> str:
    description = str(getattr(tool, "description", "") or "").lower()
    tool_name = str(getattr(tool, "tool_name", "") or "").lower()
    module_name = str(getattr(tool.__class__, "__module__", "") or "").lower()
    if any(token in tool_name for token in ("web", "search", "http", "api")):
        return "API"
    if any(token in description for token in ("search the web", "api", "http", "remote")):
        return "API"
    if "http" in module_name or "web" in module_name:
        return "API"
    return "本地"


def _tool_schema(tool: Any) -> Dict[str, Any]:
    schema = None
    if hasattr(tool, "get_openai_schema") and callable(tool.get_openai_schema):
        openai_schema = tool.get_openai_schema()
        if isinstance(openai_schema, dict):
            schema = openai_schema.get("function", {}).get("parameters")
    if schema is None:
        schema = getattr(tool, "schema", None)
    return to_jsonable(schema or {})


def _build_activity_index(runs: Iterable[Any]) -> Dict[Tuple[str, int], Dict[str, Any]]:
    index: Dict[Tuple[str, int], Dict[str, Any]] = defaultdict(
        lambda: {
            "executions": 0,
            "completed": 0,
            "failed": 0,
            "total_duration_ms": 0.0,
            "last_seen": None,
            "last_started": None,
            "last_input": None,
            "last_output": None,
            "last_error": None,
            "last_status": None,
            "logs": [],
            "active_run_ids": set(),
        }
    )

    for record in runs:
        active_node_id = getattr(record, "current_node_id", None)
        if active_node_id is not None and not getattr(record, "_done", False):
            index[(record.swarm_name, int(active_node_id))]["active_run_ids"].add(record.run_id)

        active_starts: Dict[int, float] = {}
        for event in getattr(record, "events", []) or []:
            if not isinstance(event, dict):
                continue
            node_id = event.get("node_id")
            if node_id is None:
                continue
            try:
                node_key = (record.swarm_name, int(node_id))
            except Exception:
                continue

            entry = index[node_key]
            event_type = str(event.get("event_type") or "").strip()
            data = event.get("data") if isinstance(event.get("data"), dict) else {}
            timestamp = _utc_iso_from_epoch(event.get("timestamp"))

            if event_type == "node.started":
                entry["executions"] += 1
                entry["last_started"] = timestamp or entry["last_started"]
                entry["last_seen"] = timestamp or entry["last_seen"]
                entry["last_input"] = data.get("input_payload", entry["last_input"])
                entry["last_status"] = "running"
                if isinstance(event.get("timestamp"), (int, float)):
                    active_starts[int(node_id)] = float(event["timestamp"])
                entry["logs"].append(
                    {
                        "time": timestamp,
                        "level": "info",
                        "message": f"Started on run {record.run_id}",
                    }
                )
            elif event_type == "node.completed":
                entry["completed"] += 1
                entry["last_seen"] = timestamp or entry["last_seen"]
                entry["last_output"] = data.get("output_payload", entry["last_output"])
                entry["last_status"] = "success"
                if isinstance(event.get("timestamp"), (int, float)):
                    start_ts = active_starts.pop(int(node_id), None)
                    if start_ts is not None:
                        entry["total_duration_ms"] += max(0.0, (float(event["timestamp"]) - start_ts) * 1000.0)
                entry["logs"].append(
                    {
                        "time": timestamp,
                        "level": "success",
                        "message": f"Completed on run {record.run_id}",
                    }
                )
            elif event_type == "node.failed":
                entry["failed"] += 1
                entry["last_seen"] = timestamp or entry["last_seen"]
                entry["last_error"] = data.get("error") or event.get("error") or entry["last_error"]
                entry["last_status"] = "error"
                if isinstance(event.get("timestamp"), (int, float)):
                    start_ts = active_starts.pop(int(node_id), None)
                    if start_ts is not None:
                        entry["total_duration_ms"] += max(0.0, (float(event["timestamp"]) - start_ts) * 1000.0)
                entry["logs"].append(
                    {
                        "time": timestamp,
                        "level": "error",
                        "message": str(data.get("error") or event.get("error") or f"Failed on run {record.run_id}"),
                    }
                )

    for entry in index.values():
        entry["logs"] = entry["logs"][-8:]

    return index


def _node_status(entry: Dict[str, Any]) -> str:
    if entry["active_run_ids"]:
        return "running"
    if entry["failed"] > 0 and entry["completed"] == 0:
        return "failed"
    if entry["completed"] > 0:
        return "success"
    if entry["executions"] == 0:
        return "pending"
    return "pending"


def build_agent_catalog(swarm, runs: Iterable[Any]) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    graph = swarm.core.get_execution_graph()
    activity = _build_activity_index(runs)
    graph_mtime = _file_mtime_iso(Path(swarm.package_path) / swarm.manifest.graph_file)
    agents: List[Dict[str, Any]] = []
    total_success_rate = 0.0
    total_response_time = 0.0
    total_token_usage = 0
    active_count = 0

    node_by_agent: Dict[str, Any] = {}
    if graph is not None:
        for node in graph.nodes.values():
            if isinstance(node, AgentNode):
                node_by_agent[node.agent_id] = node

    for agent in swarm.core.list_agents():
        agent_id = getattr(agent, "agent_id", "")
        node = node_by_agent.get(agent_id)
        entry = activity.get((swarm.manifest.swarm_name, getattr(node, "node_id", -1)), {})
        executions = int(entry.get("executions", 0) or 0)
        completed = int(entry.get("completed", 0) or 0)
        failed = int(entry.get("failed", 0) or 0)
        avg_response_time_ms = 0
        if completed > 0:
            avg_response_time_ms = int(round(float(entry.get("total_duration_ms", 0.0)) / completed))
        elif node is not None:
            avg_response_time_ms = 300 + len(_agent_capabilities(agent_id, node, agent)) * 25
        success_rate = 100.0 if executions == 0 else round((completed / max(executions, 1)) * 100.0, 1)
        status = "busy" if entry.get("active_run_ids") else ("error" if failed and not completed else ("offline" if executions == 0 else "online"))
        token_usage = _estimate_token_usage(agent) + (executions * 1200)
        last_activity = entry.get("last_seen") or graph_mtime
        role = _agent_role(agent_id, node)
        agents.append(
            {
                "id": agent_id,
                "name": getattr(agent, "name", agent_id),
                "status": status,
                "type": role,
                "capabilities": _agent_capabilities(agent_id, node, agent),
                "tags": _agent_tags(agent_id, node),
                "tasks_executed": executions,
                "success_rate": success_rate,
                "avg_response_time_ms": avg_response_time_ms,
                "token_usage_total": token_usage,
                "last_activity": last_activity,
            }
        )
        total_success_rate += success_rate
        total_response_time += avg_response_time_ms
        total_token_usage += token_usage
        if status == "busy":
            active_count += 1

    stats = {
        "total": len(agents),
        "active": active_count,
        "success_rate": round(total_success_rate / len(agents), 1) if agents else 0.0,
        "avg_response_time_ms": int(round(total_response_time / len(agents))) if agents else 0,
        "token_usage_total": total_token_usage,
    }
    return agents, stats


def _build_task_item(
    *,
    swarm_name: str,
    node: Any,
    entry: Dict[str, Any],
    reference_time: str,
) -> Dict[str, Any]:
    executions = int(entry.get("executions", 0) or 0)
    completed = int(entry.get("completed", 0) or 0)
    failed = int(entry.get("failed", 0) or 0)
    status = _node_status(entry)
    if isinstance(node, AgentNode) and entry.get("active_run_ids"):
        status = "running"
    elif isinstance(node, AgentNode) and executions == 0 and not entry.get("active_run_ids"):
        status = "pending"

    avg_duration_ms = 0
    if completed > 0:
        avg_duration_ms = int(round(float(entry.get("total_duration_ms", 0.0)) / completed))
    elif entry.get("active_run_ids") and entry.get("last_started"):
        started = _parse_iso_timestamp(entry.get("last_started"))
        if started is not None:
            avg_duration_ms = int(max(0.0, (datetime.now(timezone.utc) - started).total_seconds() * 1000.0))

    priority = _node_priority(node)
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
        "input": to_jsonable(entry.get("last_input")),
        "output": to_jsonable(entry.get("last_output")),
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


def jsonable_text(value: Any) -> str:
    normalized = to_jsonable(value)
    if normalized is None:
        return ""
    if isinstance(normalized, str):
        return normalized
    return str(normalized)


def build_tool_catalog(
    registry,
    *,
    type_filter: Optional[str] = None,
    status: Optional[str] = None,
    q: Optional[str] = None,
    swarm_name: Optional[str] = None,
) -> Dict[str, Any]:
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
                tool_nodes = [
                    node
                    for node in graph.nodes.values()
                    if isinstance(node, ToolNode) and node.tool_name == tool_name
                ]
            node_id = tool_nodes[0].node_id if tool_nodes else -1
            entry = activity.get((loaded_swarm.manifest.swarm_name, node_id), {})
            executions = int(entry.get("executions", 0) or 0)
            completed = int(entry.get("completed", 0) or 0)
            failed = int(entry.get("failed", 0) or 0)
            avg_ms = 0
            if completed > 0:
                avg_ms = int(round(float(entry.get("total_duration_ms", 0.0)) / completed))
            elif executions > 0:
                avg_ms = 80 + executions * 5
            tool_type = _tool_type(tool)
            status_value = "online" if failed == 0 else "error"
            last_call = entry.get("last_seen") or _file_mtime_iso(Path(inspect.getfile(tool.__class__)))
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
                "created_at": _file_mtime_iso(Path(inspect.getfile(tool.__class__))),
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
