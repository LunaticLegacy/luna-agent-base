from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from core.swarm_loader import SwarmLoaderError
from web.content_store import ContentStore
from web.runtime import RuntimeRegistry
from web.task_store import TaskStore
from web.routes.swarms import router as swarms_router
from web.routes.swarms import _serialize_swarm_with_runtime

from .errors import register_error_handlers
from .routes import catalog_router, content_router, health_router, settings_router, tasks_router
from .security import install_api_security


def create_app(config_path: str | Path = "config.toml") -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="angelus")
    config_path = Path(config_path)

    try:
        runtime_registry = RuntimeRegistry.from_config_path(config_path)
    except SwarmLoaderError as exc:
        runtime_registry = RuntimeRegistry(
            config_path=config_path,
            root_config=None,
            load_error=str(exc),
        )

    app.state.angelus_runtime = runtime_registry
    install_api_security(app)
    app.state.angelus_content = ContentStore.from_runtime_registry(
        data_dir=config_path.parent / "data",
        runtime_registry=runtime_registry,
    )
    app.state.angelus_tasks = TaskStore.from_runtime_registry(
        data_dir=config_path.parent / "data",
        runtime_registry=runtime_registry,
    )

    register_error_handlers(app)
    app.include_router(health_router, prefix="/api")
    app.include_router(catalog_router, prefix="/api")
    app.include_router(content_router, prefix="/api")
    app.include_router(settings_router, prefix="/api")
    app.include_router(tasks_router, prefix="/api")
    app.include_router(swarms_router, prefix="/api/swarms")

    @app.get("/api/swarms")
    async def api_swarms():
        return {
            "success": True,
            "swarms": [
                _serialize_swarm_with_runtime(app.state.angelus_runtime, swarm)
                for swarm in app.state.angelus_runtime.swarms.values()
            ],
        }

    @app.get("/")
    async def index():
        return {
            "success": True,
            "service": "angelus",
            "swarm_count": len(app.state.angelus_runtime.swarms),
            "load_error": app.state.angelus_runtime.load_error,
        }

    @app.get("/api")
    async def api_index():
        return {
            "success": True,
            "service": "angelus",
            "swarm_count": len(app.state.angelus_runtime.swarms),
            "load_error": app.state.angelus_runtime.load_error,
            "api_root": "/api",
        }

    return app
