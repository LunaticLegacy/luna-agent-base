from __future__ import annotations

import json
from typing import Any

from fastapi import Request

from web.errors import ApiError


def get_runtime_registry(request: Request):
    registry = getattr(request.app.state, "angelus_runtime", None)
    if registry is None:
        raise ApiError("Runtime registry is not initialized.")
    return registry


def get_content_store(request: Request):
    store = getattr(request.app.state, "angelus_content", None)
    if store is None:
        raise ApiError("Content store is not initialized.")
    return store


def get_task_store(request: Request):
    store = getattr(request.app.state, "angelus_tasks", None)
    if store is None:
        raise ApiError("Task store is not initialized.")
    return store


def parse_int(raw: Any, default: int) -> int:
    try:
        return int(raw)
    except Exception:
        return default


def parse_bool(raw: Any, default: bool = False) -> bool:
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


async def parse_json_body(request: Request) -> dict[str, Any]:
    body = await request.body()
    if not body:
        return {}
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ApiError("Request body must be valid JSON.") from exc
    if not isinstance(payload, dict):
        raise ApiError("Request body must be a JSON object.")
    return payload
