from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Optional

from core.executor import GraphExecutor
from core.results import ExecutionState
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from web.deps import get_runtime_registry, parse_bool, parse_int, parse_json_body
from web.errors import ApiError, ConflictError, NotFoundError
from web.runs import RunRegistry, serialize_graph_snapshot, serialize_swarm_detail
from web.runtime import RuntimeRegistry
from web.swarm_globals_store import save_global_variables, serialize_global_variables
from web.utils import to_jsonable

router = APIRouter()


_ARTIFACT_PATH_PATTERNS = [
    re.compile(r"(?:将该文件命名|命名|文件名)\s*为\s+([^\s,;，。]+)", re.IGNORECASE),
    re.compile(r"(?:保存为)\s+([^\s,;，。]+)", re.IGNORECASE),
    re.compile(r"(?:name it|save as)\s+([^\s,;，。]+)", re.IGNORECASE),
]


def extract_artifact_path(text: str) -> Optional[str]:
    """Scan user text for an explicit filename/path request."""
    for pattern in _ARTIFACT_PATH_PATTERNS:
        match = pattern.search(text)
        if match:
            candidate = match.group(1).strip()
            if "." in candidate:
                return candidate
    return None


def _build_artifact_info(original_request: str) -> Dict[str, Any]:
    artifact: Dict[str, Any] = {}
    path = extract_artifact_path(original_request)
    if path:
        artifact = {
            "path": path,
            "filename": Path(path).name,
            "type": "python_module" if path.endswith(".py") else "file",
        }
    return artifact


def normalize_initial_payload(raw: Any) -> Any:
    """Normalize an HTTP input into the canonical Envelope format.

    Rules:
    - Already-envelope dicts are returned as-is.
    - Dicts containing ``text`` use that value as ``original_request``.
    - Strings become ``original_request`` directly.
    - Everything else is coerced via ``str()``.
    """
    if isinstance(raw, dict):
        if raw.get("_envelope") is True or "original_request" in raw:
            return raw
        text = raw.get("text")
        if text is not None:
            return {
                "_envelope": True,
                "original_request": text,
                "artifact": _build_artifact_info(text),
                "requirements": [],
                "constraints": [],
                "attachments": [],
                "raw_input": raw,
            }
        original = str(raw)
        return {
            "_envelope": True,
            "original_request": original,
            "artifact": _build_artifact_info(original),
            "requirements": [],
            "constraints": [],
            "attachments": [],
            "raw_input": raw,
        }
    if isinstance(raw, str):
        return {
            "_envelope": True,
            "original_request": raw,
            "artifact": _build_artifact_info(raw),
            "requirements": [],
            "constraints": [],
            "attachments": [],
            "raw_input": raw,
        }
    original = str(raw)
    return {
        "_envelope": True,
        "original_request": original,
        "artifact": _build_artifact_info(original),
        "requirements": [],
        "constraints": [],
        "attachments": [],
        "raw_input": raw,
    }


def _get_swarm_or_404(request: Request, swarm_name: str):
    return get_runtime_registry(request).get_swarm(swarm_name)


def resolve_final_output(state: ExecutionState) -> Any:
    """Return the human-facing final output for a completed run.

    Legacy mode simply returns ``state.payload``.
    Envelope mode walks ``metadata.outputs`` and extracts the most
    meaningful field from the last node output.
    """
    if not state.is_envelope:
        return state.payload
    outputs = state.metadata.get("outputs")
    if isinstance(outputs, dict) and outputs:
        last_key = list(outputs.keys())[-1]
        last_output = outputs[last_key]
        if isinstance(last_output, dict):
            for key in ("final_answer", "final_report", "approved_report", "draft_report", "content"):
                value = last_output.get(key)
                if value is not None:
                    return value
            return last_output
        return last_output
    return state.payload


def _get_runs_registry(request: Request) -> RunRegistry:
    return get_runtime_registry(request).runs


def _serialize_swarm_with_runtime(registry: RuntimeRegistry, swarm) -> dict:
    payload = serialize_swarm_detail(swarm)
    payload["active_run_count"] = registry.runs.active_run_count(swarm.manifest.swarm_name)
    payload["active_run_ids"] = registry.runs.active_run_ids(swarm.manifest.swarm_name)
    return payload


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


