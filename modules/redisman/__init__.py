"""RedisManager 的懒加载入口。

本模块通过 ``__getattr__`` 实现按需导入，避免在顶层直接加载
``redis_cache`` 子模块，从而缩短导入时间并降低循环导入风险。

导出内容：
    - :class:`RedisManager`: 异步 Redis 连接池与数据操作管理器。
"""

from __future__ import annotations

__all__ = ["RedisManager"]


def __getattr__(name: str):
    if name == "RedisManager":
        from .redis_cache import RedisManager

        return RedisManager
    raise AttributeError(name)
