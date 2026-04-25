from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from web.deps import get_runtime_registry
from web.errors import NotFoundError
from web.runs import stream_run_events

router = APIRouter()


def _runs_registry(request: Request):
    return get_runtime_registry(request).runs


@router.get("/{run_id}")
async def get_run(run_id: str, request: Request):
    record = _runs_registry(request).get_run(run_id)
    if record is None:
        raise NotFoundError(f"Unknown run: {run_id}")
    return {"success": True, "run": record.snapshot()}


@router.get("/{run_id}/events")
async def stream_run(run_id: str, request: Request):
    record = _runs_registry(request).get_run(run_id)
    if record is None:
        raise NotFoundError(f"Unknown run: {run_id}")

    return StreamingResponse(
        stream_run_events(record),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
