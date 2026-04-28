"""Angelus 核心模块聚合包。

本模块统一导出与外部交互频率最高的基础设施组件，
包括 LLM 请求路由、数据库连接池以及 Redis 缓存管理器。
对于可选依赖（database / redis），采用 try/except 懒加载策略，
确保在缺少对应驱动时包体仍可被正常导入，提升部署灵活性。

导出内容：
    - :class:`LLMFetcher`: 多后端 LLM 请求路由与 fallback 管理器。
    - :class:`LLMContext`: 单条对话消息上下文。
    - :class:`LLMBackendConfig`: 单个 LLM 后端配置。
    - :class:`LLMError`: LLM 模块基础异常。
    - :class:`LLMTimeoutError`: 后端超时异常。
    - :class:`LLMBackendError`: 所有后端均失败时抛出的异常。
    - :class:`DatabaseManager` (可选): 异步数据库连接池。
    - :class:`DBTimeoutError` (可选): 数据库超时异常。
    - :class:`RedisManager` (可选): Redis 缓存管理器。
"""

from __future__ import annotations

from .llm_fetcher import (
    LLMBackendConfig,
    LLMBackendError,
    LLMContext,
    LLMError,
    LLMFetcher,
    LLMTimeoutError,
)

__all__ = [
    "LLMFetcher",
    "LLMContext",
    "LLMBackendConfig",
    "LLMError",
    "LLMTimeoutError",
    "LLMBackendError",
]

try:  # Optional runtime dependencies; keep module importable when absent.
    from .databaseman import DatabaseManager, DBTimeoutError
except Exception:  # pragma: no cover - optional dependency path
    DatabaseManager = None
    DBTimeoutError = None
else:
    __all__.extend(["DatabaseManager", "DBTimeoutError"])

try:  # Optional runtime dependencies; keep module importable when absent.
    from .redisman import RedisManager
except Exception:  # pragma: no cover - optional dependency path
    RedisManager = None
else:
    __all__.append("RedisManager")
