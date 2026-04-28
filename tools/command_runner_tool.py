"""工作区 Shell 命令执行工具。

本模块提供 ``CommandRunnerTool``，用于在受控工作区内异步执行 shell 命令。
内置危险命令正则拦截、工作区路径沙箱以及超时自动终止机制，
确保命令执行不会越权或破坏系统。

主要导出内容：
    - :class:`CommandRunnerTool`: 命令执行工具定义。
    - ``TOOL``: 模块级单例实例。
"""

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
        """执行一次受控的 shell 命令。

        流程包括：解析命令 → 危险模式拦截 → 解析工作目录 → 沙箱校验 →
        异步执行 → 结果封装。若超时则主动 kill 子进程。

        Args:
            arguments: 工具入参，需包含 ``command``。
            context: 工具执行上下文，用于权限与路径校验。

        Returns:
            Dict[str, Any]: 包含 command、returncode、stdout、stderr、duration_ms
            以及可选 error 字段的结果字典。
        """
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
        # 在非 full_access 模式下强制限制命令只能在工作区内执行
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
                # 超时后强制终止子进程，避免僵尸进程占用资源
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
        """基于正则模式拦截已知高危命令。

        覆盖 rm -rf /、sudo、fork 炸弹、磁盘格式化、管道到 sh 等常见危险模式。
        命中后直接抛出 ``ToolPolicyDeniedError``，拒绝执行。

        Args:
            command: 待检查的命令字符串。

        Raises:
            ToolPolicyDeniedError: 命中危险模式时抛出。
        """
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
                raise ToolPolicyDeniedError(
                    tool_name=self.tool_name,
                    command=command,
                    reason="dangerous_command",
                    blocked_tokens=[pattern],
                    suggested_safe_calls=self._suggest_safe_calls(command),
                    message=f"command_runner refuses to run dangerous command: '{command}'.",
                )

    def _classify_policy_denial(self, command: str) -> tuple[str, list[str]] | None:
        """对命令中的 shell 元字符进行分类，用于策略拒绝分析。

        Args:
            command: 待分类的命令字符串。

        Returns:
            (拒绝原因, 被拦截的 token 列表) 或 None。
        """
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
        """从被拦截的复合命令中提取若干简单子命令作为安全替代建议。

        若无法提取有效建议，则返回一组通用的安全示例（pwd、ls）。

        Args:
            command: 原始被拒绝的命令。

        Returns:
            建议的安全调用字典列表。
        """
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
        """从多种可能的键名中解析出实际要执行的命令。

        支持的键按优先级为：command、cmd、shell、input，以及嵌套 payload 中的同名键。

        Args:
            arguments: 工具入参字典。

        Returns:
            解析出的命令字符串；若未找到则返回空字符串。
        """
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
        """判断当前上下文是否处于受限工作区模式。

        Args:
            context: 工具上下文。

        Returns:
            True 表示非 full_access，需要执行路径沙箱校验。
        """
        if context is None:
            return True
        return str(getattr(context, "workspace_mode", "workspace")).strip() != "full_access"

    def _resolve_workspace_root(self, context: Optional[ToolContext]) -> Path:
        """解析当前工作区的根目录路径。

        若上下文未提供 workspace_root，则回退到当前进程工作目录。

        Args:
            context: 工具上下文。

        Returns:
            解析后的绝对路径。
        """
        if context is None:
            return Path.cwd().resolve()
        workspace_root = getattr(context, "workspace_root", None)
        if workspace_root is None:
            return Path.cwd().resolve()
        return Path(workspace_root).resolve()

    def _path_is_within_root(self, target_path: Path, workspace_root: Path) -> bool:
        """判断目标路径是否位于工作区根目录之下。

        使用路径解析后的父子关系判断，防止 ``..`` 绕过沙箱。

        Args:
            target_path: 待检查的目标路径。
            workspace_root: 工作区根路径。

        Returns:
            True 表示目标路径位于工作区内。
        """
        try:
            return target_path == workspace_root or workspace_root in target_path.parents
        except RuntimeError:
            return False


TOOL = CommandRunnerTool()
