"""SSE 流生成器，将运行记录转换为 Server-Sent Events 文本流。

该模块仅暴露 stream_run_events，供路由层在 /api/runs/{run_id}/events
端点返回 StreamingResponse 时使用。
"""
from __future__ import annotations

import json
from typing import Iterator

from .record import RunRecord


def stream_run_events(record: RunRecord, *, after: int = 0) -> Iterator[str]:
    """为单条运行记录创建 SSE 文本流。

    先发送当前运行快照（run.snapshot），随后透传记录中已有的
    stream_events 生成器输出。

    Args:
        record: 要流式输出的运行记录。
        after: 仅发送该索引之后的事件（用于断线重连）。

    Yields:
        SSE 格式的字符串帧，例如 ``event: run.snapshot\ndata: {...}\n\n``。
    """
    # 发送初始快照，让客户端立即获得运行基本信息
    yield f"event: run.snapshot\n"
    yield f"data: {json.dumps(record.snapshot(), ensure_ascii=False)}\n\n"
    # 透传后续事件，利用 RunRecord 内部的 Condition 实现阻塞等待
    yield from record.stream_events(after=after)
