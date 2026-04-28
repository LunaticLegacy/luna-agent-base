"""DatabaseManager 与 DBTimeoutError 的懒加载入口。

本模块通过 ``__getattr__`` 实现按需导入，避免在顶层直接加载
``database_manager`` 子模块，从而缩短首次导入耗时并降低循环导入风险。

导出内容：
    - :class:`DatabaseManager`: 异步 PostgreSQL 连接池管理器。
    - :class:`DBTimeoutError`: 数据库超时异常。
"""

from __future__ import annotations

__all__ = ["DatabaseManager", "DBTimeoutError"]


def __getattr__(name: str):
    if name in __all__:
        from .database_manager import DatabaseManager, DBTimeoutError

        return {"DatabaseManager": DatabaseManager, "DBTimeoutError": DBTimeoutError}[name]
    raise AttributeError(name)
