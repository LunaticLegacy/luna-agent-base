from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from web.deps import get_runtime_registry, parse_json_body
from web.errors import NotFoundError, ConflictError
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


@router.post("/{run_id}/stop")
async def stop_run(run_id: str, request: Request):
    """Request a soft or hard stop for an active run.

    Body: {"stop_type": "soft" | "hard"}  (default: soft)
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
    record = _runs_registry(request).get_run(run_id)
    if record is None:
        raise NotFoundError(f"Unknown run: {run_id}")

    return StreamingResponse(
        stream_run_events(record),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
