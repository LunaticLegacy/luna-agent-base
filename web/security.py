from __future__ import annotations

import hmac
import os
from typing import Iterable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from core.swarm_spec import ApiConfig


DEFAULT_CORS_ORIGINS = [
    "http://localhost:4200",
    "http://127.0.0.1:4200",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


def install_api_security(app: FastAPI) -> None:
    """Install CORS and optional token auth for high-risk API routes."""

    @app.middleware("http")
    async def enforce_api_security(request: Request, call_next):
        if request.method != "OPTIONS" and _is_high_risk_request(request):
            api_config = _api_config(app)
            token = _configured_token(api_config)
            auth_enabled = bool(api_config.require_auth or token)
            if auth_enabled:
                if not token:
                    response: Response = JSONResponse(
                        {"success": False, "error": "API authentication is enabled but no token is configured."},
                        status_code=503,
                    )
                    return _with_cors_headers(request, response, api_config)
                if not _request_token_matches(request, token):
                    response = JSONResponse({"success": False, "error": "Unauthorized."}, status_code=401)
                    return _with_cors_headers(request, response, api_config)

        response = Response(status_code=204) if request.method == "OPTIONS" else await call_next(request)
        return _with_cors_headers(request, response, _api_config(app))


def _api_config(app: FastAPI) -> ApiConfig:
    registry = getattr(app.state, "angelus_runtime", None)
    root_config = getattr(registry, "root_config", None)
    api_config = getattr(root_config, "api", None)
    if isinstance(api_config, ApiConfig):
        return api_config
    return ApiConfig()


def _is_high_risk_request(request: Request) -> bool:
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return False
    return request.url.path.startswith("/api/")


def _configured_token(api_config: ApiConfig) -> str | None:
    env_name = (api_config.api_token_env or "ANGELUS_API_TOKEN").strip()
    env_token = os.environ.get(env_name, "").strip() if env_name else ""
    config_token = (api_config.api_token or "").strip()
    return env_token or config_token or None


def _request_token_matches(request: Request, expected_token: str) -> bool:
    supplied = _extract_request_token(request)
    return bool(supplied and hmac.compare_digest(supplied, expected_token))


def _extract_request_token(request: Request) -> str | None:
    header = request.headers.get("Authorization", "").strip()
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    explicit = request.headers.get("X-Angelus-Token", "").strip()
    return explicit or None


def _with_cors_headers(request: Request, response: Response, api_config: ApiConfig) -> Response:
    allowed_origins = list(api_config.cors_allowed_origins or DEFAULT_CORS_ORIGINS)
    origin = request.headers.get("Origin")
    allowed_origin = _allowed_cors_origin(origin, allowed_origins)
    if allowed_origin is not None:
        response.headers["Access-Control-Allow-Origin"] = allowed_origin
        response.headers["Vary"] = "Origin"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Angelus-Token"
    return response


def _allowed_cors_origin(origin: str | None, allowed_origins: Iterable[str]) -> str | None:
    if not origin:
        return None
    normalized = {item.strip() for item in allowed_origins if item and item.strip()}
    if "*" in normalized:
        return origin
    return origin if origin in normalized else None
