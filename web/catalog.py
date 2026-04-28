"""Catalog 聚合导出层。

将 catalog_parts 子包中按领域拆分的构建函数统一提升到 web.catalog
命名空间，供路由层直接引用，实现 catalog 相关接口的数据组装。
"""
from __future__ import annotations

from .catalog_parts import (
    build_agent_catalog,
    build_event_catalog,
    build_log_catalog,
    build_metrics_catalog,
    build_swarm_stats,
    build_task_catalog,
    build_tool_catalog,
)

__all__ = [
    "build_agent_catalog",
    "build_event_catalog",
    "build_log_catalog",
    "build_metrics_catalog",
    "build_swarm_stats",
    "build_task_catalog",
    "build_tool_catalog",
]
