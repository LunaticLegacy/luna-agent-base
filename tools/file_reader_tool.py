"""Workspace file reader tool.

Reads text content from a workspace-relative file path with sandbox checks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.llm_fetcher.tool import Tool


DEFAULT_WORKSPACE_ROOT = Path.cwd().resolve()


def _resolve_path(path_value: str, workspace_root: Path) -> Path:
    target = Path(path_value)
    if not target.is_absolute():
        target = workspace_root / target
    return target.resolve()


def _path_is_within_root(target_path: Path, workspace_root: Path) -> bool:
    try:
        return target_path == workspace_root or workspace_root in target_path.parents
    except RuntimeError:
        return False


def _reject_sensitive_path(target_path: Path) -> None:
    parts = {part.lower() for part in target_path.parts}
    blocked_parts = {".git", ".venv", ".lvenv", "__pycache__"}
    if parts & blocked_parts:
        raise ValueError(f"file_reader refuses to read sensitive path '{target_path}'.")
    blocked_names = {".bashrc", ".profile", ".zshrc"}
    if target_path.name.lower() in blocked_names:
        raise ValueError(f"file_reader refuses to read sensitive path '{target_path}'.")
    config_names = {"config.toml", ".env", ".env.local", ".env.production"}
    if target_path.name.lower() in config_names:
        raise ValueError(
            f"file_reader refuses to read configuration path '{target_path}'."
        )


def create_file_reader_tools(
    workspace_root: Optional[Path] = None,
) -> List[Tool]:
    """Create file reader tools.

    Args:
        workspace_root: Sandbox root for path restriction. Defaults to cwd.
    """
    root = Path(workspace_root or DEFAULT_WORKSPACE_ROOT).resolve()

    async def _file_reader(**kwargs: Any) -> Any:
        path_value = str(kwargs.get("path", "")).strip()
        if not path_value:
            raise ValueError("file_reader requires a non-empty 'path'.")

        target_path = _resolve_path(path_value, root)
        if not _path_is_within_root(target_path, root):
            raise ValueError(
                f"file_reader path '{target_path}' is outside workspace root '{root}'."
            )
        _reject_sensitive_path(target_path)

        if not target_path.exists():
            return {
                "exists": False,
                "error": "File not found",
                "path": str(target_path),
            }

        content = target_path.read_text(encoding="utf-8")
        return {
            "content": content,
            "path": str(target_path),
            "bytes": len(content.encode("utf-8")),
            "exists": True,
        }

    return [
        Tool(
            name="file_reader",
            description="Read text content from a workspace-relative file path.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Workspace-relative file path to read.",
                    },
                },
                "required": ["path"],
            },
            handler=_file_reader,
        ),
    ]
