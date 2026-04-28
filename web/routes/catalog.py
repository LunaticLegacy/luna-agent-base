"""Catalog 查询路由。

聚合 Agent、Tool、Swarm Stats、Events、Logs、Metrics 六大类目的
搜索/查询接口，所有端点均从运行时注册表提取数据并通过 catalog 构建函数
转换为前端可用的结构化响应。
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from web.catalog import (
    build_agent_catalog,
    build_event_catalog,
    build_log_catalog,
    build_metrics_catalog,
    build_swarm_stats,
    build_tool_catalog,
)
from web.deps import get_runtime_registry, parse_json_body

router = APIRouter()


async def _json_filters(request: Request) -> dict:
    """读取请求体作为过滤条件字典，空体视为空字典。

    Args:
        request: FastAPI 请求对象。

    Returns:
        解析后的字典。
    """
    return await parse_json_body(request)


@router.post("/catalog/swarms/{swarm_name}/agents/search")
async def list_swarm_agents(swarm_name: str, request: Request):
    """查询指定 swarm 的 Agent 目录并支持多维度过滤。

    过滤维度包括：status、type、capability、tag、全文搜索 q。

    Args:
        swarm_name: 目标 swarm 名称。
        request: 请求体携带过滤条件。

    Returns:
        包含过滤后 agents 与聚合 stats 的字典。
    """
    registry = get_runtime_registry(request)
    swarm = registry.get_swarm(swarm_name)
    request_args = await _json_filters(request)
    agents, _ = build_agent_catalog(swarm, registry.runs.list_runs(swarm_name))

    normalized_query = str(request_args.get("q", "")).strip().lower()
    normalized_status = str(request_args.get("status", "")).strip().lower()
    normalized_type = str(request_args.get("type", "")).strip().lower()
    normalized_capability = str(request_args.get("capability", "")).strip().lower()
    normalized_tag = str(request_args.get("tag", "")).strip().lower()

    filtered = []
    for agent in agents:
        if normalized_status and str(agent.get("status", "")).lower() != normalized_status:
            continue
        if normalized_type and str(agent.get("type", "")).lower() != normalized_type:
            continue
        if normalized_capability:
            capabilities = " ".join(str(item).lower() for item in agent.get("capabilities", []))
            if normalized_capability not in capabilities:
                continue
        if normalized_tag:
            tags = " ".join(str(item).lower() for item in agent.get("tags", []))
            if normalized_tag not in tags:
                continue
        if normalized_query:
            searchable = " ".join(
                [
                    str(agent.get("id", "")),
                    str(agent.get("name", "")),
                    str(agent.get("type", "")),
                    " ".join(str(item) for item in agent.get("capabilities", [])),
                    " ".join(str(item) for item in agent.get("tags", [])),
                ]
            ).lower()
            if normalized_query not in searchable:
                continue
        filtered.append(agent)

    filtered_stats = {
        "total": len(filtered),
        "active": sum(1 for agent in filtered if agent.get("status") == "running"),
        "success_rate": round(
            sum(float(agent.get("success_rate", 0.0)) for agent in filtered) / len(filtered), 1
        ) if filtered else 0.0,
        "avg_response_time_ms": int(round(
            sum(int(agent.get("avg_response_time_ms", 0)) for agent in filtered) / len(filtered)
        )) if filtered else 0,
        "token_usage_total": sum(int(agent.get("token_usage_total", 0)) for agent in filtered),
    }

    return {
        "success": True,
        "swarm": swarm_name,
        "total": len(filtered),
        "agents": filtered,
        "stats": filtered_stats,
    }


@router.post("/catalog/tools/search")
async def list_tools(request: Request):
    """跨 swarm 查询 Tool 目录。

    Args:
        request: 请求体携带 type、status、q、swarm 等过滤条件。

    Returns:
        包含 tools 列表与 stats 的字典。
    """
    registry = get_runtime_registry(request)
    request_args = await _json_filters(request)
    payload = build_tool_catalog(
        registry,
        type_filter=request_args.get("type"),
        status=request_args.get("status"),
        q=request_args.get("q"),
        swarm_name=request_args.get("swarm") or None,
    )
    return {"success": True, **payload}


@router.get("/catalog/swarms/{swarm_name}/stats")
async def swarm_stats(swarm_name: str, request: Request):
    """获取指定 swarm 的综合统计信息。

    Args:
        swarm_name: 目标 swarm 名称。
        request: FastAPI 请求对象。

    Returns:
        包含成功率、吞吐量、资源使用等字段的字典。
    """
    registry = get_runtime_registry(request)
    registry.get_swarm(swarm_name)
    payload = build_swarm_stats(registry, swarm_name)
    return {"success": True, **payload}


@router.post("/catalog/events/search")
async def list_events(request: Request):
    """查询可观测性事件目录。

    Args:
        request: 请求体携带 level、source、from、to、q、page、limit。

    Returns:
        包含事件列表与 stats 的字典。
    """
    registry = get_runtime_registry(request)
    request_args = await _json_filters(request)
    payload = build_event_catalog(
        registry,
        level=request_args.get("level"),
        source=request_args.get("source"),
        from_time=request_args.get("from"),
        to_time=request_args.get("to"),
        q=request_args.get("q"),
        page=int(request_args.get("page", 1) or 1),
        limit=int(request_args.get("limit", 50) or 50),
    )
    return {"success": True, **payload}


@router.post("/catalog/logs/search")
async def list_logs(request: Request):
    """查询日志目录。

    Args:
        request: 请求体携带 level、service、from、to、q、page、limit。

    Returns:
        包含日志列表与级别统计 stats 的字典。
    """
    registry = get_runtime_registry(request)
    request_args = await _json_filters(request)
    payload = build_log_catalog(
        registry,
        level=request_args.get("level"),
        service=request_args.get("service"),
        from_time=request_args.get("from"),
        to_time=request_args.get("to"),
        q=request_args.get("q"),
        page=int(request_args.get("page", 1) or 1),
        limit=int(request_args.get("limit", 100) or 100),
    )
    return {"success": True, **payload}


@router.post("/catalog/metrics")
async def metrics(request: Request):
    """查询运行时指标时间序列。

    Args:
        request: 请求体携带 window（时间窗口）与 resolution（采样精度）。

    Returns:
        包含 CPU、内存、延迟、吞吐量、Token 用量、错误率序列的字典。
    """
    registry = get_runtime_registry(request)
    request_args = await _json_filters(request)
    return build_metrics_catalog(
        registry,
        window=request_args.get("window"),
        resolution=request_args.get("resolution"),
    )
