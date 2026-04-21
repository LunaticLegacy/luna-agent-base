from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from web.errors import ApiError, NotFoundError
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


@swarms_bp.get("")
def list_swarms():
    registry = _get_runtime_registry()
    swarms = registry.get("swarms", {})
    payload = []
    for swarm in swarms.values():
        validation = swarm.core.check_execution_graph_available()
        payload.append(
            {
                "swarm_name": swarm.manifest.swarm_name,
                "package_path": str(swarm.package_path),
                "manifest_path": str(swarm.manifest_path),
                "graph_file": swarm.manifest.graph_file,
                "agent_count": len(swarm.core.list_agents()),
                "skill_count": len(swarm.core.list_skills()),
                "tool_count": len(swarm.core.tools),
                "graph_attached": swarm.core.get_execution_graph() is not None,
                "graph_valid": validation.is_valid,
                "graph_errors": validation.errors,
                "graph_warnings": validation.warnings,
            }
        )
    return jsonify({"success": True, "swarms": payload})


@swarms_bp.get("/<string:swarm_name>")
def get_swarm(swarm_name: str):
    swarm = _get_swarm_or_404(swarm_name)
    validation = swarm.core.check_execution_graph_available()
    return jsonify(
        {
            "success": True,
            "swarm": {
                "swarm_name": swarm.manifest.swarm_name,
                "package_path": str(swarm.package_path),
                "manifest_path": str(swarm.manifest_path),
                "graph_file": swarm.manifest.graph_file,
                "agent_files": list(swarm.manifest.agent_files),
                "agent_count": len(swarm.core.list_agents()),
                "skill_count": len(swarm.core.list_skills()),
                "tool_count": len(swarm.core.tools),
                "graph_attached": swarm.core.get_execution_graph() is not None,
                "graph_valid": validation.is_valid,
                "graph_errors": validation.errors,
                "graph_warnings": validation.warnings,
            },
        }
    )


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
