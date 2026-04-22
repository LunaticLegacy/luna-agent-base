from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify

from core.swarm_loader import SwarmLoaderError
from web.content_store import ContentStore
from web.runtime import RuntimeRegistry

from .errors import register_error_handlers
from .routes import catalog_bp, content_bp, health_bp, swarms_bp


def create_app(config_path: str | Path = "config.toml") -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    config_path = Path(config_path)

    @app.after_request
    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response

    @app.route("/<path:path>", methods=["OPTIONS"])
    @app.route("/", methods=["OPTIONS"])
    def handle_options(path=""):
        return "", 204

    try:
        runtime_registry = RuntimeRegistry.from_config_path(config_path)
    except SwarmLoaderError as exc:
        runtime_registry = RuntimeRegistry(
            config_path=config_path,
            root_config=None,
            load_error=str(exc),
        )

    app.extensions["angelus_runtime"] = runtime_registry
    app.extensions["angelus_content"] = ContentStore.from_runtime_registry(
        data_dir=config_path.parent / "data",
        runtime_registry=runtime_registry,
    )

    register_error_handlers(app)
    app.register_blueprint(health_bp, url_prefix="/api")
    app.register_blueprint(catalog_bp, url_prefix="/api")
    app.register_blueprint(content_bp, url_prefix="/api")
    app.register_blueprint(swarms_bp, url_prefix="/api")

    @app.get("/")
    def index():
        return jsonify(
            {
                "success": True,
                "service": "angelus",
                "swarm_count": len(runtime_registry.swarms),
                "load_error": runtime_registry.load_error,
            }
        )

    @app.get("/api")
    def api_index():
        return jsonify(
            {
                "success": True,
                "service": "angelus",
                "swarm_count": len(runtime_registry.swarms),
                "load_error": runtime_registry.load_error,
                "api_root": "/api",
            }
        )

    return app