async def _execute_swarm_run(request: Request, swarm_name: str, *, use_background: bool = False):
    swarm = _get_swarm_or_404(request, swarm_name)
    graph = swarm.core.get_execution_graph()
    if graph is None:
        raise ApiError(f"Swarm '{swarm_name}' has no agent graph attached.")

    request_data = await parse_json_body(request)
    payload = normalize_initial_payload(request_data.get("input"))
    rounds = int(request_data.get("rounds", 0))
    meta_mode = bool(request_data.get("meta_mode", False))
    runs_registry = _get_runs_registry(request)

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
        return JSONResponse(
            {
                "success": True,
                "status": "started",
                "swarm": swarm_name,
                "run": record.snapshot(),
            },
            status_code=202,
        )

    if meta_mode:
        from core.meta_executor import MetaExecutor

        meta = MetaExecutor(max_iterations=5)
        state = await meta.run(graph, swarm.core, payload, rounds=rounds)
    else:
        state = await GraphExecutor().execute(graph, swarm.core, payload, rounds=rounds)

    return {
        "success": True,
        "swarm": swarm_name,
        "rounds": state.rounds,
        "output": to_jsonable(resolve_final_output(state)),
        "trace": to_jsonable(state.trace),
        "metadata": to_jsonable(state.metadata),
    }


@router.get("")
async def list_swarms(request: Request):
    registry = get_runtime_registry(request)
    return {
        "success": True,
        "swarms": [
            _serialize_swarm_with_runtime(registry, swarm)
            for swarm in registry.swarms.values()
        ],
    }


@router.post("")
async def load_swarm(request: Request):
    registry = get_runtime_registry(request)
    request_data = await parse_json_body(request)
    source = request_data.get("package_path") or request_data.get("source") or request_data.get("swarm_name")
    if not source:
        raise ApiError("Request body must include 'package_path', 'source', or 'swarm_name'.")

    replace = parse_bool(request_data.get("replace", False))
    loaded = registry.load_swarm(source, replace=replace)
    return JSONResponse(
        {
            "success": True,
            "action": "load",
            "swarm": _serialize_swarm_with_runtime(registry, loaded),
        },
        status_code=201,
    )


@router.get("/{swarm_name}")
async def get_swarm(swarm_name: str, request: Request):
    swarm = _get_swarm_or_404(request, swarm_name)
    return {"success": True, "swarm": _serialize_swarm_with_runtime(get_runtime_registry(request), swarm)}


@router.get("/{swarm_name}/agent-graph")
async def get_swarm_graph(swarm_name: str, request: Request):
    swarm = _get_swarm_or_404(request, swarm_name)
    return {"success": True, "swarm": swarm_name, "graph": _serialize_graph_with_state(swarm)}


@router.get("/{swarm_name}/globals")
async def get_swarm_globals(swarm_name: str, request: Request):
    swarm = _get_swarm_or_404(request, swarm_name)
    return {
        "success": True,
        "swarm": swarm_name,
        "globals": serialize_global_variables(swarm.manifest.global_variables),
    }


@router.get("/{swarm_name}/apis")
async def get_swarm_apis(swarm_name: str, request: Request):
    swarm = _get_swarm_or_404(request, swarm_name)
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
    return {"success": True, "swarm": swarm_name, "apis": apis}


@router.put("/{swarm_name}/globals")
async def update_swarm_globals(swarm_name: str, request: Request):
    swarm = _get_swarm_or_404(request, swarm_name)
    request_data = await parse_json_body(request)
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
    return {
        "success": True,
        "swarm": swarm_name,
        "globals": serialize_global_variables(updated_globals),
    }


@router.get("/{swarm_name}/execution-graph")
async def get_swarm_execution_graph(swarm_name: str, request: Request):
    swarm = _get_swarm_or_404(request, swarm_name)
    return {"success": True, "swarm": swarm_name, "graph": _serialize_execution_graph_with_state(swarm)}


@router.post("/{swarm_name}/graph/state")
async def get_swarm_graph_state(swarm_name: str, request: Request):
    swarm = _get_swarm_or_404(request, swarm_name)
    graph_getter = getattr(swarm.core, "get_agent_graph", None)
    graph = graph_getter() if callable(graph_getter) else swarm.core.get_execution_graph()
    if graph is None:
        raise ApiError(f"Swarm '{swarm_name}' has no agent graph attached.")
    state = swarm.core.get_graph_runtime_state()
    request_data = await parse_json_body(request)
    since_revision = parse_int(request_data.get("since_revision"), 0)
    return {
        "success": True,
        "swarm": swarm_name,
        "graph": state,
        "has_changes_since": int(state.get("revision") or 0) > since_revision,
    }


