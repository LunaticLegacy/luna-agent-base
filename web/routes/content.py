from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from web.errors import ApiError

content_bp = Blueprint("content", __name__)


def _get_content_store():
    store = current_app.extensions.get("angelus_content")
    if store is None:
        raise ApiError("Content store is not initialized.")
    return store


def _parse_int(raw, default: int) -> int:
    try:
        return int(raw)
    except Exception:
        return default


@content_bp.get("/knowledge")
def list_knowledge():
    store = _get_content_store()
    payload = store.list_knowledge(
        type_filter=request.args.get("type"),
        source=request.args.get("source"),
        tag=request.args.get("tag"),
        q=request.args.get("q"),
        page=_parse_int(request.args.get("page", 1), 1),
        limit=_parse_int(request.args.get("limit", 20), 20),
    )
    return jsonify({"success": True, **payload})


@content_bp.get("/knowledge/<string:knowledge_id>")
def get_knowledge(knowledge_id: str):
    store = _get_content_store()
    return jsonify({"success": True, "knowledge": store.get_knowledge(knowledge_id)})


@content_bp.post("/knowledge")
def create_knowledge():
    store = _get_content_store()
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        raise ApiError("Request body must be a JSON object.")
    item = store.create_knowledge(payload)
    return jsonify({"success": True, "knowledge": item}), 201


@content_bp.put("/knowledge/<string:knowledge_id>")
def update_knowledge(knowledge_id: str):
    store = _get_content_store()
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        raise ApiError("Request body must be a JSON object.")
    item = store.update_knowledge(knowledge_id, payload)
    return jsonify({"success": True, "knowledge": item})


@content_bp.delete("/knowledge/<string:knowledge_id>")
def delete_knowledge(knowledge_id: str):
    store = _get_content_store()
    item = store.delete_knowledge(knowledge_id)
    return jsonify({"success": True, "knowledge": item})


@content_bp.get("/memory")
def list_memory():
    store = _get_content_store()
    payload = store.list_memory(
        type_filter=request.args.get("type"),
        source=request.args.get("source"),
        q=request.args.get("q"),
        page=_parse_int(request.args.get("page", 1), 1),
        limit=_parse_int(request.args.get("limit", 20), 20),
    )
    return jsonify({"success": True, **payload})


@content_bp.get("/memory/<string:memory_id>")
def get_memory(memory_id: str):
    store = _get_content_store()
    return jsonify({"success": True, "memory": store.get_memory(memory_id)})


@content_bp.post("/memory")
def create_memory():
    store = _get_content_store()
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        raise ApiError("Request body must be a JSON object.")
    item = store.create_memory(payload)
    return jsonify({"success": True, "memory": item}), 201


@content_bp.delete("/memory/<string:memory_id>")
def delete_memory(memory_id: str):
    store = _get_content_store()
    item = store.delete_memory(memory_id)
    return jsonify({"success": True, "memory": item})
