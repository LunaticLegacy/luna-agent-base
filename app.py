"""Angelus FastAPI 后端启动入口。

本模块提供命令行参数解析与 Uvicorn 服务启动逻辑。
通过 ``create_app`` 工厂函数构造 ASGI 应用实例，并支持
--config、--host、--port、--debug 等常用启动选项。

主要导出内容：
    - :func:`parse_args`: 解析命令行参数。
    - :func:`main`: 应用主入口。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from web.app_factory import create_app


DEFAULT_CONFIG_PATH = Path("config.toml")


def parse_args() -> argparse.Namespace:
    """解析命令行启动参数。

    Returns:
        argparse.Namespace: 包含 config、host、port、debug 的命名空间。
    """
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
