from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from web.app_factory import create_app


DEFAULT_CONFIG_PATH = Path("config.toml")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Angelus FastAPI backend")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to the top-level config.toml file.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="FastAPI host.")
    parser.add_argument("--port", type=int, default=5000, help="FastAPI port.")
    parser.add_argument("--debug", action="store_true", help="Enable auto-reload mode.")
    return parser.parse_args()


def main() -> None:
    """Application entry point."""
    args = parse_args()
    app = create_app(args.config)
    uvicorn.run(app, host=args.host, port=args.port, reload=args.debug, timeout_graceful_shutdown=10)


if __name__ == "__main__":
    main()
