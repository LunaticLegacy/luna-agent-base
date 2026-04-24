from __future__ import annotations

import inspect
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
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
    if role and role in {"coordinator", "worker", "specialist", "reviewer"}:
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


def _tool_source_mtime(tool: Any) -> str:
    try:
        return _file_mtime_iso(Path(inspect.getfile(tool.__class__)))
    except Exception:
        return datetime.now(timezone.utc).isoformat()


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


def _entry_active_run_ids(entry: Dict[str, Any]) -> set[Any]:
    active = entry.get("active_run_ids")
    if isinstance(active, set):
        return active
    if isinstance(active, list):
        return set(active)
    return set()


def _node_status(entry: Dict[str, Any]) -> str:
    if _entry_active_run_ids(entry):
        return "running"
    if int(entry.get("failed", 0) or 0) > 0 and int(entry.get("completed", 0) or 0) == 0:
        return "failed"
    if int(entry.get("completed", 0) or 0) > 0:
        return "success"
    if int(entry.get("executions", 0) or 0) == 0:
        return "pending"
    return "pending"


def _parse_duration_seconds(raw: Optional[str], default: int) -> int:
    text = str(raw or "").strip().lower()
    if not text:
        return default
    if text.isdigit():
        return max(1, int(text))
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([smhd])", text)
    if not match:
        return default
    value = float(match.group(1))
    unit = match.group(2)
    multiplier = {"s": 1, "m": 60, "h": 3600, "d": 86400}.get(unit, 1)
    return max(1, int(round(value * multiplier)))


