from __future__ import annotations

import json
import time

from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context

from web.errors import ApiError, ConflictError, NotFoundError
from web.swarm_globals_store import save_global_variables, serialize_global_variables
from web.runs import (
    RunRegistry,
    serialize_graph_snapshot,
    serialize_swarm_detail,
    serialize_swarm_summary,
    stream_run_events,
)
from web.runtime import RuntimeRegistry
from web.utils import to_jsonable

swarms_bp = Blueprint("swarms", __name__)


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


def _parse_int(raw, default: int = 0) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _serialize_graph_with_state(swarm) -> dict:
    graph_getter = getattr(swarm.core, "get_agent_graph", None)
    graph = graph_getter() if callable(graph_getter) else swarm.core.get_execution_graph()
    if graph is None:
        raise ApiError(f"Swarm '{swarm.manifest.swarm_name}' has no execution graph attached.")
    payload = serialize_graph_snapshot(graph)
    payload.update(swarm.core.get_graph_runtime_state())
    return payload


def _serialize_execution_graph_with_state(swarm) -> dict:
    graph = swarm.core.get_execution_graph()
    if graph is None:
        raise ApiError(f"Swarm '{swarm.manifest.swarm_name}' has no execution graph attached.")
    payload = serialize_graph_snapshot(graph)
    payload["graph_kind"] = getattr(graph, "graph_kind", "execution")
    return payload


def _parse_bool(raw, default: bool = False) -> bool:
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    value = str(raw).strip().lower()
    if value in {"1", "true", "yes", "y", "on", "True"}:
        return True
    if value in {"0", "false", "no", "n", "off", "False"}:
        return False
    return default


