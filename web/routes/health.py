from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/runtime/health")
async def health():
    return {"success": True, "status": "ok"}


@router.get("/runtime/ready")
async def ready(request: Request):
    registry = getattr(request.app.state, "angelus_runtime", None)
    if registry is None:
        return JSONResponse(
            {"success": False, "ready": False, "reason": "runtime registry missing"},
            status_code=503,
        )

    load_error = registry.load_error
    if load_error:
        return JSONResponse(
            {
                "success": False,
                "ready": False,
                "reason": "swarm load error",
                "load_error": load_error,
            },
            status_code=503,
        )

    swarms = registry.swarms
    if not swarms:
        return JSONResponse({"success": False, "ready": False, "reason": "no swarms loaded"}, status_code=503)

    invalid = []
    for swarm_name, swarm in swarms.items():
        validation = swarm.core.check_execution_graph_available()
        if not validation.is_valid:
            invalid.append({"swarm": swarm_name, "errors": validation.errors})

    if invalid:
        return JSONResponse({"success": False, "ready": False, "invalid_swarms": invalid}, status_code=503)

    return {"success": True, "ready": True, "swarm_count": len(swarms)}


@router.get("/runtime/status")
async def runtime_status(request: Request):
    registry = getattr(request.app.state, "angelus_runtime", None)
    if registry is None:
        return JSONResponse(
            {"success": False, "status": "unavailable", "reason": "runtime registry missing"},
            status_code=503,
        )
    return {
        "success": True,
        "status": "ok" if not registry.load_error else "degraded",
        "service": "angelus",
        "swarm_count": len(registry.swarms),
        "active_run_count": registry.runs.active_run_count(),
        "load_error": registry.load_error,
    }
