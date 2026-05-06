"""Workspace shell command runner tool.

Executes shell commands in a controlled workspace with dangerous-pattern blocking
and timeout handling.
"""

from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.llm_fetcher.tool import Tool


DEFAULT_WORKSPACE_ROOT = Path.cwd().resolve()


def _resolve_cwd(cwd: Optional[str], workspace_root: Path) -> Path:
    if cwd:
        cwd_path = Path(cwd)
        if not cwd_path.is_absolute():
            cwd_path = workspace_root / cwd_path
        return cwd_path.resolve()
    return workspace_root


def _path_is_within_root(target_path: Path, workspace_root: Path) -> bool:
    try:
        return target_path == workspace_root or workspace_root in target_path.parents
    except RuntimeError:
        return False


def _reject_dangerous_command(command: str) -> None:
    lowered = command.lower()
    dangerous_patterns = [
        r"rm\s+-rf\s+/",
        r"sudo\s",
        r":\(\)\s*\{\s*:\|:\s*\&\s*\};:",
        r"mkfs\.",
        r"dd\s+if=.*of=/dev/[sh]d",
        r">\s*/dev/[sh]d[a-z]",
        r"curl\s+.*\|\s*sh",
        r"wget\s+.*\|\s*sh",
    ]
    for pattern in dangerous_patterns:
        if re.search(pattern, lowered):
            raise ValueError(
                f"command_runner refuses to run dangerous command: '{command}'."
            )


def create_command_runner_tools(
    workspace_root: Optional[Path] = None,
) -> List[Tool]:
    """Create command runner tools.

    Args:
        workspace_root: Sandbox root for cwd restriction. Defaults to cwd.
    """
    root = Path(workspace_root or DEFAULT_WORKSPACE_ROOT).resolve()

    async def _command_runner(**kwargs: Any) -> Any:
        command = str(kwargs.get("command", "")).strip()
        if not command:
            raise ValueError("command_runner requires a non-empty 'command'.")
        _reject_dangerous_command(command)

        timeout_seconds = int(kwargs.get("timeout_seconds", 60))
        if timeout_seconds <= 0:
            timeout_seconds = 60

        cwd_path = _resolve_cwd(str(kwargs.get("cwd", "")).strip() or None, root)
        if not _path_is_within_root(cwd_path, root):
            raise ValueError(
                f"command_runner cwd '{cwd_path}' is outside workspace root '{root}'."
            )

        start_time = time.time()
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd_path),
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return {
                    "command": command,
                    "returncode": -1,
                    "stdout": "",
                    "stderr": "",
                    "error": "Timeout",
                    "duration_ms": int((time.time() - start_time) * 1000),
                }
            duration_ms = int((time.time() - start_time) * 1000)
            stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
            stderr = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""
            return {
                "command": command,
                "returncode": proc.returncode if proc.returncode is not None else -1,
                "stdout": stdout,
                "stderr": stderr,
                "duration_ms": duration_ms,
            }
        except Exception as exc:
            duration_ms = int((time.time() - start_time) * 1000)
            return {
                "command": command,
                "returncode": -1,
                "stdout": "",
                "stderr": "",
                "error": str(exc),
                "duration_ms": duration_ms,
            }

    return [
        Tool(
            name="command_runner",
            description="Run a shell command in the workspace.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to run inside the workspace.",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Optional working directory, relative to the workspace root.",
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "description": "Optional timeout in seconds.",
                    },
                },
                "required": ["command"],
            },
            handler=_command_runner,
        ),
    ]
