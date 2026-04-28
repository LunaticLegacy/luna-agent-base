"""健康检查与就绪探针路由。

提供 Kubernetes 或负载均衡器常用的 liveness（health）与
readiness（ready）端点，以及运行时状态概览接口。
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/runtime/health")
async def health():
    """返回服务存活状态。

    Returns:
        固定返回 success=True 与 status=ok，表示进程仍在运行。
    """
    return {"success": True, "status": "ok"}


@router.get("/runtime/ready")
async def ready(request: Request):
    """返回服务就绪状态，包含多层校验。

    依次检查：
    1. 运行时注册表是否存在。
    2. 配置加载阶段是否出错。
    3. 是否有已加载的 swarm。
    4. 各 swarm 的执行图是否通过有效性校验。

    Args:
        request: FastAPI 请求对象。

    Returns:
        就绪时返回 success=True；任一检查失败返回 503 并附带原因。
    """
    registry = getattr(request.app.state, "angelus_runtime", None)
    if registry is None:
        return JSONResponse(
            {"success": False, "ready": False, "reason": "runtime registry missing"},
            status_code=503,
        )

    load_error = registry.load_error
    if load_error:
        # 配置加载失败时认为未就绪，避免将异常流量导入不完整的运行时
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
    """返回运行时当前状态摘要。

    Args:
        request: FastAPI 请求对象。

    Returns:
        包含服务状态、swarm 数量、活跃运行数及加载错误信息。
    """
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
