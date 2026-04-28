"""运行时配置管理路由。

允许通过 HTTP 接口读取与修改 config.toml 中的 API 相关配置。
修改后会尝试热重载运行时注册表中的根配置，失败时不阻断服务。
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from core.swarm_spec import load_root_config
from web.deps import get_runtime_registry, parse_json_body
from web.settings_store import ApiSettings, load_api_settings, save_api_settings, serialize_api_settings

router = APIRouter()


def _get_config_path(request: Request):
    """提取当前运行时关联的配置文件路径及其注册表。

    Args:
        request: FastAPI 请求对象。

    Returns:
        (config_path, registry) 元组。
    """
    registry = get_runtime_registry(request)
    return registry.config_path, registry


@router.get("/settings")
async def get_settings(request: Request):
    """读取当前 API 设置。

    Args:
        request: FastAPI 请求对象。

    Returns:
        包含 success=True 与当前 settings 的字典。
    """
    config_path, _registry = _get_config_path(request)
    api_settings = load_api_settings(config_path)
    return {"success": True, "settings": {"api": serialize_api_settings(api_settings)}}


@router.put("/settings")
async def update_settings(request: Request):
    """更新 API 设置并持久化到 config.toml。

    保存成功后会尝试重新加载根配置；若加载失败则静默忽略，
    避免配置编辑成功后因解析异常导致服务不可用。

    Args:
        request: 请求体需包含 {"api": {...}} 结构。

    Returns:
        包含 success=True 与更新后 settings 的字典。
    """
    config_path, registry = _get_config_path(request)
    request_data = await parse_json_body(request)
    api_section = request_data.get("api")
    existing = load_api_settings(config_path)
    api_settings = ApiSettings.from_mapping(api_section, existing=existing)
    updated = save_api_settings(config_path, api_settings)
    try:
        # 热重载根配置，使新设置立即对安全中间件等生效
        registry.root_config = load_root_config(config_path)
        registry.load_error = None
    except Exception:
        # 文件已保存为唯一真相源；即使重载失败也保持运行时可操作
        pass
    return {"success": True, "settings": {"api": serialize_api_settings(updated.api)}}
