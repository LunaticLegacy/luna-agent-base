"""Swarm 统计构建器。

聚合单个 swarm 的运行成功率、吞吐量、Token 用量、任务分布与资源使用
时间序列，为前端 Dashboard 提供一站式数据视图。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from .agents import build_agent_catalog
from .shared import _build_resource_usage_series, _parse_iso_timestamp
from .tasks import build_task_catalog


def build_swarm_stats(
    registry,
    swarm_name: str,
) -> Dict[str, Any]:
    """构建指定 swarm 的综合统计信息。

    Args:
        registry: 运行时注册表。
        swarm_name: 目标 swarm 名称。

    Returns:
        包含成功率、吞吐量、Token 用量、任务分布、资源使用等字段的字典。
    """
    swarm = registry.get_swarm(swarm_name)
    runs = registry.runs.list_runs(swarm_name)
    graph_getter = getattr(swarm.core, "get_agent_graph", None)
    graph = graph_getter() if callable(graph_getter) else swarm.core.get_execution_graph()
    agent_stats = build_agent_catalog(swarm, runs)[1]
    # 拉取大量任务以避免分页截断，确保统计完整
    task_catalog = build_task_catalog(registry, swarm_name=swarm_name, page=1, limit=5000)
    completed_runs = [record for record in runs if getattr(record, "status", "") == "completed"]
    successful_runs = [record for record in completed_runs if not getattr(record, "error", None)]
    total_runs = len(runs)

    throughput = 0
    if completed_runs:
        timestamps = [_parse_iso_timestamp(record.finished_at or record.started_at or record.created_at) for record in completed_runs]
        timestamps = [ts for ts in timestamps if ts is not None]
        if len(timestamps) >= 2:
            # 按时间跨度计算每小时吞吐量
            span_seconds = max(1.0, (max(timestamps) - min(timestamps)).total_seconds())
            throughput = int(round(len(completed_runs) / max(1.0, span_seconds / 3600.0)))
        else:
            throughput = len(completed_runs)
    else:
        # 无 completed 记录时，以 _done 标记的运行数兜底
        throughput = len([record for record in runs if getattr(record, "_done", False)])

    token_usage = int(agent_stats["token_usage_total"])
    task_distribution = dict(task_catalog["stats"])
    # 前端使用 "completed" 而非 "success" 作为键名
    task_distribution["completed"] = task_distribution.pop("success", 0)

    resource_usage = _build_resource_usage_series(
        swarm_name=swarm_name,
        runs=runs,
        graph=graph,
    )

    success_rate = 100.0 if total_runs == 0 else round((len(successful_runs) / max(total_runs, 1)) * 100.0, 1)
    return {
        "success_rate": success_rate,
        "throughput": throughput,
        "token_usage": token_usage,
        "task_distribution": task_distribution,
        "resource_usage": resource_usage,
        "run_count": total_runs,
        "active_runs": registry.runs.active_run_count(swarm_name),
        "agent_count": agent_stats["total"],
        "tool_count": len(swarm.core.tools),
        "api_count": len(getattr(swarm.core, "apis", {})),
        "native_api_count": sum(
            1
            for metadata in getattr(swarm.core, "api_sources", {}).values()
            if str(metadata.get("origin", "")).strip().lower() == "native"
        ),
        "package_api_count": sum(
            1
            for metadata in getattr(swarm.core, "api_sources", {}).values()
            if str(metadata.get("origin", "")).strip().lower() == "package"
        ),
    }
