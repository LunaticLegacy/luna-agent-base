from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from web.catalog import (
    build_agent_catalog,
    build_event_catalog,
    build_log_catalog,
    build_metrics_catalog,
    build_swarm_stats,
    build_task_catalog,
    build_tool_catalog,
)
from web.errors import ApiError

catalog_bp = Blueprint("catalog", __name__)


def _get_runtime_registry():
    registry = current_app.extensions.get("angelus_runtime")
    if registry is None:
        raise ApiError("Runtime registry is not initialized.")
    return registry


def _parse_int(raw, default: int) -> int:
    try:
        return int(raw)
    except Exception:
        return default


def _parse_time_arg(name: str):
    value = request.args.get(name)
    return value if value else None


@catalog_bp.get("/swarms/<string:swarm_name>/agents")
def list_swarm_agents(swarm_name: str):
    registry = _get_runtime_registry()
    swarm = registry.get_swarm(swarm_name)
    request_args = request.args
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
        "active": sum(1 for agent in filtered if agent.get("status") == "busy"),
        "success_rate": round(
            sum(float(agent.get("success_rate", 0.0)) for agent in filtered) / len(filtered), 1
        ) if filtered else 0.0,
        "avg_response_time_ms": int(round(
            sum(int(agent.get("avg_response_time_ms", 0)) for agent in filtered) / len(filtered)
        )) if filtered else 0,
        "token_usage_total": sum(int(agent.get("token_usage_total", 0)) for agent in filtered),
    }

    return jsonify(
        {
            "success": True,
            "swarm": swarm_name,
            "total": len(filtered),
            "agents": filtered,
            "stats": filtered_stats,
        }
    )


@catalog_bp.get("/tasks")
def list_tasks():
    registry = _get_runtime_registry()
    swarm_name = request.args.get("swarm") or None
    if swarm_name:
        registry.get_swarm(swarm_name)

    page = _parse_int(request.args.get("page", 1), 1)
    limit = _parse_int(request.args.get("limit", 20), 20)
    payload = build_task_catalog(
        registry,
        swarm_name=swarm_name,
        status=request.args.get("status"),
        priority=request.args.get("priority"),
        executor=request.args.get("executor"),
        from_time=request.args.get("from"),
        to_time=request.args.get("to"),
        q=request.args.get("q"),
        page=page,
        limit=limit,
    )
    return jsonify({"success": True, **payload})


@catalog_bp.get("/tools")
def list_tools():
    registry = _get_runtime_registry()
    payload = build_tool_catalog(
        registry,
        type_filter=request.args.get("type"),
        status=request.args.get("status"),
        q=request.args.get("q"),
        swarm_name=request.args.get("swarm") or None,
    )
    return jsonify({"success": True, **payload})


@catalog_bp.get("/swarms/<string:swarm_name>/stats")
def swarm_stats(swarm_name: str):
    registry = _get_runtime_registry()
    registry.get_swarm(swarm_name)
    payload = build_swarm_stats(registry, swarm_name)
    return jsonify({"success": True, **payload})


@catalog_bp.get("/events")
def list_events():
    registry = _get_runtime_registry()
    payload = build_event_catalog(
        registry,
        level=request.args.get("level"),
        source=request.args.get("source"),
        from_time=_parse_time_arg("from"),
        to_time=_parse_time_arg("to"),
        q=request.args.get("q"),
        page=_parse_int(request.args.get("page", 1), 1),
        limit=_parse_int(request.args.get("limit", 50), 50),
    )
    return jsonify({"success": True, **payload})


@catalog_bp.get("/logs")
def list_logs():
    registry = _get_runtime_registry()
    payload = build_log_catalog(
        registry,
        level=request.args.get("level"),
        service=request.args.get("service"),
        from_time=_parse_time_arg("from"),
        to_time=_parse_time_arg("to"),
        q=request.args.get("q"),
        page=_parse_int(request.args.get("page", 1), 1),
        limit=_parse_int(request.args.get("limit", 100), 100),
    )
    return jsonify({"success": True, **payload})


@catalog_bp.get("/metrics")
def metrics():
    registry = _get_runtime_registry()
    payload = build_metrics_catalog(
        registry,
        window=request.args.get("window"),
        resolution=request.args.get("resolution"),
    )
    return jsonify(payload)
