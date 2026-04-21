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
from web.utils import to_jsonable

swarms_bp = Blueprint("swarms", __name__, url_prefix="/swarms")


def _get_runtime_registry():
    registry = current_app.extensions.get("angelus_runtime")
    if registry is None:
        raise ApiError("Runtime registry is not initialized.")
    return registry


def _get_swarm_or_404(swarm_name: str):
    registry = _get_runtime_registry()
    swarms = registry.get("swarms", {})
    swarm = swarms.get(swarm_name)
    if swarm is None:
        raise NotFoundError(f"Unknown swarm: {swarm_name}")
    return swarm


def _get_runs_registry() -> RunRegistry:
    registry = _get_runtime_registry()
    runs = registry.get("runs")
    if runs is None:
        raise ApiError("Run registry is not initialized.")
    return runs


@swarms_bp.get("/")
def list_swarms():
    registry = _get_runtime_registry()
    swarms = registry.get("swarms", {})
    payload = [serialize_swarm_summary(swarm) for swarm in swarms.values()]
    return jsonify({"success": True, "swarms": payload})


@swarms_bp.get("/<string:swarm_name>")
def get_swarm(swarm_name: str):
    swarm = _get_swarm_or_404(swarm_name)
    return jsonify({"success": True, "swarm": serialize_swarm_detail(swarm)})


@swarms_bp.get("/<string:swarm_name>/graph")
def get_swarm_graph(swarm_name: str):
    swarm = _get_swarm_or_404(swarm_name)
    graph = swarm.core.get_execution_graph()
    if graph is None:
        raise ApiError(f"Swarm '{swarm_name}' has no execution graph attached.")
    return jsonify({"success": True, "swarm": swarm_name, "graph": serialize_graph_snapshot(graph)})


@swarms_bp.post("/<string:swarm_name>/run")
async def run_swarm(swarm_name: str):
    swarm = _get_swarm_or_404(swarm_name)
    graph = swarm.core.get_execution_graph()
    if graph is None:
        raise ApiError(f"Swarm '{swarm_name}' has no execution graph attached.")

    request_data = request.get_json(silent=True) or {}
    payload = request_data.get("input")
    rounds = int(request_data.get("rounds", 0))
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


@swarms_bp.post("/<string:swarm_name>/runs")
def start_swarm_run(swarm_name: str):
    swarm = _get_swarm_or_404(swarm_name)
    graph = swarm.core.get_execution_graph()
    if graph is None:
        raise ApiError(f"Swarm '{swarm_name}' has no execution graph attached.")

    request_data = request.get_json(silent=True) or {}
    payload = request_data.get("input")
    rounds = int(request_data.get("rounds", 0))
    record = _get_runs_registry().launch_run(
        swarm_name=swarm_name,
        core=swarm.core,
        graph=graph,
        initial_payload=payload,
        rounds=rounds,
    )
    return jsonify(
        {
            "success": True,
            "status": "started",
            "swarm": swarm_name,
            "run": record.snapshot(),
        }
    ), 202


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
