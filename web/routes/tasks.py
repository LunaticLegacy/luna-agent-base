from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from web.errors import ApiError, NotFoundError
from web.task_store import TaskStore

tasks_bp = Blueprint("tasks", __name__)


def _get_task_store() -> TaskStore:
    store = current_app.extensions.get("angelus_tasks")
    if store is None:
        raise ApiError("Task store is not initialized.")
    return store


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


@tasks_bp.get("/tasks")
def list_tasks():
    store = _get_task_store()
    payload = store.list_tasks(
        swarm_name=request.args.get("swarm") or None,
        status=request.args.get("status") or None,
        agent_id=request.args.get("agent_id") or None,
        page=int(request.args.get("page", 1) or 1),
        limit=int(request.args.get("limit", 20) or 20),
    )
    payload["items"] = [_task_to_catalog_item(item) for item in payload["items"]]
    return jsonify({"success": True, **payload})


@tasks_bp.post("/tasks")
def create_task():
    store = _get_task_store()
    request_data = request.get_json(silent=True) or {}
    swarm_name = request_data.get("swarm")
    if not swarm_name:
        raise ApiError("Request body must include 'swarm' (swarm_name).")
    task = store.create_task(swarm_name, request_data)
    return jsonify({"success": True, "task": task.snapshot()}), 201


@tasks_bp.get("/tasks/<string:task_id>")
def get_task(task_id: str):
    store = _get_task_store()
    swarm_name = request.args.get("swarm")
    if not swarm_name:
        raise ApiError("Query parameter 'swarm' is required.")
    try:
        task = store.get_task(swarm_name, task_id)
    except KeyError as exc:
        raise NotFoundError(str(exc)) from exc
    return jsonify({"success": True, "task": task.snapshot()})


@tasks_bp.put("/tasks/<string:task_id>")
def update_task(task_id: str):
    store = _get_task_store()
    request_data = request.get_json(silent=True) or {}
    swarm_name = request_data.get("swarm") or request.args.get("swarm")
    if not swarm_name:
        raise ApiError("Request body or query parameter 'swarm' is required.")
    try:
        task = store.update_task(swarm_name, task_id, request_data)
    except KeyError as exc:
        raise NotFoundError(str(exc)) from exc
    return jsonify({"success": True, "task": task.snapshot()})


@tasks_bp.delete("/tasks/<string:task_id>")
def delete_task(task_id: str):
    store = _get_task_store()
    swarm_name = request.args.get("swarm")
    if not swarm_name:
        raise ApiError("Query parameter 'swarm' is required.")
    try:
        task = store.delete_task(swarm_name, task_id)
    except KeyError as exc:
        raise NotFoundError(str(exc)) from exc
    return jsonify({"success": True, "task": task.snapshot()})


@tasks_bp.post("/tasks/<string:task_id>/link")
def link_task(task_id: str):
    store = _get_task_store()
    request_data = request.get_json(silent=True) or {}
    swarm_name = request_data.get("swarm") or request.args.get("swarm")
    to_task_id = request_data.get("to_task_id")
    if not swarm_name:
        raise ApiError("Request body or query parameter 'swarm' is required.")
    if not to_task_id:
        raise ApiError("Request body must include 'to_task_id'.")
    try:
        store.link_tasks(swarm_name, task_id, to_task_id)
    except (KeyError, ValueError) as exc:
        raise ApiError(str(exc)) from exc
    return jsonify({"success": True, "from_task_id": task_id, "to_task_id": to_task_id})


@tasks_bp.post("/tasks/<string:task_id>/unlink")
def unlink_task(task_id: str):
    store = _get_task_store()
    request_data = request.get_json(silent=True) or {}
    swarm_name = request_data.get("swarm") or request.args.get("swarm")
    to_task_id = request_data.get("to_task_id")
    if not swarm_name:
        raise ApiError("Request body or query parameter 'swarm' is required.")
    if not to_task_id:
        raise ApiError("Request body must include 'to_task_id'.")
    try:
        store.unlink_tasks(swarm_name, task_id, to_task_id)
    except (KeyError, ValueError) as exc:
        raise ApiError(str(exc)) from exc
    return jsonify({"success": True, "from_task_id": task_id, "to_task_id": to_task_id})
