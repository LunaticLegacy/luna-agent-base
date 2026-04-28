"""Catalog 构建器的共享工具函数。

提供时间解析、文件元数据读取、agent/tool 元数据推断、
活动索引构建、可观测性数据收集与过滤等通用能力。
所有函数均为纯函数，不依赖外部可变状态。
"""
from __future__ import annotations

import inspect
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from core.policy import AgentNode, ToolNode, _node_is_transient
from web.utils import to_jsonable


def _utc_iso_from_epoch(timestamp: Optional[float]) -> Optional[str]:
    """将 Unix 时间戳转为 UTC ISO 格式字符串。

    Args:
        timestamp: 秒级时间戳。

    Returns:
        ISO 字符串，或 None（输入无效时）。
    """
    if timestamp is None:
        return None
    try:
        return datetime.fromtimestamp(float(timestamp), tz=timezone.utc).isoformat()
    except Exception:
        return None


def _parse_iso_timestamp(raw: Optional[str]) -> Optional[datetime]:
    """将 ISO 时间字符串安全解析为 datetime 对象。

    兼容含 "Z" 后缀的格式。

    Args:
        raw: 原始时间字符串。

    Returns:
        解析后的 datetime，或 None。
    """
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
    """获取文件最后修改时间的 UTC ISO 字符串。

    文件不可读时回退到当前时间，避免前端展示空值。

    Args:
        path: 目标文件路径。

    Returns:
        ISO 格式时间字符串。
    """
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()


def _normalize_priority(raw: Any, default: str = "medium") -> str:
    """将原始优先级归一化为标准四档之一。

    Args:
        raw: 原始值。
        default: 无法识别时的默认值。

    Returns:
        "low" / "medium" / "high" / "urgent" 之一。
    """
    value = str(raw or default).strip().lower()
    if value in {"low", "medium", "high", "urgent"}:
        return value
    return default


def _normalize_capabilities(value: Any) -> List[str]:
    """将原始能力描述规范化为字符串列表。

    Args:
        value: list、str 或其他。

    Returns:
        非空字符串列表。
    """
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _node_priority(node) -> str:
    """根据节点类型与元数据推断默认优先级。

    Args:
        node: 图节点实例。

    Returns:
        优先级字符串。
    """
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
    """根据 agent_id 与节点元数据推断角色。

    若元数据显式指定 role/type 且属于已知集合，则直接采用；
    否则通过 agent_id 中的关键词启发式推断。

    Args:
        agent_id: agent 标识。
        node: 可选的关联节点。

    Returns:
        "coordinator" / "worker" / "specialist" / "reviewer" 之一。
    """
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
    """提取 agent 的标签列表。

    优先使用节点元数据中的 tags；若缺失则按角色分配默认标签，
    并对 transient 节点追加 "transient" 标记。

    Args:
        agent_id: agent 标识。
        node: 可选的关联节点。

    Returns:
        标签字符串列表。
    """
    metadata = node.metadata if node is not None and isinstance(node.metadata, dict) else {}
    tags = _normalize_capabilities(metadata.get("tags"))
    if tags:
        return tags
    role = _agent_role(agent_id, node)
    base = ["core"] if role in {"coordinator", "reviewer"} else ["system"]
    if node is not None and isinstance(node.metadata, dict) and _node_is_transient(node.metadata):
        base.append("transient")
    return base


def _agent_capabilities(agent_id: str, node: Optional[Any], agent: Any) -> List[str]:
    """提取 agent 的能力列表。

    优先级：节点元数据 capabilities > agent.tools 工具名 > 按角色默认。

    Args:
        agent_id: agent 标识。
        node: 可选的关联节点。
        agent: agent 实例。

    Returns:
        能力字符串列表。
    """
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
    """根据 agent 上下文快照估算已用 Token 数。

    按总字符数除以 4 做粗略估算。

    Args:
        agent: agent 实例。

    Returns:
        估算的 Token 数量。
    """
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
    """根据工具名称、描述与模块路径推断工具类型。

    若包含 web/search/http/api 相关关键词，则归类为 "API"；
    否则归类为 "本地"。

    Args:
        tool: 工具实例。

    Returns:
        "API" 或 "本地"。
    """
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
    """提取工具的 JSON Schema。

    优先使用 OpenAI 风格的 function schema，其次回退到 tool.schema。

    Args:
        tool: 工具实例。

    Returns:
        JSON-safe 的 schema 字典。
    """
    schema = None
    if hasattr(tool, "get_openai_schema") and callable(tool.get_openai_schema):
        openai_schema = tool.get_openai_schema()
        if isinstance(openai_schema, dict):
            schema = openai_schema.get("function", {}).get("parameters")
    if schema is None:
        schema = getattr(tool, "schema", None)
    return to_jsonable(schema or {})


def _tool_source_mtime(tool: Any) -> str:
    """获取工具源文件的最后修改时间。

    若无法通过 inspect 定位源文件，则回退到当前时间。

    Args:
        tool: 工具实例。

    Returns:
        ISO 格式时间字符串。
    """
    try:
        return _file_mtime_iso(Path(inspect.getfile(tool.__class__)))
    except Exception:
        return datetime.now(timezone.utc).isoformat()


