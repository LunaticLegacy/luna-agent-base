from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional

from core.errors import ToolPolicyDeniedError
from core.toodefl import ToolContext, ToolDefinition, require_tool_capability


class CommandRunnerTool(ToolDefinition):
    """Run a shell command in the workspace."""

    def __init__(self) -> None:
        super().__init__(
            tool_name="command_runner",
            description="Run a shell command in the workspace.",
            schema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to run inside the workspace.",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Optional working directory, relative to the workspace root unless absolute.",
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "description": "Optional timeout in seconds.",
                    },
                },
                "required": ["command"],
            },
        )

    async def execute(
        self,
        arguments: Dict[str, Any],
        *,
        context: Optional[ToolContext] = None,
    ) -> Any:
        require_tool_capability(context, "command_execute", self.tool_name)
        command = self._resolve_command(arguments)
        if not command:
            raise ValueError("command_runner requires a non-empty 'command'.")
        self._reject_dangerous_command(command)
        timeout_seconds = int(arguments.get("timeout_seconds", 60))
        if timeout_seconds <= 0:
            timeout_seconds = 60
        workspace_root = self._resolve_workspace_root(context)
        cwd = str(arguments.get("cwd", "")).strip()
        if cwd:
            cwd_path = Path(cwd)
            if not cwd_path.is_absolute():
                cwd_path = workspace_root / cwd_path
            cwd_path = cwd_path.resolve()
        else:
            cwd_path = workspace_root
        if self._is_workspace_restricted(context):
            if not self._path_is_within_root(cwd_path, workspace_root):
                raise ValueError(
                    f"command_runner cwd '{cwd_path}' is outside workspace root '{workspace_root}'."
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

    def _reject_dangerous_command(self, command: str) -> None:
        lowered = command.lower()
        policy_denial = self._classify_policy_denial(command)
        if policy_denial is not None:
            reason, blocked_tokens = policy_denial
            raise ToolPolicyDeniedError(
                tool_name=self.tool_name,
                command=command,
                reason=reason,
                blocked_tokens=blocked_tokens,
                suggested_safe_calls=self._suggest_safe_calls(command),
            )
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
                raise ToolPolicyDeniedError(
                    tool_name=self.tool_name,
                    command=command,
                    reason="dangerous_command",
                    blocked_tokens=[pattern],
                    suggested_safe_calls=self._suggest_safe_calls(command),
                    message=f"command_runner refuses to run dangerous command: '{command}'.",
                )

    def _classify_policy_denial(self, command: str) -> tuple[str, list[str]] | None:
        token_patterns = [
            ("&&", r"&&"),
            ("||", r"\|\|"),
            (";", r";"),
            ("|", r"(?<!\|)\|(?!\|)"),
            (">", r">"),
            ("<", r"<"),
            ("`", r"`"),
            ("$()", r"\$\("),
        ]
        blocked = [
            token
            for token, pattern in token_patterns
            if re.search(pattern, command)
        ]
        if not blocked:
            return None
        if any(token in blocked for token in (">", "<")):
            return "redirect_denied", blocked
        if any(token in blocked for token in (";", "&&", "||", "|")):
            return "compound_shell_command", blocked
        return "shell_metacharacter", blocked

    def _suggest_safe_calls(self, command: str) -> list[dict[str, Any]]:
        suggestions: list[dict[str, Any]] = []
        for raw_part in re.split(r"\s*(?:;|&&|\|\|)\s*", command):
            part = raw_part.strip()
            if not part:
                continue
            if any(token in part for token in ("|", ">", "<", "`", "$(")):
                continue
            suggestions.append({
                "tool": self.tool_name,
                "args": {
                    "command": part,
                    "cwd": ".",
                    "timeout_seconds": 60,
                },
            })
            if len(suggestions) >= 3:
                break
        if suggestions:
            return suggestions
        return [
            {
                "tool": self.tool_name,
                "args": {
                    "command": "pwd",
                    "cwd": ".",
                    "timeout_seconds": 60,
                },
            },
            {
                "tool": self.tool_name,
                "args": {
                    "command": "ls",
                    "cwd": ".",
                    "timeout_seconds": 60,
                },
            },
        ]

    def _resolve_command(self, arguments: Dict[str, Any]) -> str:
        for key in ("command", "cmd", "shell", "input"):
            value = arguments.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        payload = arguments.get("payload")
        if isinstance(payload, dict):
            for key in ("command", "cmd", "shell"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return ""

    def _is_workspace_restricted(self, context: Optional[ToolContext]) -> bool:
        if context is None:
            return True
        return str(getattr(context, "workspace_mode", "workspace")).strip() != "full_access"

    def _resolve_workspace_root(self, context: Optional[ToolContext]) -> Path:
        if context is None:
            return Path.cwd().resolve()
        workspace_root = getattr(context, "workspace_root", None)
        if workspace_root is None:
            return Path.cwd().resolve()
        return Path(workspace_root).resolve()

    def _path_is_within_root(self, target_path: Path, workspace_root: Path) -> bool:
        try:
            return target_path == workspace_root or workspace_root in target_path.parents
        except RuntimeError:
            return False


TOOL = CommandRunnerTool()
