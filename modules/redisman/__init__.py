from __future__ import annotations

__all__ = ["RedisManager"]


def __getattr__(name: str):
    if name == "RedisManager":
        from .redis_cache import RedisManager

        return RedisManager
    raise AttributeError(name)
