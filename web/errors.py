"""全局异常体系与 FastAPI 错误处理器注册。

定义了项目内部使用的 ApiError 层级，并将常见异常（包括 SwarmLoaderError、
KeyError、ValueError 等）统一映射为 JSON 响应，避免未处理异常直接暴露
堆栈信息。
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from fastapi.responses import JSONResponse

from core.swarm_spec import SwarmLoaderError


class ApiError(RuntimeError):
    """项目统一的 HTTP 友好型运行时异常基类。

    Attributes:
        status_code: 默认 HTTP 状态码，子类可覆盖。
    """

    status_code = 400

    def to_response(self) -> JSONResponse:
        """将异常实例序列化为标准 JSON 响应。

        Returns:
            包含 success=False 与错误描述的 JSONResponse。
        """
        return JSONResponse({"success": False, "error": str(self)}, status_code=self.status_code)


class NotFoundError(ApiError):
    """资源不存在异常，对应 HTTP 404。"""

    status_code = 404


class RunNotFoundError(NotFoundError):
    """指定运行记录无法找到时抛出。"""


class ConflictError(ApiError):
    """业务冲突异常，对应 HTTP 409。"""

    status_code = 409


def register_error_handlers(app: FastAPI) -> None:
    """向 FastAPI 应用注册全局异常处理器。

    所有处理器均以 JSON 形式返回错误信息，保持前后端响应格式一致。

    Args:
        app: 当前 FastAPI 应用实例。
    """

    @app.exception_handler(ApiError)
    async def handle_api_error(_request: Request, exc: ApiError):
        # 利用 ApiError 自身的序列化方法，确保状态码与消息一致
        return exc.to_response()

    @app.exception_handler(SwarmLoaderError)
    async def handle_swarm_loader_error(_request: Request, exc: SwarmLoaderError):
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)

    @app.exception_handler(KeyError)
    async def handle_key_error(_request: Request, exc: KeyError):
        # 将字典缺失键映射为 404，符合 REST 语义
        return JSONResponse({"success": False, "error": str(exc)}, status_code=404)

    @app.exception_handler(ValueError)
    async def handle_value_error(_request: Request, exc: ValueError):
        # 参数校验失败统一视为 400 Bad Request
        return JSONResponse({"success": False, "error": str(exc)}, status_code=400)

    @app.exception_handler(FastAPIHTTPException)
    async def handle_http_error(_request: Request, exc: FastAPIHTTPException):
        # 透传 FastAPI 原生 HTTPException 的状态码与详情
        return JSONResponse({"success": False, "error": str(exc.detail)}, status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_request: Request, exc: Exception):
        # 兜底处理器：防止未捕获异常泄露内部堆栈
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)
