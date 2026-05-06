"""Angelus FastAPI backend entry point.

Reads ``config.toml`` and bootstraps the Uvicorn server.
Business routes are served directly (no prefix) — ``base_url`` is only used
to resolve the bind address (host / port).
"""

from __future__ import annotations

import argparse
import os
import tomllib
from pathlib import Path
from typing import Any, Dict

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from web import create_app

DEFAULT_CONFIG_PATH = Path("config.toml")


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Angelus FastAPI backend")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to the top-level config.toml file.",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="FastAPI bind host (overrides config).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="FastAPI bind port (overrides config).",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable auto-reload mode.",
    )
    return parser.parse_args()


def load_config(path: Path) -> Dict[str, Any]:
    """Load and return the TOML config as a plain dict."""
    if not path.is_file():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def _extract_bind(config: Dict[str, Any]) -> tuple[str, int]:
    """Return ``(host, port)`` parsed from ``api.base_url``."""
    from urllib.parse import urlparse

    api_cfg = config.get("api", {})
    base_url = api_cfg.get("base_url", "http://127.0.0.1:5000/api")
    parsed = urlparse(base_url)

    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 5000
    return host, port


def _resolve_api_token(config: Dict[str, Any]) -> str | None:
    """Read the bearer token from the environment if auth is required."""
    api_cfg = config.get("api", {})
    if not api_cfg.get("require_auth"):
        return None
    env_name = api_cfg.get("api_token_env", "ANGELUS_API_TOKEN")
    return os.environ.get(env_name)


def build_app(config: Dict[str, Any]) -> FastAPI:
    """Assemble the main ASGI application.

    * Creates the business-route app via :func:`web.create_app`.
    * Applies CORS from ``cors_allowed_origins``.
    * Optionally adds bearer-token auth.
    """
    host, port = _extract_bind(config)
    api_cfg = config.get("api", {})

    # Business routes (thin REST layer over the runtime)
    app = create_app(config_path=None)

    # CORS
    cors_origins = api_cfg.get("cors_allowed_origins", [])
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Optional bearer-token auth
    api_token = _resolve_api_token(config)
    if api_token:

        @app.middleware("http")
        async def auth_middleware(request: Request, call_next):
            path = request.url.path
            if path.endswith(("/docs", "/openapi.json", "/redoc")):
                return await call_next(request)
            auth = request.headers.get("Authorization", "")
            if not auth.startswith("Bearer ") or auth[7:] != api_token:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or missing API token"},
                )
            return await call_next(request)

    # Persist resolved bind info for the CLI entry point
    app.state.host = host
    app.state.port = port
    app.state.config = config

    return app


def main() -> None:
    """Application entry point."""
    args = parse_args()
    config = load_config(args.config)

    app = build_app(config)

    host = args.host or app.state.host
    port = args.port or app.state.port

    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=args.debug,
        timeout_graceful_shutdown=10,
    )


if __name__ == "__main__":
    main()
