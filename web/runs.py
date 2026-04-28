"""Runs 模块的聚合导出层。

将 runstore 子包中的核心类与函数提升到 web.runs 命名空间，
方便路由层统一引用，减少导入路径深度。
"""
from __future__ import annotations

from .runstore import (
    RunRecord,
    RunRegistry,
    serialize_edge,
    serialize_graph_snapshot,
    serialize_node,
    serialize_swarm_detail,
    serialize_swarm_summary,
    stream_run_events,
)

__all__ = [
    "RunRecord",
    "RunRegistry",
    "serialize_edge",
    "serialize_graph_snapshot",
    "serialize_node",
    "serialize_swarm_detail",
    "serialize_swarm_summary",
    "stream_run_events",
]
