from __future__ import annotations

__all__ = ["DatabaseManager", "DBTimeoutError"]


def __getattr__(name: str):
    if name in __all__:
        from .database_manager import DatabaseManager, DBTimeoutError

        return {"DatabaseManager": DatabaseManager, "DBTimeoutError": DBTimeoutError}[name]
    raise AttributeError(name)
