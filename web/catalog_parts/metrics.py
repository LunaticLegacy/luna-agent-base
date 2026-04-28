"""运行时指标构建器。

从所有 swarm 的运行记录中提取事件，按时间窗口与分辨率分桶，
计算 CPU、内存、延迟、吞吐量、Token 用量与错误率六条时间序列。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .shared import _metric_bucket_index, _metric_text_size, _parse_duration_seconds, _parse_iso_timestamp


def build_metrics_catalog(
    registry,
    *,
    window: Optional[str] = None,
    resolution: Optional[str] = None,
) -> Dict[str, Any]:
    """构建运行时指标时间序列。

    采集逻辑：
    1. 解析 window / resolution 并限制最大桶数（上限 240）。
    2. 扫描所有运行记录，确定最新事件时间作为窗口右边界。
    3. 将运行与事件按中点匹配落入对应桶。
    4. 根据各桶的活跃运行数、事件数、完成/失败数等推导六条指标序列。

    Args:
        registry: 运行时注册表。
        window: 时间窗口描述（如 "1h"、"30m"）；默认 1 小时。
        resolution: 采样精度描述（如 "1m"、"10s"）；默认 1 分钟。

    Returns:
        包含 window、resolution 与六条指标序列的字典。
    """
    window_seconds, resolution_seconds, bucket_count = _compute_bucket_params(window, resolution)
    all_runs, latest_timestamp = _find_latest_timestamp(registry)
    start_timestamp = latest_timestamp - timedelta(seconds=window_seconds)
    bucket_midpoints, buckets = _initialize_buckets(start_timestamp, resolution_seconds, bucket_count)
    base_memory_mb = _compute_base_memory(registry)

    buckets = _aggregate_events_into_buckets(
        all_runs, buckets, bucket_midpoints,
        start_timestamp, latest_timestamp, resolution_seconds, bucket_count,
    )

    return _compute_metric_series(
        buckets, base_memory_mb, resolution_seconds, window, resolution,
    )

def _compute_bucket_params(
    window: Optional[str],
    resolution: Optional[str],
) -> tuple[int, int, int]:
    """解析时间窗口与分辨率，计算桶数量和实际窗口秒数。

    最大桶数限制为 240，避免前端渲染压力过大。

    Returns:
        (window_seconds, resolution_seconds, bucket_count)
    """
    window_seconds = _parse_duration_seconds(window, 3600)
    resolution_seconds = _parse_duration_seconds(resolution, 60)
    bucket_count = max(1, min(240, (window_seconds + resolution_seconds - 1) // resolution_seconds))
    window_seconds = bucket_count * resolution_seconds
    return window_seconds, resolution_seconds, bucket_count

def _find_latest_timestamp(registry) -> tuple[List[Any], datetime]:
    """扫描所有运行记录及其事件，返回最新时间戳。

    Returns:
        (all_runs, latest_timestamp)
    """
    now = datetime.now(timezone.utc)
    latest_timestamp = now
    all_runs: List[Any] = []
    for swarm_name in registry.swarms.keys():
        all_runs.extend(registry.runs.list_runs(swarm_name))

    for record in all_runs:
        for raw_time in (record.started_at, record.finished_at, record.created_at):
            parsed = _parse_iso_timestamp(raw_time)
            if parsed is not None and parsed > latest_timestamp:
                latest_timestamp = parsed
        for event in getattr(record, "events", []) or []:
            if not isinstance(event, dict):
                continue
            parsed = _parse_iso_timestamp(str(event.get("timestamp") or ""))
            if parsed is not None and parsed > latest_timestamp:
                latest_timestamp = parsed

    return all_runs, latest_timestamp

def _initialize_buckets(
    start_timestamp: datetime,
    resolution_seconds: int,
    bucket_count: int,
) -> tuple[List[datetime], List[Dict[str, float]]]:
    """生成桶中点列表并初始化计数器字典。

    Returns:
        (bucket_midpoints, buckets)
    """
    bucket_midpoints = [
        start_timestamp + timedelta(seconds=(index * resolution_seconds) + (resolution_seconds / 2.0))
        for index in range(bucket_count)
    ]
    buckets: List[Dict[str, float]] = [
        {
            "active_runs": 0.0,
            "started": 0.0,
            "completed": 0.0,
            "failed": 0.0,
            "events": 0.0,
            "latency_sum": 0.0,
            "latency_count": 0.0,
            "token_usage": 0.0,
            "error_events": 0.0,
        }
        for _ in range(bucket_count)
    ]
    return bucket_midpoints, buckets

def _compute_base_memory(registry) -> int:
    """基于 swarm 与节点规模估算基准内存（MB）。

    Returns:
        估算的基准内存值（MB）。
    """
    total_nodes = 0
    total_swarm_count = len(registry.swarms)
    for loaded_swarm in registry.swarms.values():
        graph_getter = getattr(loaded_swarm.core, "get_agent_graph", None)
        graph = graph_getter() if callable(graph_getter) else loaded_swarm.core.get_execution_graph()
        if graph is not None:
            total_nodes += len(graph.nodes)
    return 220 + (total_nodes * 12) + (total_swarm_count * 28)

def _aggregate_events_into_buckets(
    all_runs: List[Any],
    buckets: List[Dict[str, float]],
    bucket_midpoints: List[datetime],
    start_timestamp: datetime,
    latest_timestamp: datetime,
    resolution_seconds: int,
    bucket_count: int,
) -> List[Dict[str, float]]:
    """将运行记录与事件按时间落入对应桶并累加计数器。

    Args:
        all_runs: 所有运行记录列表。
        buckets: 初始化的桶计数器。
        bucket_midpoints: 每个桶的中点时间。
        start_timestamp: 窗口起始时间。
        latest_timestamp: 窗口结束时间（最新事件时间）。
        resolution_seconds: 桶分辨率（秒）。
        bucket_count: 桶总数。

    Returns:
        更新后的桶计数器列表。
    """
    now_for_active = latest_timestamp
    for record in all_runs:
        record_start = _parse_iso_timestamp(record.started_at) or _parse_iso_timestamp(record.created_at) or start_timestamp
        record_end = _parse_iso_timestamp(record.finished_at) or now_for_active
        if record_end < start_timestamp or record_start > latest_timestamp:
            continue

        for bucket_index, midpoint in enumerate(bucket_midpoints):
            if record_start <= midpoint <= record_end:
                buckets[bucket_index]["active_runs"] += 1

        active_starts: Dict[int, float] = {}
        for event in getattr(record, "events", []) or []:
            if not isinstance(event, dict):
                continue
            parsed = _parse_iso_timestamp(str(event.get("timestamp") or ""))
            if parsed is None or parsed < start_timestamp or parsed > latest_timestamp:
                continue
            bucket_index = _metric_bucket_index(parsed, start_timestamp, resolution_seconds, bucket_count)
            if bucket_index is None:
                continue

            _apply_event_to_bucket(event, buckets[bucket_index], active_starts, parsed)

    return buckets

def _apply_event_to_bucket(
    event: Dict[str, Any],
    bucket: Dict[str, float],
    active_starts: Dict[int, float],
    parsed_timestamp: datetime,
) -> None:
    """根据事件类型更新单个桶的计数器。

    Args:
        event: 原始事件字典。
        bucket: 目标桶计数器（ mutated in-place ）。
        active_starts: 记录节点启动时间的字典（ mutated in-place ）。
        parsed_timestamp: 事件解析后的时间戳。
    """
    event_type = str(event.get("event_type") or "").strip()
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    node_id = event.get("node_id")
    bucket["events"] += 1

    if event_type == "run.started":
        bucket["token_usage"] += 180 + (_metric_text_size(data.get("input_payload")) // 6)
    elif event_type == "run.completed":
        bucket["completed"] += 1
        bucket["token_usage"] += 140 + (_metric_text_size(data.get("state_snapshot")) // 8)
    elif event_type == "run.failed":
        bucket["failed"] += 1
        bucket["error_events"] += 1
        bucket["token_usage"] += 70 + (_metric_text_size(data.get("error")) // 4)
    elif event_type == "node.started":
        bucket["started"] += 1
        input_text = data.get("input_payload")
        if input_text is None:
            state_snapshot = data.get("state_snapshot", {})
            payload = state_snapshot.get("payload") if isinstance(state_snapshot, dict) else None
            input_text = payload
        bucket["token_usage"] += 45 + (_metric_text_size(input_text) // 10)
        if node_id is not None:
            try:
                active_starts[int(node_id)] = parsed_timestamp.timestamp()
            except Exception:
                pass
    elif event_type == "node.completed":
        bucket["completed"] += 1
        output_text = data.get("output_payload")
        if output_text is None:
            state_snapshot = data.get("state_snapshot", {})
            metadata = state_snapshot.get("metadata", {}) if isinstance(state_snapshot, dict) else {}
            outputs = metadata.get("outputs", {}) if isinstance(metadata, dict) else {}
            output_text = outputs.get(str(node_id)) if node_id is not None else None
        bucket["token_usage"] += 110 + (_metric_text_size(output_text) // 8)
        if node_id is not None:
            try:
                start_ts = active_starts.pop(int(node_id), None)
                if start_ts is not None:
                    bucket["latency_sum"] += max(0.0, (float(parsed_timestamp.timestamp()) - float(start_ts)) * 1000.0)
                    bucket["latency_count"] += 1
            except Exception:
                pass
    elif event_type == "node.failed":
        bucket["failed"] += 1
        bucket["error_events"] += 1
        bucket["token_usage"] += 55 + (_metric_text_size(data.get("error") or event.get("error")) // 4)
        if node_id is not None:
            try:
                start_ts = active_starts.pop(int(node_id), None)
                if start_ts is not None:
                    bucket["latency_sum"] += max(0.0, (float(parsed_timestamp.timestamp()) - float(start_ts)) * 1000.0)
                    bucket["latency_count"] += 1
            except Exception:
                pass
    else:
        if any(token in event_type for token in ("error", "failed")):
            bucket["error_events"] += 1
        bucket["token_usage"] += 12 + (_metric_text_size(data) // 24)

def _compute_metric_series(
    buckets: List[Dict[str, float]],
    base_memory_mb: int,
    resolution_seconds: int,
    window: Optional[str],
    resolution: Optional[str],
) -> Dict[str, Any]:
    """根据桶计数器计算六条指标时间序列。

    使用经验公式将活跃运行数、事件数、完成/失败数等转换为
    CPU、内存、延迟、吞吐量、Token 用量与错误率。

    Returns:
        包含 window、resolution 与六条指标序列的字典。
    """
    cpu_series: List[int] = []
    memory_series: List[int] = []
    latency_series: List[int] = []
    throughput_series: List[float] = []
    token_usage_series: List[int] = []
    error_rate_series: List[float] = []

    for bucket in buckets:
        active_runs = bucket["active_runs"]
        events = bucket["events"]
        completed = bucket["completed"]
        failed = bucket["failed"]
        started = bucket["started"]
        token_usage = bucket["token_usage"]

        cpu_value = 8 + (active_runs * 9.5) + (events * 2.5) + (failed * 6.5) + (completed * 2.0)
        memory_value = base_memory_mb + (active_runs * 32.0) + (events * 5.0) + (token_usage / 260.0)
        latency_value = (bucket["latency_sum"] / bucket["latency_count"]) if bucket["latency_count"] > 0 else (32.0 + active_runs * 8.0 + events * 3.0)
        throughput_value = completed / max(1, resolution_seconds)
        error_rate_value = failed / max(1.0, started + completed + failed)

        cpu_series.append(int(max(1, min(100, round(cpu_value)))))
        memory_series.append(int(max(128, round(memory_value))))
        latency_series.append(int(max(1, round(latency_value))))
        throughput_series.append(round(throughput_value, 3))
        token_usage_series.append(int(max(0, round(token_usage))))
        error_rate_series.append(round(error_rate_value, 4))

    return {
        "success": True,
        "window": window or "1h",
        "resolution": resolution or "1m",
        "series": {
            "cpu_percent": cpu_series,
            "memory_mb": memory_series,
            "request_latency_ms": latency_series,
            "throughput_rps": throughput_series,
            "token_usage": token_usage_series,
            "error_rate": error_rate_series,
        },
    }

