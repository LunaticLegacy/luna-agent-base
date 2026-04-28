"""运行记录管理路由。

提供单条运行的状态查询、停止控制以及事件流（SSE）输出。
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from web.deps import get_runtime_registry, parse_json_body
from web.errors import NotFoundError, ConflictError
from web.runs import stream_run_events

router = APIRouter()


def _runs_registry(request: Request):
    """从请求中提取运行注册表（RunRegistry）的快捷函数。

    Args:
        request: FastAPI 请求对象。

    Returns:
        RunRegistry 实例。
    """
    return get_runtime_registry(request).runs


@router.get("/{run_id}")
async def get_run(run_id: str, request: Request):
    """获取单条运行的当前快照。

    Args:
        run_id: 运行唯一标识。
        request: FastAPI 请求对象。

    Returns:
        包含 success=True 与运行快照。

    Raises:
        NotFoundError: 运行不存在时抛出。
    """
    record = _runs_registry(request).get_run(run_id)
    if record is None:
        raise NotFoundError(f"Unknown run: {run_id}")
    return {"success": True, "run": record.snapshot()}


@router.post("/{run_id}/stop")
async def stop_run(run_id: str, request: Request):
    """请求停止一条活跃的运行（软停止或硬停止）。

    请求体示例：``{"stop_type": "soft"}``

    Args:
        run_id: 要停止的运行 ID。
        request: FastAPI 请求对象。

    Returns:
        包含 success=True、stop_type 与停止后状态。

    Raises:
        NotFoundError: 运行不存在。
        ConflictError: 运行已结束，或 stop_type 不合法，或停止操作未生效。
    """
    registry = _runs_registry(request)
    record = registry.get_run(run_id)
    if record is None:
        raise NotFoundError(f"Unknown run: {run_id}")
    if record._done:
        raise ConflictError(f"Run {run_id} is already finished.")

    body = await parse_json_body(request)
    stop_type = str(body.get("stop_type", "soft")).strip().lower()
    if stop_type not in {"soft", "hard"}:
        raise ConflictError(f"Invalid stop_type: '{stop_type}'. Use 'soft' or 'hard'.")

    stopped = registry.stop_run(run_id, stop_type=stop_type)
    if stopped is None:
        raise ConflictError(f"Run {run_id} could not be stopped.")
    return {"success": True, "run_id": run_id, "stop_type": stop_type, "status": stopped.status}


@router.get("/{run_id}/events")
async def stream_run(run_id: str, request: Request):
    """以 SSE 流形式推送指定运行的事件。

    Args:
        run_id: 运行唯一标识。
        request: FastAPI 请求对象。

    Returns:
        StreamingResponse，媒体类型为 text/event-stream。

    Raises:
        NotFoundError: 运行不存在时抛出。
    """
    record = _runs_registry(request).get_run(run_id)
    if record is None:
        raise NotFoundError(f"Unknown run: {run_id}")

    # 禁用缓存与代理缓冲，确保 SSE 帧实时推送至客户端
    return StreamingResponse(
        stream_run_events(record),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
