from __future__ import annotations

from flask import Blueprint, current_app, jsonify

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health():
    return jsonify({"success": True, "status": "ok"})


@health_bp.get("/ready")
def ready():
    registry = current_app.extensions.get("angelus_runtime")
    if registry is None:
        return jsonify({"success": False, "ready": False, "reason": "runtime registry missing"}), 503

    load_error = registry.load_error
    if load_error:
        return (
            jsonify(
                {
                    "success": False,
                    "ready": False,
                    "reason": "swarm load error",
                    "load_error": load_error,
                }
            ),
            503,
        )

    swarms = registry.swarms
    if not swarms:
        return jsonify({"success": False, "ready": False, "reason": "no swarms loaded"}), 503

    invalid = []
    for swarm_name, swarm in swarms.items():
        validation = swarm.core.check_execution_graph_available()
        if not validation.is_valid:
            invalid.append(
                {
                    "swarm": swarm_name,
                    "errors": validation.errors,
                }
            )

    if invalid:
        return jsonify({"success": False, "ready": False, "invalid_swarms": invalid}), 503

    return jsonify({"success": True, "ready": True, "swarm_count": len(swarms)})
