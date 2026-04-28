"""API 安全中间件：CORS 与可选的 Token 认证。

通过 FastAPI 的 http 中间件为所有请求附加 CORS 响应头，并对
高危写操作端点（POST/PUT/PATCH/DELETE）实施基于 Token 的认证。
"""
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
    """注册 HTTP 中间件，统一处理 CORS 与 Token 认证。

    认证仅针对 /api/ 前缀的写请求生效；OPTIONS 预检请求直接返回 204。

    Args:
        app: 当前 FastAPI 应用实例。
    """

    @app.middleware("http")
    async def enforce_api_security(request: Request, call_next):
        # 非预检请求且属于高危操作时才校验 Token
        if request.method != "OPTIONS" and _is_high_risk_request(request):
            api_config = _api_config(app)
            token = _configured_token(api_config)
            auth_enabled = bool(api_config.require_auth or token)
            if auth_enabled:
                if not token:
                    # 安全策略要求认证却未配置 Token，返回 503 提示管理员
                    response: Response = JSONResponse(
                        {"success": False, "error": "API authentication is enabled but no token is configured."},
                        status_code=503,
                    )
                    return _with_cors_headers(request, response, api_config)
                if not _request_token_matches(request, token):
                    response = JSONResponse({"success": False, "error": "Unauthorized."}, status_code=401)
                    return _with_cors_headers(request, response, api_config)

        # OPTIONS 预检直接返回 204，其余请求正常进入后续路由
        response = Response(status_code=204) if request.method == "OPTIONS" else await call_next(request)
        return _with_cors_headers(request, response, _api_config(app))


def _api_config(app: FastAPI) -> ApiConfig:
    """从应用状态中读取当前 API 配置，若不存在则返回默认值。

    Args:
        app: FastAPI 应用实例。

    Returns:
        ApiConfig 实例。
    """
    registry = getattr(app.state, "angelus_runtime", None)
    root_config = getattr(registry, "root_config", None)
    api_config = getattr(root_config, "api", None)
    if isinstance(api_config, ApiConfig):
        return api_config
    # 运行时注册表未就绪时回退到空配置，避免中间件初始化阶段报错
    return ApiConfig()


def _is_high_risk_request(request: Request) -> bool:
    """判断请求是否为需要认证的高危操作。

    Args:
        request: FastAPI 请求对象。

    Returns:
        True 表示该请求需进行 Token 校验。
    """
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return False
    return request.url.path.startswith("/api/")


def _configured_token(api_config: ApiConfig) -> str | None:
    """获取实际生效的 API Token，优先级：环境变量 > 配置文件。

    Args:
        api_config: API 配置对象。

    Returns:
        非空 Token 字符串，或 None。
    """
    env_name = (api_config.api_token_env or "ANGELUS_API_TOKEN").strip()
    env_token = os.environ.get(env_name, "").strip() if env_name else ""
    config_token = (api_config.api_token or "").strip()
    return env_token or config_token or None


def _request_token_matches(request: Request, expected_token: str) -> bool:
    """使用 HMAC 比较请求中的 Token 是否与期望值一致，防止时序攻击。

    Args:
        request: FastAPI 请求对象。
        expected_token: 配置侧期望的 Token。

    Returns:
        True 表示 Token 匹配。
    """
    supplied = _extract_request_token(request)
    return bool(supplied and hmac.compare_digest(supplied, expected_token))


def _extract_request_token(request: Request) -> str | None:
    """从 Authorization 头或自定义 X-Angelus-Token 头中提取 Token。

    Args:
        request: FastAPI 请求对象。

    Returns:
        提取到的 Token 字符串，或 None。
    """
    header = request.headers.get("Authorization", "").strip()
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    explicit = request.headers.get("X-Angelus-Token", "").strip()
    return explicit or None


def _with_cors_headers(request: Request, response: Response, api_config: ApiConfig) -> Response:
    """为响应附加 CORS 相关头部。

    根据配置中的 allowed_origins 决定是否设置 Access-Control-Allow-Origin。

    Args:
        request: 当前请求对象，用于读取 Origin 头。
        response: 待返回的响应对象。
        api_config: API 配置对象。

    Returns:
        附加 CORS 头后的响应对象。
    """
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
    """判断请求 Origin 是否在允许列表中，支持通配符 ``*``。

    Args:
        origin: 请求携带的 Origin 头值。
        allowed_origins: 配置中允许的源列表。

    Returns:
        允许的 Origin 字符串，或 None（不应设置 CORS 头）。
    """
    if not origin:
        return None
    normalized = {item.strip() for item in allowed_origins if item and item.strip()}
    if "*" in normalized:
        return origin
    return origin if origin in normalized else None