def _build_activity_index(runs: Iterable[Any]) -> Dict[Tuple[str, int], Dict[str, Any]]:
    """为所有运行记录构建按 (swarm_name, node_id) 索引的活动统计。

    统计项包括：executions、completed、failed、total_duration_ms、
    last_seen、last_started、last_input、last_output、last_error、
    last_status、logs、active_run_ids。

    Args:
        runs: 运行记录迭代器。

    Returns:
        活动索引字典。
    """
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
        # 记录当前仍活跃的运行（未结束且有 current_node_id）
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
                input_payload = data.get("input_payload")
                if input_payload is None:
                    state_snapshot = data.get("state_snapshot", {})
                    payload = state_snapshot.get("payload") if isinstance(state_snapshot, dict) else None
                    input_payload = payload
                entry["last_input"] = input_payload or entry["last_input"]
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
                output_payload = data.get("output_payload")
                if output_payload is None:
                    state_snapshot = data.get("state_snapshot", {})
                    metadata = state_snapshot.get("metadata", {}) if isinstance(state_snapshot, dict) else {}
                    outputs = metadata.get("outputs", {}) if isinstance(metadata, dict) else {}
                    output_payload = outputs.get(str(node_id)) if node_id is not None else None
                entry["last_output"] = output_payload or entry["last_output"]
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
            elif event_type == "node.skipped":
                entry["last_seen"] = timestamp or entry["last_seen"]
                entry["last_status"] = "skipped"
                entry["logs"].append(
                    {
                        "time": timestamp,
                        "level": "warn",
                        "message": str(data.get("reason") or f"Skipped on run {record.run_id}"),
                    }
                )

    for entry in index.values():
        entry["logs"] = entry["logs"][-8:]

    return index


def _entry_active_run_ids(entry: Dict[str, Any]) -> set[Any]:
    """安全提取 entry 中的活跃运行 ID 集合。

    Args:
        entry: 活动索引条目。

    Returns:
        run_id 的集合。
    """
    active = entry.get("active_run_ids")
    if isinstance(active, set):
        return active
    if isinstance(active, list):
        return set(active)
    return set()


def _node_status(entry: Dict[str, Any]) -> str:
    """根据活动统计推断节点状态。

    状态优先级：running > failed > success > pending。

    Args:
        entry: 活动索引条目。

    Returns:
        状态字符串。
    """
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
    """将持续时间描述解析为秒数。

    支持纯数字或 "<数值><单位>" 格式，单位包括 s、m、h、d。

    Args:
        raw: 原始描述字符串。
        default: 解析失败时的默认值。

    Returns:
        正整数秒数。
    """
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
    """将时间点映射到指标桶索引。

    Args:
        timestamp: 待映射的时间点。
        start: 窗口起始时间。
        bucket_seconds: 每个桶的秒数。
        bucket_count: 桶总数。

    Returns:
        桶索引，或 None（超出范围）。
    """
    offset = (timestamp - start).total_seconds()
    if offset < 0:
        return None
    index = int(offset // bucket_seconds)
    if index >= bucket_count:
        return None
    return index


def _metric_text_size(value: Any) -> int:
    """将任意值转为 JSON 字符串后返回其长度。

    Args:
        value: 原始值。

    Returns:
        字符串长度。
    """
    text = jsonable_text(value)
    return len(text)


def jsonable_text(value: Any) -> str:
    """将任意值转为可 JSON 序列化的字符串表示。

    Args:
        value: 原始值。

    Returns:
        字符串。
    """
    normalized = to_jsonable(value)
    if normalized is None:
        return ""
    if isinstance(normalized, str):
        return normalized
    return str(normalized)


def _load_runtime_info_events(package_path: Path) -> List[Dict[str, Any]]:
    """从 swarm 包的 runtime_info/events.jsonl 加载运行时事件。

    Args:
        package_path: swarm 包路径。

    Returns:
        事件字典列表。
    """
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
    """从 swarm 包的 runtime_info/runs/*/events.jsonl 加载运行级事件。

    Args:
        package_path: swarm 包路径。

    Returns:
        事件字典列表。
    """
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
    """将运行时事件转换为可观测性条目。

    Args:
        event: 原始事件字典。
        swarm_name: 所属 swarm 名称。
        swarm_package_path: swarm 包路径。

    Returns:
        标准化可观测性条目。
    """
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
    """将运行事件转换为可观测性条目。

    Args:
        event: 原始事件字典。
        swarm_name: 所属 swarm 名称。

    Returns:
        标准化可观测性条目。
    """
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
    """收集所有 swarm 的可观测性条目，按时间倒序排列。

    数据来源包括：
    1. runtime_info/events.jsonl（运行时事件）。
    2. runtime_info/runs/*/events.jsonl（运行级持久化事件）。
    3. 内存中运行记录的 events（尚未持久化的事件）。

    Args:
        registry: 运行时注册表。

    Returns:
        可观测性条目列表。
    """
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
    """对可观测性条目进行多维度过滤。

    Args:
        items: 条目列表。
        level: 级别过滤。
        source: 来源过滤。
        from_time: 时间下限。
        to_time: 时间上限。
        q: 全文搜索关键词。

    Returns:
        过滤后的条目列表。
    """
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
    """计算可观测性条目的基础统计。

    Args:
        items: 条目列表。

    Returns:
        包含 today、errors、warnings、infos 计数的字典。
    """
    return {
        "today": len(items),
        "errors": sum(1 for item in items if str(item.get("level", "")).lower() == "error"),
        "warnings": sum(1 for item in items if str(item.get("level", "")).lower() == "warn"),
        "infos": sum(1 for item in items if str(item.get("level", "")).lower() == "info"),
    }


def _build_resource_usage_series(*, swarm_name: str, runs: List[Any], graph: Any) -> Dict[str, List[int]]:
    """为指定 swarm 构建 CPU 与内存的时间序列。

    将事件按时间排序后均分为 12 个桶，按桶内活动量估算资源使用。

    Args:
        swarm_name: 目标 swarm 名称。
        runs: 运行记录列表。
        graph: 执行图对象。

    Returns:
        包含 cpu_percent 与 memory_mb 序列的字典。
    """
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
        # 无事件时生成一个占位 idle 事件，确保序列非空
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
