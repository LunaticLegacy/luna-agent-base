from __future__ import annotations

import hmac
import os
from typing import Iterable

from flask import Flask, jsonify, request

from core.swarm_spec import ApiConfig


DEFAULT_CORS_ORIGINS = [
    "http://localhost:4200",
    "http://127.0.0.1:4200",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


def install_api_security(app: Flask) -> None:
    """Install CORS and optional token auth for high-risk API routes."""

    @app.before_request
    def enforce_api_token():
        if request.method == "OPTIONS":
            return None
        if not _is_high_risk_request():
            return None

        api_config = _api_config(app)
        token = _configured_token(api_config)
        auth_enabled = bool(api_config.require_auth or token)
        if not auth_enabled:
            return None
        if not token:
            return jsonify({"success": False, "error": "API authentication is enabled but no token is configured."}), 503
        if _request_token_matches(token):
            return None
        return jsonify({"success": False, "error": "Unauthorized."}), 401

    @app.after_request
    def add_cors_headers(response):
        api_config = _api_config(app)
        allowed_origins = list(api_config.cors_allowed_origins or DEFAULT_CORS_ORIGINS)
        origin = request.headers.get("Origin")
        allowed_origin = _allowed_cors_origin(origin, allowed_origins)
        if allowed_origin is not None:
            response.headers["Access-Control-Allow-Origin"] = allowed_origin
            response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Angelus-Token"
        return response


def _api_config(app: Flask) -> ApiConfig:
    registry = app.extensions.get("angelus_runtime")
    root_config = getattr(registry, "root_config", None)
    api_config = getattr(root_config, "api", None)
    if isinstance(api_config, ApiConfig):
        return api_config
    return ApiConfig()


def _is_high_risk_request() -> bool:
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return False
    return request.path.startswith("/api/")


def _configured_token(api_config: ApiConfig) -> str | None:
    env_name = (api_config.api_token_env or "ANGELUS_API_TOKEN").strip()
    env_token = os.environ.get(env_name, "").strip() if env_name else ""
    config_token = (api_config.api_token or "").strip()
    return env_token or config_token or None


def _request_token_matches(expected_token: str) -> bool:
    supplied = _extract_request_token()
    return bool(supplied and hmac.compare_digest(supplied, expected_token))


def _extract_request_token() -> str | None:
    header = request.headers.get("Authorization", "").strip()
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    explicit = request.headers.get("X-Angelus-Token", "").strip()
    return explicit or None


def _allowed_cors_origin(origin: str | None, allowed_origins: Iterable[str]) -> str | None:
    if not origin:
        return None
    normalized = {item.strip() for item in allowed_origins if item and item.strip()}
    if "*" in normalized:
        return origin
    return origin if origin in normalized else None
