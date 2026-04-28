"""FastAPI 依赖函数与请求解析工具。

该模块提供路由层常用的依赖注入函数（如获取运行时注册表、内容存储）
以及请求体/查询参数的解析辅助函数。
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import Request

from web.errors import ApiError


def get_runtime_registry(request: Request):
    """从应用状态中提取运行时注册表。

    Args:
        request: 当前 HTTP 请求对象。

    Returns:
        RuntimeRegistry 实例。

    Raises:
        ApiError: 注册表尚未初始化时抛出。
    """
    registry = getattr(request.app.state, "angelus_runtime", None)
    if registry is None:
        raise ApiError("Runtime registry is not initialized.")
    return registry


def get_content_store(request: Request):
    """从应用状态中提取内容存储。

    Args:
        request: 当前 HTTP 请求对象。

    Returns:
        ContentStore 实例。

    Raises:
        ApiError: 内容存储尚未初始化时抛出。
    """
    store = getattr(request.app.state, "angelus_content", None)
    if store is None:
        raise ApiError("Content store is not initialized.")
    return store


def parse_int(raw: Any, default: int) -> int:
    """将任意值安全地转换为整数。

    Args:
        raw: 待转换的原始值。
        default: 转换失败时的默认值。

    Returns:
        转换后的整数，或 default。
    """
    try:
        return int(raw)
    except Exception:
        # 兼容字符串、None 及不合法类型，静默回退到默认值
        return default


def parse_bool(raw: Any, default: bool = False) -> bool:
    """将任意值安全地转换为布尔值。

    支持 Python 原生 bool、数字以及常见的字符串表示
    （true/yes/on/1 等）。

    Args:
        raw: 待转换的原始值。
        default: 转换失败或无法识别时的默认值。

    Returns:
        解析后的布尔值。
    """
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
    """读取并解析请求体为 JSON 对象。

    Args:
        request: 当前 HTTP 请求对象。

    Returns:
        解析后的字典；若请求体为空则返回空字典。

    Raises:
        ApiError: 请求体不是合法 JSON，或解析结果不是 JSON 对象时抛出。
    """
    body = await request.body()
    if not body:
        # 空体视为空对象，减少调用方重复判断
        return {}
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ApiError("Request body must be valid JSON.") from exc
    if not isinstance(payload, dict):
        raise ApiError("Request body must be a JSON object.")
    return payload
