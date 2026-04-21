from __future__ import annotations

from pathlib import Path
from typing import Dict

from flask import Flask, jsonify

from core.swarm_loader import SwarmLoaderError, load_all_swarms
from core.swarm_spec import load_root_config

from .errors import register_error_handlers
from .routes import health_bp, swarms_bp


def _load_runtime_registry(config_path: Path) -> Dict[str, object]:
    root_config = load_root_config(config_path)
    swarms = load_all_swarms(root_config.swarm_root)
    return {
        "config_path": config_path,
        "root_config": root_config,
        "swarms": {swarm.manifest.swarm_name: swarm for swarm in swarms},
    }


def create_app(config_path: str | Path = "config.toml") -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    config_path = Path(config_path)

    try:
        runtime_registry = _load_runtime_registry(config_path)
    except SwarmLoaderError as exc:
        runtime_registry = {
            "config_path": config_path,
            "root_config": None,
            "swarms": {},
            "load_error": str(exc),
        }

    app.extensions["angelus_runtime"] = runtime_registry

    register_error_handlers(app)
    app.register_blueprint(health_bp)
    app.register_blueprint(swarms_bp)

    @app.get("/")
    def index():
        swarms = runtime_registry.get("swarms", {})
        load_error = runtime_registry.get("load_error")
        return jsonify(
            {
                "success": True,
                "service": "angelus",
                "swarm_count": len(swarms),
                "load_error": load_error,
            }
        )

    return app
