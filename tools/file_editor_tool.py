"""Workspace file editor tool.

Performs precise replace/insert/delete operations on text files with sandbox checks.
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
        raise ValueError(f"file_editor refuses to edit sensitive path '{target_path}'.")
    blocked_names = {".bashrc", ".profile", ".zshrc"}
    if target_path.name.lower() in blocked_names:
        raise ValueError(f"file_editor refuses to edit sensitive path '{target_path}'.")
    config_names = {"config.toml", ".env", ".env.local", ".env.production"}
    if target_path.name.lower() in config_names:
        raise ValueError(
            f"file_editor refuses to edit configuration path '{target_path}'."
        )


def create_file_editor_tools(
    workspace_root: Optional[Path] = None,
) -> List[Tool]:
    """Create file editor tools.

    Args:
        workspace_root: Sandbox root for path restriction. Defaults to cwd.
    """
    root = Path(workspace_root or DEFAULT_WORKSPACE_ROOT).resolve()

    async def _file_editor(**kwargs: Any) -> Any:
        path_value = str(kwargs.get("path", "")).strip()
        if not path_value:
            raise ValueError("file_editor requires a non-empty 'path'.")

        target_path = _resolve_path(path_value, root)
        if not _path_is_within_root(target_path, root):
            raise ValueError(
                f"file_editor path '{target_path}' is outside workspace root '{root}'."
            )
        _reject_sensitive_path(target_path)

        if not target_path.exists():
            raise ValueError(f"file_editor target file does not exist: '{target_path}'.")

        operation = str(kwargs.get("operation", "")).strip().lower()
        if operation not in {"replace", "insert", "delete"}:
            raise ValueError(
                f"file_editor unsupported operation '{operation}'. Supported: replace, insert, delete."
            )

        content = target_path.read_text(encoding="utf-8")
        old_string = kwargs.get("old_string", "")
        new_string = kwargs.get("new_string", "")
        after = kwargs.get("after", "")

        if operation == "replace":
            if old_string not in content:
                raise ValueError("file_editor replace: 'old_string' not found in file.")
            replacements = content.count(old_string)
            new_content = content.replace(old_string, new_string)
        elif operation == "insert":
            if after == "":
                new_content = new_string + content
                replacements = 1
            else:
                if after not in content:
                    raise ValueError("file_editor insert: 'after' string not found in file.")
                replacements = content.count(after)
                new_content = content.replace(after, after + new_string)
        else:  # delete
            if old_string not in content:
                raise ValueError("file_editor delete: 'old_string' not found in file.")
            replacements = content.count(old_string)
            new_content = content.replace(old_string, "")

        target_path.write_text(new_content, encoding="utf-8")
        return {
            "edited": True,
            "path": str(target_path),
            "operation": operation,
            "replacements": replacements,
        }

    return [
        Tool(
            name="file_editor",
            description="Edit a file with precise replace/insert/delete operations.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Workspace-relative target file path.",
                    },
                    "operation": {
                        "type": "string",
                        "enum": ["replace", "insert", "delete"],
                    },
                    "old_string": {
                        "type": "string",
                        "description": "Text to replace or delete.",
                    },
                    "new_string": {
                        "type": "string",
                        "description": "Replacement text or inserted text.",
                    },
                    "after": {
                        "type": "string",
                        "description": "Anchor text for insert operations.",
                    },
                },
                "required": ["path", "operation"],
            },
            handler=_file_editor,
        ),
    ]
