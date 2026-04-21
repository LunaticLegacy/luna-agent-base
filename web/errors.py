from __future__ import annotations

from typing import Any, Tuple

from flask import jsonify
from werkzeug.exceptions import HTTPException

from core.swarm_spec import SwarmLoaderError


class ApiError(RuntimeError):
    """Base HTTP-friendly runtime error."""

    status_code = 400

    def to_response(self) -> Tuple[Any, int]:
        return jsonify({"success": False, "error": str(self)}), self.status_code


class NotFoundError(ApiError):
    status_code = 404


class RunNotFoundError(NotFoundError):
    """Raised when a requested live run cannot be found."""


class ConflictError(ApiError):
    status_code = 409


def register_error_handlers(app) -> None:
    """Register Flask error handlers for runtime exceptions."""

    @app.errorhandler(ApiError)
    def handle_api_error(exc: ApiError):
        return exc.to_response()

    @app.errorhandler(SwarmLoaderError)
    def handle_swarm_loader_error(exc: SwarmLoaderError):
        return jsonify({"success": False, "error": str(exc)}), 500

    @app.errorhandler(KeyError)
    def handle_key_error(exc: KeyError):
        return jsonify({"success": False, "error": str(exc)}), 404

    @app.errorhandler(ValueError)
    def handle_value_error(exc: ValueError):
        return jsonify({"success": False, "error": str(exc)}), 400

    @app.errorhandler(Exception)
    def handle_unexpected_error(exc: Exception):
        if isinstance(exc, HTTPException):
            return jsonify({"success": False, "error": exc.description}), exc.code
        return jsonify({"success": False, "error": str(exc)}), 500
