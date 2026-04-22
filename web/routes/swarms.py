from __future__ import annotations

from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context

from web.errors import ApiError, NotFoundError
from web.runs import (
    RunRegistry,
    serialize_graph_snapshot,
    serialize_swarm_detail,
    serialize_swarm_summary,
    stream_run_events,
)
from web.runtime import RuntimeRegistry
from web.utils import to_jsonable

swarms_bp = Blueprint("swarms", __name__, url_prefix="/swarms")


def _get_runtime_registry() -> RuntimeRegistry:
    registry = current_app.extensions.get("angelus_runtime")
    if registry is None:
        raise ApiError("Runtime registry is not initialized.")
    return registry


def _get_swarm_or_404(swarm_name: str):
    return _get_runtime_registry().get_swarm(swarm_name)


def _get_runs_registry() -> RunRegistry:
    return _get_runtime_registry().runs


def _serialize_swarm_with_runtime(swarm) -> dict:
    payload = serialize_swarm_detail(swarm)
    registry = _get_runtime_registry()
    payload["active_run_count"] = registry.runs.active_run_count(swarm.manifest.swarm_name)
    payload["active_run_ids"] = registry.runs.active_run_ids(swarm.manifest.swarm_name)
    return payload


def _parse_bool(raw, default: bool = False) -> bool:
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    value = str(raw).strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    return default


async def _execute_swarm_run(swarm_name: str, *, use_background: bool = False):
    swarm = _get_swarm_or_404(swarm_name)
    graph = swarm.core.get_execution_graph()
    if graph is None:
        raise ApiError(f"Swarm '{swarm_name}' has no execution graph attached.")

    request_data = request.get_json(silent=True) or {}
    payload = request_data.get("input")
    rounds = int(request_data.get("rounds", 0))
    meta_mode = bool(request_data.get("meta_mode", False))

    if use_background:
        record = _get_runs_registry().launch_run(
            swarm_name=swarm_name,
            core=swarm.core,
            graph=graph,
            initial_payload=payload,
            rounds=rounds,
            meta_mode=meta_mode,
        )
        return jsonify(
            {
                "success": True,
                "status": "started",
                "swarm": swarm_name,
                "run": record.snapshot(),
            }
        ), 202

    if meta_mode:
        from core.meta_executor import MetaExecutor

        meta = MetaExecutor(max_iterations=5)
        state = await meta.run(graph, swarm.core, payload, rounds=rounds)
    else:
        state = await graph.run(swarm.core, payload, rounds=rounds)

    return jsonify(
        {
            "success": True,
            "swarm": swarm_name,
            "rounds": state.rounds,
            "output": to_jsonable(state.payload),
            "trace": to_jsonable(state.trace),
            "metadata": to_jsonable(state.metadata),
        }
    )


@swarms_bp.post("/load")
def load_swarm():
    registry = _get_runtime_registry()
    request_data = request.get_json(silent=True) or {}
    source = request_data.get("package_path") or request_data.get("source") or request_data.get("swarm_name")
    if not source:
        raise ApiError("Request body must include 'package_path', 'source', or 'swarm_name'.")

    replace = _parse_bool(request_data.get("replace", False))
    loaded = registry.load_swarm(source, replace=replace)
    return jsonify(
        {
            "success": True,
            "action": "load",
            "swarm": _serialize_swarm_with_runtime(loaded),
        }
    ), 201


@swarms_bp.get("/<string:swarm_name>")
def get_swarm(swarm_name: str):
    swarm = _get_swarm_or_404(swarm_name)
    return jsonify({"success": True, "swarm": _serialize_swarm_with_runtime(swarm)})


@swarms_bp.get("/<string:swarm_name>/graph")
def get_swarm_graph(swarm_name: str):
    swarm = _get_swarm_or_404(swarm_name)
    graph = swarm.core.get_execution_graph()
    if graph is None:
        raise ApiError(f"Swarm '{swarm_name}' has no execution graph attached.")
    return jsonify({"success": True, "swarm": swarm_name, "graph": serialize_graph_snapshot(graph)})


@swarms_bp.post("/<string:swarm_name>/run")
async def run_swarm(swarm_name: str):
    return await _execute_swarm_run(swarm_name)


@swarms_bp.post("/<string:swarm_name>/start")
async def start_swarm(swarm_name: str):
    return await _execute_swarm_run(swarm_name)


@swarms_bp.post("/<string:swarm_name>/runs")
async def start_swarm_run(swarm_name: str):
    return await _execute_swarm_run(swarm_name, use_background=True)


@swarms_bp.post("/<string:swarm_name>/start/background")
async def start_swarm_background(swarm_name: str):
    return await _execute_swarm_run(swarm_name, use_background=True)


@swarms_bp.get("/runs/<string:run_id>")
def get_run(run_id: str):
    record = _get_runs_registry().get_run(run_id)
    if record is None:
        raise NotFoundError(f"Unknown run: {run_id}")
    return jsonify({"success": True, "run": record.snapshot()})


@swarms_bp.get("/runs/<string:run_id>/events")
def stream_run(run_id: str):
    record = _get_runs_registry().get_run(run_id)
    if record is None:
        raise NotFoundError(f"Unknown run: {run_id}")

    response = Response(
        stream_with_context(stream_run_events(record)),
        mimetype="text/event-stream",
    )
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response


@swarms_bp.delete("/<string:swarm_name>")
def unload_swarm(swarm_name: str):
    registry = _get_runtime_registry()
    force = _parse_bool(request.args.get("force", False))
    unloaded = registry.unload_swarm(swarm_name, force=force)
    return jsonify(
        {
            "success": True,
            "action": "unload",
            "swarm": {
                "swarm_name": unloaded.manifest.swarm_name,
                "package_path": str(unloaded.package_path),
            },
        }
    )


@swarms_bp.post("/<string:swarm_name>/reload")
def reload_swarm(swarm_name: str):
    registry = _get_runtime_registry()
    request_data = request.get_json(silent=True) or {}
    force = _parse_bool(request_data.get("force", request.args.get("force", False)))
    source = request_data.get("package_path") or request_data.get("source")
    reloaded = registry.reload_swarm(swarm_name, force=force, source=source)
    return jsonify(
        {
            "success": True,
            "action": "reload",
            "swarm": _serialize_swarm_with_runtime(reloaded),
        }
    )


@swarms_bp.post("/<string:swarm_name>/agents/<string:agent_id>/round")
async def run_agent_round(swarm_name: str, agent_id: str):
    swarm = _get_swarm_or_404(swarm_name)
    agent = swarm.core.get_agent(agent_id)
    request_data = request.get_json(silent=True) or {}
    user_message = str(request_data.get("message", "")).strip()
    if not user_message:
        raise ApiError("Request body must include a non-empty 'message'.")

    rounds = int(request_data.get("rounds", 0))
    additional_prompt = request_data.get("additional_prompt")
    result = await agent.round_call(
        rounds=rounds,
        user_message=user_message,
        additional_prompt=additional_prompt,
    )
    return jsonify(
        {
            "success": True,
            "swarm": swarm_name,
            "agent_id": agent_id,
            "result": to_jsonable(result),
            "context": to_jsonable(agent.get_context_snapshot()),
        }
    )
