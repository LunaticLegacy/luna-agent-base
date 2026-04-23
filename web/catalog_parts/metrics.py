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
    window_seconds = _parse_duration_seconds(window, 3600)
    resolution_seconds = _parse_duration_seconds(resolution, 60)
    bucket_count = max(1, min(240, (window_seconds + resolution_seconds - 1) // resolution_seconds))
    window_seconds = bucket_count * resolution_seconds

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

    start_timestamp = latest_timestamp - timedelta(seconds=window_seconds)
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

    total_nodes = 0
    total_swarm_count = len(registry.swarms)
    for loaded_swarm in registry.swarms.values():
        graph = loaded_swarm.core.get_execution_graph()
        if graph is not None:
            total_nodes += len(graph.nodes)

    base_memory_mb = 220 + (total_nodes * 12) + (total_swarm_count * 28)
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
            timestamp = event.get("timestamp")
            parsed = _parse_iso_timestamp(str(timestamp or ""))
            if parsed is None or parsed < start_timestamp or parsed > latest_timestamp:
                continue
            bucket_index = _metric_bucket_index(parsed, start_timestamp, resolution_seconds, bucket_count)
            if bucket_index is None:
                continue

            event_type = str(event.get("event_type") or "").strip()
            data = event.get("data") if isinstance(event.get("data"), dict) else {}
            bucket = buckets[bucket_index]
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
                bucket["token_usage"] += 45 + (_metric_text_size(data.get("input_payload")) // 10)
                node_id = event.get("node_id")
                if node_id is not None:
                    try:
                        active_starts[int(node_id)] = float(timestamp) if isinstance(timestamp, (int, float)) else parsed.timestamp()
                    except Exception:
                        pass
            elif event_type == "node.completed":
                bucket["completed"] += 1
                bucket["token_usage"] += 110 + (_metric_text_size(data.get("output_payload")) // 8)
                node_id = event.get("node_id")
                if node_id is not None:
                    try:
                        start_ts = active_starts.pop(int(node_id), None)
                        if start_ts is not None:
                            bucket["latency_sum"] += max(0.0, (float(parsed.timestamp()) - float(start_ts)) * 1000.0)
                            bucket["latency_count"] += 1
                    except Exception:
                        pass
            elif event_type == "node.failed":
                bucket["failed"] += 1
                bucket["error_events"] += 1
                bucket["token_usage"] += 55 + (_metric_text_size(data.get("error") or event.get("error")) // 4)
                node_id = event.get("node_id")
                if node_id is not None:
                    try:
                        start_ts = active_starts.pop(int(node_id), None)
                        if start_ts is not None:
                            bucket["latency_sum"] += max(0.0, (float(parsed.timestamp()) - float(start_ts)) * 1000.0)
                            bucket["latency_count"] += 1
                    except Exception:
                        pass
            else:
                if any(token in event_type for token in ("error", "failed")):
                    bucket["error_events"] += 1
                bucket["token_usage"] += 12 + (_metric_text_size(data) // 24)

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
