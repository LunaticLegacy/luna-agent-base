from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from web.deps import get_task_store, parse_json_body
from web.errors import ApiError, NotFoundError
from web.task_store import TaskStore

router = APIRouter()


def _task_to_catalog_item(task_data: dict) -> dict:
    """Map Task snapshot fields to legacy TaskCatalogItem shape for frontend compatibility."""
    return {
        "id": task_data.get("task_id", ""),
        "name": task_data.get("name", ""),
        "status": task_data.get("status", "pending"),
        "priority": task_data.get("priority", "medium"),
        "executor": task_data.get("agent_id") or "system",
        "duration_ms": 0,
        "created_at": task_data.get("created_at", ""),
        "description": task_data.get("description", ""),
        "input": task_data.get("input"),
        "output": task_data.get("output"),
        "logs": task_data.get("metadata", {}).get("logs", []),
        "swarm": task_data.get("swarm_name", ""),
        "failed_count": task_data.get("failed_count", 0),
        "completed_count": task_data.get("completed_count", 0),
        "executed_count": task_data.get("executed_count", 0),
    }


def _store(request: Request) -> TaskStore:
    return get_task_store(request)


@router.get("/swarms/{swarm_name}/tasks")
async def list_tasks(swarm_name: str, request: Request):
    store = _store(request)
    payload = store.list_tasks(
        swarm_name=swarm_name,
        page=1,
        limit=500,
    )
    payload["items"] = [_task_to_catalog_item(item) for item in payload["items"]]
    return {"success": True, **payload}


@router.post("/swarms/{swarm_name}/tasks/search")
async def search_tasks(swarm_name: str, request: Request):
    store = _store(request)
    request_data = await parse_json_body(request)
    payload = store.list_tasks(
        swarm_name=swarm_name,
        status=request_data.get("status") or None,
        agent_id=request_data.get("agent_id") or request_data.get("executor") or None,
        page=int(request_data.get("page", 1) or 1),
        limit=int(request_data.get("limit", 20) or 20),
    )
    payload["items"] = [_task_to_catalog_item(item) for item in payload["items"]]
    return {"success": True, **payload}


@router.get("/swarms/{swarm_name}/task-graph")
async def get_task_graph(swarm_name: str, request: Request):
    store = _store(request)
    return {"success": True, "graph": store.get_graph_snapshot(swarm_name)}


@router.post("/swarms/{swarm_name}/tasks")
async def create_task(swarm_name: str, request: Request):
    store = _store(request)
    request_data = await parse_json_body(request)
    task = store.create_task(swarm_name, request_data)
    return JSONResponse({"success": True, "task": task.snapshot()}, status_code=201)


@router.get("/swarms/{swarm_name}/tasks/{task_id}")
async def get_task(swarm_name: str, task_id: str, request: Request):
    store = _store(request)
    try:
        task = store.get_task(swarm_name, task_id)
    except KeyError as exc:
        raise NotFoundError(str(exc)) from exc
    return {"success": True, "task": task.snapshot()}


@router.put("/swarms/{swarm_name}/tasks/{task_id}")
async def update_task(swarm_name: str, task_id: str, request: Request):
    store = _store(request)
    request_data = await parse_json_body(request)
    try:
        task = store.update_task(swarm_name, task_id, request_data)
    except KeyError as exc:
        raise NotFoundError(str(exc)) from exc
    return {"success": True, "task": task.snapshot()}


@router.post("/swarms/{swarm_name}/tasks/{task_id}/transition")
async def transition_task(swarm_name: str, task_id: str, request: Request):
    store = _store(request)
    request_data = await parse_json_body(request)
    try:
        task = store.transition_task(swarm_name, task_id, request_data)
    except KeyError as exc:
        raise NotFoundError(str(exc)) from exc
    except ValueError as exc:
        raise ApiError(str(exc)) from exc
    return {"success": True, "task": task.snapshot()}


@router.post("/swarms/{swarm_name}/tasks/claim-ready")
async def claim_ready_tasks(swarm_name: str, request: Request):
    store = _store(request)
    request_data = await parse_json_body(request)
    agent_id = request_data.get("agent_id")
    limit_raw = request_data.get("limit")
    limit = int(limit_raw) if limit_raw is not None else None
    tasks = store.claim_ready_tasks(swarm_name, agent_id=agent_id, limit=limit)
    return {"success": True, "tasks": [task.snapshot() for task in tasks]}


@router.delete("/swarms/{swarm_name}/tasks/{task_id}")
async def delete_task(swarm_name: str, task_id: str, request: Request):
    store = _store(request)
    try:
        task = store.delete_task(swarm_name, task_id)
    except KeyError as exc:
        raise NotFoundError(str(exc)) from exc
    return {"success": True, "task": task.snapshot()}


@router.post("/swarms/{swarm_name}/tasks/{task_id}/link")
async def link_task(swarm_name: str, task_id: str, request: Request):
    store = _store(request)
    request_data = await parse_json_body(request)
    to_task_id = request_data.get("to_task_id")
    if not to_task_id:
        raise ApiError("Request body must include 'to_task_id'.")
    try:
        store.link_tasks(swarm_name, task_id, to_task_id)
    except (KeyError, ValueError) as exc:
        raise ApiError(str(exc)) from exc
    return {"success": True, "from_task_id": task_id, "to_task_id": to_task_id}


@router.post("/swarms/{swarm_name}/tasks/{task_id}/unlink")
async def unlink_task(swarm_name: str, task_id: str, request: Request):
    store = _store(request)
    request_data = await parse_json_body(request)
    to_task_id = request_data.get("to_task_id")
    if not to_task_id:
        raise ApiError("Request body must include 'to_task_id'.")
    try:
        store.unlink_tasks(swarm_name, task_id, to_task_id)
    except (KeyError, ValueError) as exc:
        raise ApiError(str(exc)) from exc
    return {"success": True, "from_task_id": task_id, "to_task_id": to_task_id}
