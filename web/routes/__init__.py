"""路由子包，聚合所有 FastAPI APIRouter 实例。

每个子模块按业务域划分（health、catalog、content、settings、
swarms、runs），最终由 app_factory 统一挂载到 FastAPI 应用上。
"""
from .health import router as health_router
from .catalog import router as catalog_router
from .content import router as content_router
from .settings import router as settings_router
from .swarms import router as swarms_router
from .runs import router as runs_router

__all__ = [
    "health_router",
    "catalog_router",
    "content_router",
    "settings_router",
    "swarms_router",
    "runs_router",
]