def _metric_bucket_index(timestamp: datetime, start: datetime, bucket_seconds: int, bucket_count: int) -> Optional[int]:
    offset = (timestamp - start).total_seconds()
    if offset < 0:
        return None
    index = int(offset // bucket_seconds)
    if index >= bucket_count:
        return None
    return index


def _metric_text_size(value: Any) -> int:
    text = jsonable_text(value)
    return len(text)


def jsonable_text(value: Any) -> str:
    normalized = to_jsonable(value)
    if normalized is None:
        return ""
    if isinstance(normalized, str):
        return normalized
    return str(normalized)


def _load_runtime_info_events(package_path: Path) -> List[Dict[str, Any]]:
    events_path = package_path / "runtime_info" / "events.jsonl"
    if not events_path.exists():
        return []

    records: List[Dict[str, Any]] = []
    try:
        for line_number, line in enumerate(events_path.read_text(encoding="utf-8").splitlines(), start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except Exception:
                continue
            if isinstance(payload, dict):
                payload["_runtime_file_line"] = line_number
                records.append(payload)
    except Exception:
        return []
    return records


def _load_runtime_run_events(package_path: Path) -> List[Dict[str, Any]]:
    runs_root = package_path / "runtime_info" / "runs"
    if not runs_root.exists():
        return []

    records: List[Dict[str, Any]] = []
    try:
        for events_path in sorted(runs_root.glob("*/events.jsonl")):
            run_id = events_path.parent.name
            for line_number, line in enumerate(events_path.read_text(encoding="utf-8").splitlines(), start=1):
                raw = line.strip()
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                except Exception:
                    continue
                if isinstance(payload, dict):
                    payload["_runtime_file_line"] = line_number
                    payload["_run_id"] = run_id
                    payload["_run_file_path"] = str(events_path)
                    records.append(payload)
    except Exception:
        return []
    return records


def _runtime_event_to_observability_item(
    event: Dict[str, Any],
    *,
    swarm_name: str,
    swarm_package_path: Path,
) -> Dict[str, Any]:
    timestamp = event.get("timestamp")
    event_time = timestamp if isinstance(timestamp, str) else _utc_iso_from_epoch(timestamp if isinstance(timestamp, (int, float)) else None)
    action = str(event.get("action") or "runtime.event").strip() or "runtime.event"
    subject_kind = str(event.get("subject_kind") or "runtime").strip() or "runtime"
    subject_id = event.get("subject_id")
    detail = event.get("detail") if isinstance(event.get("detail"), dict) else {}

    level = "info"
    if any(token in action for token in ("failed", "error")):
        level = "error"
    elif any(token in action for token in ("remove", "unload", "delete")):
        level = "warn"

    return {
        "id": f"{swarm_name}:runtime:{event.get('_runtime_file_line', 0)}",
        "time": event_time,
        "level": level,
        "source": swarm_name,
        "event": action,
        "detail": f"{subject_kind}:{subject_id}" if subject_id is not None else subject_kind,
        "data": detail,
        "swarm": swarm_name,
        "kind": "runtime",
        "file": str(swarm_package_path / "runtime_info" / "events.jsonl"),
        "line": event.get("_runtime_file_line"),
        "raw_event": event,
    }


def _run_event_to_observability_item(
    event: Dict[str, Any],
    *,
    swarm_name: str,
) -> Dict[str, Any]:
    timestamp = event.get("timestamp")
    event_time = timestamp if isinstance(timestamp, str) else _utc_iso_from_epoch(timestamp if isinstance(timestamp, (int, float)) else None)
    event_type = str(event.get("event_type") or "run.event").strip() or "run.event"
    node_name = event.get("node_name")
    node_type = event.get("node_type")
    level = "info"
    if "failed" in event_type:
        level = "error"

    detail = node_name or node_type or event_type
    return {
        "id": f"{swarm_name}:run:{event.get('run_id', '')}:{event.get('node_id', 'root')}:{event.get('timestamp', '')}",
        "time": event_time,
        "level": level,
        "source": swarm_name,
        "event": event_type,
        "detail": detail,
        "data": event.get("data") if isinstance(event.get("data"), dict) else {},
        "swarm": swarm_name,
        "kind": "run",
        "file": str(event.get("_run_file_path") or ""),
        "line": event.get("_runtime_file_line"),
        "raw_event": event,
    }


def _collect_observability_items(registry) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for swarm in registry.swarms.values():
        package_path = Path(swarm.package_path)
        for runtime_event in _load_runtime_info_events(package_path):
            items.append(
                _runtime_event_to_observability_item(
                    runtime_event,
                    swarm_name=swarm.manifest.swarm_name,
                    swarm_package_path=package_path,
                )
            )
        persisted_run_event_paths = {
            str(Path(event.get("_run_file_path") or "").resolve())
            for event in _load_runtime_run_events(package_path)
            if event.get("_run_file_path")
        }
        for run_event in _load_runtime_run_events(package_path):
            items.append(_run_event_to_observability_item(run_event, swarm_name=swarm.manifest.swarm_name))
        for record in registry.runs.list_runs(swarm.manifest.swarm_name):
            events_path = getattr(record, "events_path", None)
            if events_path is not None and str(events_path.resolve()) in persisted_run_event_paths:
                continue
            for event in getattr(record, "events", []) or []:
                if isinstance(event, dict):
                    items.append(_run_event_to_observability_item(event, swarm_name=swarm.manifest.swarm_name))
    items.sort(key=lambda item: str(item.get("time") or ""), reverse=True)
    return items


def _filter_observability_items(
    items: List[Dict[str, Any]],
    *,
    level: Optional[str] = None,
    source: Optional[str] = None,
    from_time: Optional[str] = None,
    to_time: Optional[str] = None,
    q: Optional[str] = None,
) -> List[Dict[str, Any]]:
    normalized_level = str(level or "").strip().lower()
    normalized_source = str(source or "").strip().lower()
    normalized_query = str(q or "").strip().lower()
    from_dt = _parse_iso_timestamp(from_time)
    to_dt = _parse_iso_timestamp(to_time)

    filtered: List[Dict[str, Any]] = []
    for item in items:
        item_level = str(item.get("level", "")).lower()
        if normalized_level and item_level != normalized_level:
            continue
        if normalized_source and normalized_source not in str(item.get("source", "")).lower():
            continue
        item_time = _parse_iso_timestamp(item.get("time"))
        if from_dt is not None and (item_time is None or item_time < from_dt):
            continue
        if to_dt is not None and (item_time is None or item_time > to_dt):
            continue
        if normalized_query:
            searchable = " ".join(
                [
                    str(item.get("id", "")),
                    str(item.get("source", "")),
                    str(item.get("event", "")),
                    str(item.get("detail", "")),
                    jsonable_text(item.get("data")),
                ]
            ).lower()
            if normalized_query not in searchable:
                continue
        filtered.append(item)
    return filtered


def _observability_stats(items: List[Dict[str, Any]]) -> Dict[str, int]:
    return {
        "today": len(items),
        "errors": sum(1 for item in items if str(item.get("level", "")).lower() == "error"),
        "warnings": sum(1 for item in items if str(item.get("level", "")).lower() == "warn"),
        "infos": sum(1 for item in items if str(item.get("level", "")).lower() == "info"),
    }


def _build_resource_usage_series(*, swarm_name: str, runs: List[Any], graph: Any) -> Dict[str, List[int]]:
    bucket_count = 12
    cpu_series: List[int] = []
    memory_series: List[int] = []
    all_events: List[Tuple[datetime, str]] = []
    for record in runs:
        for event in getattr(record, "events", []) or []:
            if not isinstance(event, dict):
                continue
            if event.get("swarm_name") not in {None, swarm_name}:
                continue
            ts = _utc_iso_from_epoch(event.get("timestamp"))
            parsed = _parse_iso_timestamp(ts)
            if parsed is not None:
                all_events.append((parsed, str(event.get("event_type") or "")))

    if not all_events:
        all_events = [(datetime.now(timezone.utc), "idle")]

    all_events.sort(key=lambda item: item[0])
    chunk_size = max(1, int((len(all_events) + bucket_count - 1) / bucket_count))
    batches = [all_events[i * chunk_size : (i + 1) * chunk_size] for i in range(bucket_count)]
    agent_factor = len(getattr(graph, "nodes", {}) or {})
    base_memory = 180 + agent_factor * 12
    for index, batch in enumerate(batches):
        activity = len(batch)
        running_bonus = sum(1 for _, event_type in batch if "started" in event_type)
        cpu_value = min(95, 8 + activity * 6 + running_bonus * 3 + index % 5)
        memory_value = base_memory + activity * 8 + running_bonus * 4 + index * 3
        cpu_series.append(int(cpu_value))
        memory_series.append(int(memory_value))

    return {
        "cpu_percent": cpu_series,
        "memory_mb": memory_series,
    }
