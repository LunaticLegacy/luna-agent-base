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
