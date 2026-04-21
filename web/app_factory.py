from __future__ import annotations

from pathlib import Path
from typing import Dict

from flask import Flask, Response, jsonify, request, stream_with_context

from core.swarm_loader import SwarmLoaderError, load_all_swarms
from core.swarm_spec import load_root_config
from web.runs import (
    RunRegistry,
    serialize_graph_snapshot,
    serialize_swarm_detail,
    serialize_swarm_summary,
    stream_run_events,
)
from web.utils import to_jsonable

from .errors import register_error_handlers
from .routes import health_bp, swarms_bp


def _load_runtime_registry(config_path: Path) -> Dict[str, object]:
    root_config = load_root_config(config_path)
    swarms = load_all_swarms(root_config.swarm_root)
    return {
        "config_path": config_path,
        "root_config": root_config,
        "swarms": {swarm.manifest.swarm_name: swarm for swarm in swarms},
        "runs": RunRegistry(),
    }


def create_app(config_path: str | Path = "config.toml") -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    config_path = Path(config_path)

    try:
        runtime_registry = _load_runtime_registry(config_path)
    except SwarmLoaderError as exc:
        runtime_registry = {
            "config_path": config_path,
            "root_config": None,
            "swarms": {},
            "load_error": str(exc),
        }

    app.extensions["angelus_runtime"] = runtime_registry

    register_error_handlers(app)
    app.register_blueprint(health_bp, url_prefix="/api")
    app.register_blueprint(swarms_bp, url_prefix="/api")

    @app.get("/")
    def index():
        swarms = runtime_registry.get("swarms", {})
        load_error = runtime_registry.get("load_error")
        return jsonify(
            {
                "success": True,
                "service": "angelus",
                "swarm_count": len(swarms),
                "load_error": load_error,
            }
        )

    @app.get("/api")
    def api_index():
        swarms = runtime_registry.get("swarms", {})
        load_error = runtime_registry.get("load_error")
        return jsonify(
            {
                "success": True,
                "service": "angelus",
                "swarm_count": len(swarms),
                "load_error": load_error,
                "api_root": "/api",
            }
        )

    @app.get("/api/swarms")
    def api_swarms():
        registry = app.extensions.get("angelus_runtime", {})
        swarms = registry.get("swarms", {})
        payload = [serialize_swarm_summary(swarm) for swarm in swarms.values()]
        return jsonify({"success": True, "swarms": payload})

    @app.get("/api/swarms/<string:swarm_name>")
    def api_swarm_detail(swarm_name: str):
        registry = app.extensions.get("angelus_runtime", {})
        swarms = registry.get("swarms", {})
        swarm = swarms.get(swarm_name)
        if swarm is None:
            return jsonify({"success": False, "error": f"Unknown swarm: {swarm_name}"}), 404

        return jsonify({"success": True, "swarm": serialize_swarm_detail(swarm)})

    @app.get("/api/swarms/<string:swarm_name>/graph")
    def api_swarm_graph(swarm_name: str):
        registry = app.extensions.get("angelus_runtime", {})
        swarms = registry.get("swarms", {})
        swarm = swarms.get(swarm_name)
        if swarm is None:
            return jsonify({"success": False, "error": f"Unknown swarm: {swarm_name}"}), 404

        graph = swarm.core.get_execution_graph()
        if graph is None:
            return jsonify(
                {"success": False, "error": f"Swarm '{swarm_name}' has no execution graph attached."}
            ), 400

        return jsonify(
            {
                "success": True,
                "swarm": swarm_name,
                "graph": serialize_graph_snapshot(graph),
            }
        )

    @app.post("/api/swarms/<string:swarm_name>/run")
    async def api_run_swarm(swarm_name: str):
        registry = app.extensions.get("angelus_runtime", {})
        swarms = registry.get("swarms", {})
        swarm = swarms.get(swarm_name)
        if swarm is None:
            return jsonify({"success": False, "error": f"Unknown swarm: {swarm_name}"}), 404

        graph = swarm.core.get_execution_graph()
        if graph is None:
            return jsonify({"success": False, "error": f"Swarm '{swarm_name}' has no execution graph attached."}), 400

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

    @app.post("/api/swarms/<string:swarm_name>/runs")
    def api_start_swarm_run(swarm_name: str):
        registry = app.extensions.get("angelus_runtime", {})
        swarms = registry.get("swarms", {})
        swarm = swarms.get(swarm_name)
        if swarm is None:
            return jsonify({"success": False, "error": f"Unknown swarm: {swarm_name}"}), 404

        graph = swarm.core.get_execution_graph()
        if graph is None:
            return jsonify({"success": False, "error": f"Swarm '{swarm_name}' has no execution graph attached."}), 400

        request_data = request.get_json(silent=True) or {}
        payload = request_data.get("input")
        rounds = int(request_data.get("rounds", 0))
        runs: RunRegistry = registry.get("runs")
        record = runs.launch_run(
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

    @app.get("/api/runs/<string:run_id>")
    def api_get_run(run_id: str):
        registry = app.extensions.get("angelus_runtime", {})
        runs: RunRegistry = registry.get("runs")
        record = runs.get_run(run_id) if runs is not None else None
        if record is None:
            return jsonify({"success": False, "error": f"Unknown run: {run_id}"}), 404
        return jsonify({"success": True, "run": record.snapshot()})

    @app.get("/api/runs/<string:run_id>/events")
    def api_stream_run_events(run_id: str):
        registry = app.extensions.get("angelus_runtime", {})
        runs: RunRegistry = registry.get("runs")
        record = runs.get_run(run_id) if runs is not None else None
        if record is None:
            return jsonify({"success": False, "error": f"Unknown run: {run_id}"}), 404

        response = Response(
            stream_with_context(stream_run_events(record)),
            mimetype="text/event-stream",
        )
        response.headers["Cache-Control"] = "no-cache"
        response.headers["X-Accel-Buffering"] = "no"
        return response

    @app.post("/api/swarms/<string:swarm_name>/agents/<string:agent_id>/round")
    async def api_run_agent_round(swarm_name: str, agent_id: str):
        registry = app.extensions.get("angelus_runtime", {})
        swarms = registry.get("swarms", {})
        swarm = swarms.get(swarm_name)
        if swarm is None:
            return jsonify({"success": False, "error": f"Unknown swarm: {swarm_name}"}), 404

        agent = swarm.core.get_agent(agent_id)
        request_data = request.get_json(silent=True) or {}
        user_message = str(request_data.get("message", "")).strip()
        if not user_message:
            return jsonify({"success": False, "error": "Request body must include a non-empty 'message'."}), 400

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

    return app
