"""Run store 子包，提供运行记录、注册表、序列化与流式输出能力。

导出内容：
    RunRecord: 单条运行记录的数据类。
    RunRegistry: 线程安全的运行注册表。
    serialize_edge / serialize_graph_snapshot / serialize_node:
        图结构与节点的序列化工具。
    serialize_swarm_detail / serialize_swarm_summary:
        Swarm 元信息的序列化工具。
    stream_run_events: 将运行事件转换为 SSE 流。
"""
from .record import RunRecord
from .registry import RunRegistry
from .serialization import (
    serialize_edge,
    serialize_graph_snapshot,
    serialize_node,
    serialize_swarm_detail,
    serialize_swarm_summary,
)
from .stream import stream_run_events

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
