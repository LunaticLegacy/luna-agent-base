"""Catalog 构建子包，按领域拆分为独立的构建函数。

每个模块负责从运行时注册表中提取原始数据，并转换为前端可用的
目录/统计/可观测性结构。所有构建函数均为纯函数，不修改运行时状态。
"""
from .agents import build_agent_catalog
from .metrics import build_metrics_catalog
from .observability import build_event_catalog, build_log_catalog
from .swarm import build_swarm_stats
from .tasks import build_task_catalog
from .tools import build_tool_catalog

__all__ = [
    "build_agent_catalog",
    "build_event_catalog",
    "build_log_catalog",
    "build_metrics_catalog",
    "build_swarm_stats",
    "build_task_catalog",
    "build_tool_catalog",
]
