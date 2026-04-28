"""FastAPI 应用工厂模块。

负责根据配置路径创建并组装 Angelus 的 FastAPI 应用实例，包括：
- 初始化运行时注册表（RuntimeRegistry）与内容存储（ContentStore）。
- 安装安全中间件（CORS / Token Auth）。
- 注册全局错误处理器。
- 挂载各业务域路由。
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from core.swarm_loader import SwarmLoaderError
from web.content_store import ContentStore
from web.runtime import RuntimeRegistry

from .errors import register_error_handlers
from .routes import catalog_router, content_router, health_router, runs_router, settings_router, swarms_router


def create_app(config_path: str | Path = "config.toml") -> FastAPI:
    """创建并配置 Angelus FastAPI 应用。

    若配置加载失败，仍会返回一个可启动的应用实例，但运行时注册表会
    携带 load_error 信息，方便 health/ready 接口暴露加载状态。

    Args:
        config_path: 根配置文件路径，默认当前目录下的 ``config.toml``。

    Returns:
        配置完成的 FastAPI 应用实例。
    """
    app = FastAPI(title="angelus")
    config_path = Path(config_path)

    try:
        # 正常路径：从配置文件中加载所有 swarm 并构建运行时注册表
        runtime_registry = RuntimeRegistry.from_config_path(config_path)
    except SwarmLoaderError as exc:
        # 降级路径：配置解析失败时仍返回可启动应用，避免进程直接崩溃
        runtime_registry = RuntimeRegistry(
            config_path=config_path,
            root_config=None,
            load_error=str(exc),
        )

    # 将运行时注册表挂载到应用状态，供依赖注入函数后续提取
    app.state.angelus_runtime = runtime_registry
    install_api_security(app)
    # 基于运行时注册表初始化持久化内容存储（knowledge / memory）
    app.state.angelus_content = ContentStore.from_runtime_registry(
        data_dir=config_path.parent / "data",
        runtime_registry=runtime_registry,
    )
    register_error_handlers(app)
    # 按业务域挂载路由，swarms 与 runs 使用独立前缀以支持更细粒度的 URL 规划
    app.include_router(health_router, prefix="/api")
    app.include_router(catalog_router, prefix="/api")
    app.include_router(content_router, prefix="/api")
    app.include_router(settings_router, prefix="/api")
    app.include_router(swarms_router, prefix="/api/swarms")
    app.include_router(runs_router, prefix="/api/runs")

    @app.get("/")
    async def index():
        """返回服务根路径的基础状态信息。"""
        return {
            "success": True,
            "service": "angelus",
            "swarm_count": len(app.state.angelus_runtime.swarms),
            "load_error": app.state.angelus_runtime.load_error,
        }

    @app.get("/api")
    async def api_index():
        """返回 API 根路径的状态信息，包含版本标识。"""
        return {
            "success": True,
            "service": "angelus",
            "swarm_count": len(app.state.angelus_runtime.swarms),
            "load_error": app.state.angelus_runtime.load_error,
            "api_root": "/api",
            "api_version": "v2",
        }

    return app
