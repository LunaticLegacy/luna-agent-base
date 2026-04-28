"""Agent 目录构建器。

从 swarm 的执行图与运行历史中聚合每个 agent 的状态、能力、成功率、
响应时间与 Token 使用量，生成前端 Agent Catalog 所需的结构化数据。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List

from .shared import (
    _agent_capabilities,
    _agent_role,
    _agent_tags,
    _build_activity_index,
    _entry_active_run_ids,
    _file_mtime_iso,
    _estimate_token_usage,
)


def build_agent_catalog(swarm, runs: Iterable[Any]) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """为指定 swarm 构建 Agent 目录与聚合统计。

    遍历 swarm 中的所有 agent，结合运行事件中的 node 级别统计，
    计算每个 agent 的在线状态、成功率、平均响应时间与 Token 消耗。

    Args:
        swarm: 已加载的 swarm 实例。
        runs: 该 swarm 关联的运行记录迭代器。

    Returns:
        (agents, stats) 元组。agents 为 agent 详情列表；
        stats 包含 total、active、success_rate 等聚合指标。
    """
    # 优先使用 get_agent_graph，若不存在则回退到 get_execution_graph
    graph_getter = getattr(swarm.core, "get_agent_graph", None)
    graph = graph_getter() if callable(graph_getter) else swarm.core.get_execution_graph()
    activity = _build_activity_index(runs)
    graph_mtime = _file_mtime_iso(Path(swarm.package_path) / swarm.manifest.graph_file)
    agents: List[Dict[str, Any]] = []
    total_success_rate = 0.0
    total_response_time = 0.0
    total_token_usage = 0
    active_count = 0

    # 建立 agent_id 到 AgentNode 的映射，用于后续提取节点元数据
    node_by_agent: Dict[str, Any] = {}
    if graph is not None:
        from core.policy import AgentNode

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
        active_run_ids = _entry_active_run_ids(entry)
        avg_response_time_ms = 0
        if completed > 0:
            # 基于实际完成耗时计算平均响应时间
            avg_response_time_ms = int(round(float(entry.get("total_duration_ms", 0.0)) / completed))
        elif node is not None:
            # 无历史完成记录时，按能力数量做简单预估
            avg_response_time_ms = 300 + len(_agent_capabilities(agent_id, node, agent)) * 25
        success_rate = 100.0 if executions == 0 else round((completed / max(executions, 1)) * 100.0, 1)
        status = "running" if active_run_ids else ("error" if failed and not completed else ("offline" if executions == 0 else "online"))
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
        if status == "running":
            active_count += 1

    stats = {
        "total": len(agents),
        "active": active_count,
        "success_rate": round(total_success_rate / len(agents), 1) if agents else 0.0,
        "avg_response_time_ms": int(round(total_response_time / len(agents))) if agents else 0,
        "token_usage_total": total_token_usage,
    }
    return agents, stats