@router.post("/{swarm_name}/graph/diff")
async def get_swarm_graph_diff(swarm_name: str, request: Request):
    swarm = _get_swarm_or_404(request, swarm_name)
    graph_getter = getattr(swarm.core, "get_agent_graph", None)
    graph = graph_getter() if callable(graph_getter) else swarm.core.get_execution_graph()
    if graph is None:
        raise ApiError(f"Swarm '{swarm_name}' has no agent graph attached.")
    request_data = await parse_json_body(request)
    since_revision = parse_int(request_data.get("since_revision"), 0)
    diff = swarm.core.get_graph_runtime_diff(since_revision=since_revision)
    return {"success": True, "swarm": swarm_name, "patch": diff}


@router.get("/{swarm_name}/graph/events/from/{since_revision}")
async def stream_swarm_graph_events(swarm_name: str, since_revision: int, request: Request):
    swarm = _get_swarm_or_404(request, swarm_name)
    graph_getter = getattr(swarm.core, "get_agent_graph", None)
    graph = graph_getter() if callable(graph_getter) else swarm.core.get_execution_graph()
    if graph is None:
        raise ApiError(f"Swarm '{swarm_name}' has no execution graph attached.")
    async def _stream():
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
            await asyncio.sleep(1.5)

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{swarm_name}/thought-graph")
async def get_swarm_thought_graph(swarm_name: str, request: Request):
    swarm = _get_swarm_or_404(request, swarm_name)
    snapshot = swarm.core.get_cognitive_graph_snapshot()
    return {"success": True, "swarm": swarm_name, "thought_graph": to_jsonable(snapshot)}


@router.get("/{swarm_name}/execution-traces/latest")
async def get_swarm_execution_trace(swarm_name: str, request: Request):
    runs = [record for record in _get_runs_registry(request).list_runs(swarm_name) if record.swarm_name == swarm_name]
    record = runs[-1] if runs else None

    if record is None:
        return {"success": True, "swarm": swarm_name, "run": None, "events": []}

    return {
        "success": True,
        "swarm": swarm_name,
        "run": record.snapshot(),
        "events": to_jsonable(record.events),
    }


@router.get("/{swarm_name}/execution-traces/{run_id}")
async def get_swarm_execution_trace_by_run(swarm_name: str, run_id: str, request: Request):
    record = _get_runs_registry(request).get_run(run_id)
    if record is None or record.swarm_name != swarm_name:
        raise NotFoundError(f"Unknown run for swarm '{swarm_name}': {run_id}")
    return {
        "success": True,
        "swarm": swarm_name,
        "run": record.snapshot(),
        "events": to_jsonable(record.events),
    }


@router.post("/{swarm_name}/runs/execute")
async def run_swarm(swarm_name: str, request: Request):
    return await _execute_swarm_run(request, swarm_name)


@router.post("/{swarm_name}/runs")
async def create_run(swarm_name: str, request: Request):
    return await _execute_swarm_run(request, swarm_name, use_background=True)


@router.delete("/{swarm_name}")
async def unload_swarm(swarm_name: str, request: Request):
    registry = get_runtime_registry(request)
    request_data = await parse_json_body(request)
    force = parse_bool(request_data.get("force", False))
    unloaded = registry.unload_swarm(swarm_name, force=force)
    return {
        "success": True,
        "action": "unload",
        "swarm": {
            "swarm_name": unloaded.manifest.swarm_name,
            "package_path": str(unloaded.package_path),
        },
    }


@router.post("/{swarm_name}/reload")
async def reload_swarm(swarm_name: str, request: Request):
    registry = get_runtime_registry(request)
    request_data = await parse_json_body(request)
    force = parse_bool(request_data.get("force", False))
    source = request_data.get("package_path") or request_data.get("source")
    reloaded = registry.reload_swarm(swarm_name, force=force, source=source)
    return {
        "success": True,
        "action": "reload",
        "swarm": _serialize_swarm_with_runtime(registry, reloaded),
    }


@router.post("/{swarm_name}/agents/{agent_id}/round")
async def run_agent_round(swarm_name: str, agent_id: str, request: Request):
    swarm = _get_swarm_or_404(request, swarm_name)
    agent = swarm.core.get_agent(agent_id)
    request_data = await parse_json_body(request)
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
    return {
        "success": True,
        "swarm": swarm_name,
        "agent_id": agent_id,
        "result": to_jsonable(result),
        "context": to_jsonable(agent.get_context_snapshot()),
    }
