from __future__ import annotations

from fastapi import APIRouter, Request

from web.catalog import (
    build_agent_catalog,
    build_event_catalog,
    build_log_catalog,
    build_metrics_catalog,
    build_swarm_stats,
    build_task_catalog,
    build_tool_catalog,
)
from web.deps import get_runtime_registry, parse_int

router = APIRouter()


def _parse_time_arg(request: Request, name: str):
    value = request.query_params.get(name)
    return value if value else None


@router.get("/swarms/{swarm_name}/agents")
async def list_swarm_agents(swarm_name: str, request: Request):
    registry = get_runtime_registry(request)
    swarm = registry.get_swarm(swarm_name)
    request_args = request.query_params
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


@router.get("/tasks")
async def list_tasks(request: Request):
    registry = get_runtime_registry(request)
    swarm_name = request.query_params.get("swarm") or None
    if swarm_name:
        registry.get_swarm(swarm_name)

    page = parse_int(request.query_params.get("page", 1), 1)
    limit = parse_int(request.query_params.get("limit", 20), 20)
    payload = build_task_catalog(
        registry,
        swarm_name=swarm_name,
        status=request.query_params.get("status"),
        priority=request.query_params.get("priority"),
        executor=request.query_params.get("executor"),
        from_time=request.query_params.get("from"),
        to_time=request.query_params.get("to"),
        q=request.query_params.get("q"),
        page=page,
        limit=limit,
    )
    return {"success": True, **payload}


@router.get("/tools")
async def list_tools(request: Request):
    registry = get_runtime_registry(request)
    payload = build_tool_catalog(
        registry,
        type_filter=request.query_params.get("type"),
        status=request.query_params.get("status"),
        q=request.query_params.get("q"),
        swarm_name=request.query_params.get("swarm") or None,
    )
    return {"success": True, **payload}


@router.get("/swarms/{swarm_name}/stats")
async def swarm_stats(swarm_name: str, request: Request):
    registry = get_runtime_registry(request)
    registry.get_swarm(swarm_name)
    payload = build_swarm_stats(registry, swarm_name)
    return {"success": True, **payload}


@router.get("/events")
async def list_events(request: Request):
    registry = get_runtime_registry(request)
    payload = build_event_catalog(
        registry,
        level=request.query_params.get("level"),
        source=request.query_params.get("source"),
        from_time=_parse_time_arg(request, "from"),
        to_time=_parse_time_arg(request, "to"),
        q=request.query_params.get("q"),
        page=parse_int(request.query_params.get("page", 1), 1),
        limit=parse_int(request.query_params.get("limit", 50), 50),
    )
    return {"success": True, **payload}


@router.get("/logs")
async def list_logs(request: Request):
    registry = get_runtime_registry(request)
    payload = build_log_catalog(
        registry,
        level=request.query_params.get("level"),
        service=request.query_params.get("service"),
        from_time=_parse_time_arg(request, "from"),
        to_time=_parse_time_arg(request, "to"),
        q=request.query_params.get("q"),
        page=parse_int(request.query_params.get("page", 1), 1),
        limit=parse_int(request.query_params.get("limit", 100), 100),
    )
    return {"success": True, **payload}


@router.get("/metrics")
async def metrics(request: Request):
    registry = get_runtime_registry(request)
    return build_metrics_catalog(
        registry,
        window=request.query_params.get("window"),
        resolution=request.query_params.get("resolution"),
    )
