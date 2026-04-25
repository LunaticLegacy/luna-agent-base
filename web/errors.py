from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from fastapi.responses import JSONResponse

from core.swarm_spec import SwarmLoaderError


class ApiError(RuntimeError):
    """Base HTTP-friendly runtime error."""

    status_code = 400

    def to_response(self) -> JSONResponse:
        return JSONResponse({"success": False, "error": str(self)}, status_code=self.status_code)


class NotFoundError(ApiError):
    status_code = 404


class RunNotFoundError(NotFoundError):
    """Raised when a requested live run cannot be found."""


class ConflictError(ApiError):
    status_code = 409


def register_error_handlers(app: FastAPI) -> None:
    """Register FastAPI error handlers for runtime exceptions."""

    @app.exception_handler(ApiError)
    async def handle_api_error(_request: Request, exc: ApiError):
        return exc.to_response()

    @app.exception_handler(SwarmLoaderError)
    async def handle_swarm_loader_error(_request: Request, exc: SwarmLoaderError):
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)

    @app.exception_handler(KeyError)
    async def handle_key_error(_request: Request, exc: KeyError):
        return JSONResponse({"success": False, "error": str(exc)}, status_code=404)

    @app.exception_handler(ValueError)
    async def handle_value_error(_request: Request, exc: ValueError):
        return JSONResponse({"success": False, "error": str(exc)}, status_code=400)

    @app.exception_handler(FastAPIHTTPException)
    async def handle_http_error(_request: Request, exc: FastAPIHTTPException):
        return JSONResponse({"success": False, "error": str(exc.detail)}, status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_request: Request, exc: Exception):
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)
