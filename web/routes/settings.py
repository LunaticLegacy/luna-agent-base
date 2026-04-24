from __future__ import annotations

from fastapi import APIRouter, Request

from core.swarm_spec import load_root_config
from web.deps import get_runtime_registry, parse_json_body
from web.settings_store import ApiSettings, load_api_settings, save_api_settings, serialize_api_settings

router = APIRouter()


def _get_config_path(request: Request):
    registry = get_runtime_registry(request)
    return registry.config_path, registry


@router.get("/settings")
async def get_settings(request: Request):
    config_path, _registry = _get_config_path(request)
    api_settings = load_api_settings(config_path)
    return {"success": True, "settings": {"api": serialize_api_settings(api_settings)}}


@router.put("/settings")
async def update_settings(request: Request):
    config_path, registry = _get_config_path(request)
    request_data = await parse_json_body(request)
    api_section = request_data.get("api")
    existing = load_api_settings(config_path)
    api_settings = ApiSettings.from_mapping(api_section, existing=existing)
    updated = save_api_settings(config_path, api_settings)
    try:
        registry.root_config = load_root_config(config_path)
        registry.load_error = None
    except Exception:
        # The file just saved is the source of truth; keep the runtime usable
        # even if reloading root config fails for an unexpected reason.
        pass
    return {"success": True, "settings": {"api": serialize_api_settings(updated.api)}}