async def _execute_swarm_run(swarm_name: str, *, use_background: bool = False):
    swarm = _get_swarm_or_404(swarm_name)   # get a swarm
    graph = swarm.core.get_execution_graph()    # get the execution graph
    if graph is None:
        raise ApiError(f"Swarm '{swarm_name}' has no agent graph attached.")
        
    request_data = request.get_json(silent=True) or {}
    payload = request_data.get("input")
    rounds = int(request_data.get("rounds", 0))
    meta_mode = bool(request_data.get("meta_mode", False))
    runs_registry = _get_runs_registry()

    if runs_registry.active_run_count(swarm_name) > 0:
        raise ConflictError(
            f"Swarm '{swarm_name}' already has an active run. Wait for it to finish before starting another."
        )

    swarm.core.reset_runtime_state()

    if use_background:
        record = runs_registry.launch_run(
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
    return jsonify({"success": True, "swarm": swarm_name, "graph": _serialize_graph_with_state(swarm)})


@swarms_bp.get("/<string:swarm_name>/globals")
def get_swarm_globals(swarm_name: str):
    swarm = _get_swarm_or_404(swarm_name)
    return jsonify(
        {
            "success": True,
            "swarm": swarm_name,
            "globals": serialize_global_variables(swarm.manifest.global_variables),
        }
    )


@swarms_bp.get("/<string:swarm_name>/apis")
def get_swarm_apis(swarm_name: str):
    swarm = _get_swarm_or_404(swarm_name)
    apis = []
    for api_name in sorted(getattr(swarm.core, "apis", {}).keys()):
        api = swarm.core.get_api(api_name)
        metadata = swarm.core.get_api_metadata(api_name)
        apis.append(
            {
                "name": api_name,
                "origin": metadata.get("origin", "package"),
                "source": metadata.get("source"),
                "type": api.__class__.__name__,
            }
        )
    return jsonify({"success": True, "swarm": swarm_name, "apis": apis})


@swarms_bp.put("/<string:swarm_name>/globals")
def update_swarm_globals(swarm_name: str):
    swarm = _get_swarm_or_404(swarm_name)
    request_data = request.get_json(silent=True) or {}
    globals_section = request_data.get("globals")
    visibility_section = request_data.get("visibility")
    if globals_section is None and visibility_section is None:
        raise ApiError("Request body must include 'globals' and/or 'visibility'.")
    if globals_section is not None and not isinstance(globals_section, dict):
        raise ApiError("'globals' must be a JSON object.")
    if visibility_section is not None and not isinstance(visibility_section, dict):
        raise ApiError("'visibility' must be a JSON object.")

    current_globals = swarm.manifest.global_variables
    values = dict(current_globals.values)
    visibility = {key: list(value) for key, value in current_globals.visibility.items()}
    if isinstance(globals_section, dict):
        for key, value in globals_section.items():
            values[str(key).strip()] = value
    if isinstance(visibility_section, dict):
        for key, agent_list in visibility_section.items():
            if agent_list is None:
                visibility.pop(str(key).strip(), None)
                continue
            if isinstance(agent_list, str):
                agent_list = [agent_list]
            if not isinstance(agent_list, list):
                raise ApiError(f"visibility for '{key}' must be a string array.")
            visibility[str(key).strip()] = [str(item).strip() for item in agent_list if str(item).strip()]

    updated_globals = type(current_globals)(values=values, visibility=visibility)
    save_global_variables(swarm.manifest_path, updated_globals)
    swarm.manifest.global_variables = updated_globals
    swarm.core.set_global_variables(updated_globals)
    swarm.core.record_runtime_change(
        action="set_global_variables",
        subject_kind="globals",
        subject_id=swarm_name,
        detail=serialize_global_variables(updated_globals),
    )
    return jsonify(
        {
            "success": True,
            "swarm": swarm_name,
            "globals": serialize_global_variables(updated_globals),
        }
    )


@swarms_bp.get("/<string:swarm_name>/execution-graph")
def get_swarm_execution_graph(swarm_name: str):
    swarm = _get_swarm_or_404(swarm_name)
    return jsonify({"success": True, "swarm": swarm_name, "graph": _serialize_execution_graph_with_state(swarm)})


@swarms_bp.get("/<string:swarm_name>/graph/state")
def get_swarm_graph_state(swarm_name: str):
    swarm = _get_swarm_or_404(swarm_name)
    graph_getter = getattr(swarm.core, "get_agent_graph", None)
    graph = graph_getter() if callable(graph_getter) else swarm.core.get_execution_graph()
    if graph is None:
        raise ApiError(f"Swarm '{swarm_name}' has no agent graph attached.")
    state = swarm.core.get_graph_runtime_state()
    since_revision = _parse_int(request.args.get("since_revision"), 0)
    return jsonify(
        {
            "success": True,
            "swarm": swarm_name,
            "graph": state,
            "has_changes_since": int(state.get("revision") or 0) > since_revision,
        }
    )


@swarms_bp.get("/<string:swarm_name>/graph/diff")
def get_swarm_graph_diff(swarm_name: str):
    swarm = _get_swarm_or_404(swarm_name)
    graph_getter = getattr(swarm.core, "get_agent_graph", None)
    graph = graph_getter() if callable(graph_getter) else swarm.core.get_execution_graph()
    if graph is None:
        raise ApiError(f"Swarm '{swarm_name}' has no agent graph attached.")
    since_revision = _parse_int(request.args.get("since_revision"), 0)
    diff = swarm.core.get_graph_runtime_diff(since_revision=since_revision)
    return jsonify({"success": True, "swarm": swarm_name, "patch": diff})


@swarms_bp.get("/<string:swarm_name>/graph/events")
def stream_swarm_graph_events(swarm_name: str):
    swarm = _get_swarm_or_404(swarm_name)
    graph_getter = getattr(swarm.core, "get_agent_graph", None)
    graph = graph_getter() if callable(graph_getter) else swarm.core.get_execution_graph()
    if graph is None:
        raise ApiError(f"Swarm '{swarm_name}' has no execution graph attached.")
    since_revision = _parse_int(request.args.get("since_revision"), 0)

    def _stream():
        last_revision = since_revision
        yield "retry: 3000\n\n"
        while True:
            events = swarm.core.get_graph_runtime_events(since_revision=last_revision)
            if events:
                for event in events:
                    last_revision = max(last_revision, int(event.get("revision") or last_revision))
                    payload = {
                        "swarm": swarm_name,
                        "graph_id": event.get("snapshot", {}).get("graph_name"),
                        "revision": event.get("revision"),
                        "change": event.get("change"),
                        "action": event.get("action"),
                        "subject_kind": event.get("subject_kind"),
                        "subject_id": event.get("subject_id"),
                    }
                    yield f"event: graph.changed\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            else:
                yield ": keepalive\n\n"
            time.sleep(1.5)

    response = Response(stream_with_context(_stream()), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response


@swarms_bp.get("/<string:swarm_name>/thought-graph")
def get_swarm_thought_graph(swarm_name: str):
    swarm = _get_swarm_or_404(swarm_name)
    snapshot = swarm.core.get_cognitive_graph_snapshot()
    return jsonify({"success": True, "swarm": swarm_name, "thought_graph": to_jsonable(snapshot)})


@swarms_bp.get("/<string:swarm_name>/execution-trace")
def get_swarm_execution_trace(swarm_name: str):
    runs = [record for record in _get_runs_registry().list_runs(swarm_name) if record.swarm_name == swarm_name]
    run_id = request.args.get("run_id")
    record = None
    if run_id:
        record = _get_runs_registry().get_run(run_id)
        if record is None or record.swarm_name != swarm_name:
            raise NotFoundError(f"Unknown run for swarm '{swarm_name}': {run_id}")
    elif runs:
        record = runs[-1]

    if record is None:
        return jsonify(
            {
                "success": True,
                "swarm": swarm_name,
                "run": None,
                "events": [],
            }
        )

    return jsonify(
        {
            "success": True,
            "swarm": swarm_name,
            "run": record.snapshot(),
            "events": to_jsonable(record.events),
        }
    )


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
