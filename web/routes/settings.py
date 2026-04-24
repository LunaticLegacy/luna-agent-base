from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from web.errors import ApiError
from web.settings_store import ApiSettings, load_api_settings, save_api_settings, serialize_api_settings
from core.swarm_spec import load_root_config

settings_bp = Blueprint("settings", __name__)


def _get_runtime_registry():
    registry = current_app.extensions.get("angelus_runtime")
    if registry is None:
        raise ApiError("Runtime registry is not initialized.")
    return registry


def _get_config_path():
    registry = _get_runtime_registry()
    return registry.config_path, registry


@settings_bp.get("/settings")
def get_settings():
    config_path, _registry = _get_config_path()
    api_settings = load_api_settings(config_path)
    return jsonify({"success": True, "settings": {"api": serialize_api_settings(api_settings)}})


@settings_bp.put("/settings")
def update_settings():
    config_path, registry = _get_config_path()
    request_data = request.get_json(silent=True) or {}
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
    return jsonify({"success": True, "settings": {"api": serialize_api_settings(updated.api)}})
