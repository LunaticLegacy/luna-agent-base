from .health import router as health_router
from .catalog import router as catalog_router
from .content import router as content_router
from .settings import router as settings_router
from .swarms import router as swarms_router
from .tasks import router as tasks_router

__all__ = [
    "health_router",
    "catalog_router",
    "content_router",
    "settings_router",
    "swarms_router",
    "tasks_router",
]
