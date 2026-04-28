"""工作区文件写入工具。

本模块提供 ``FileWriterTool``，用于将文本内容写入工作区指定路径。
支持自动创建父目录、多层路径解析回退、工作区沙箱校验以及敏感路径拦截。

主要导出内容：
    - :class:`FileWriterTool`: 文件写入工具定义。
    - ``TOOL``: 模块级单例实例。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from core.toodefl import ToolContext, ToolDefinition, require_tool_capability


class FileWriterTool(ToolDefinition):
    """Write text content to a file path."""

    def __init__(self) -> None:
        super().__init__(
            tool_name="file_writer",
            description="Write text content to a file in the workspace.",
            schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Workspace-relative destination file path.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Complete UTF-8 text content to write.",
                    },
                    "fallback_path": {
                        "type": "string",
                        "description": "Optional fallback destination path when path is not available.",
                    },
                },
                "required": ["path", "content"],
            },
        )

    def _resolve_path(self, arguments: Dict[str, Any]) -> str:
        """按优先级解析目标文件路径。

        顺序为：显式 path > payload/canonical_payload 中的 path/filename >
        artifact 中的 path/filename > fallback_path。

        Args:
            arguments: 工具入参字典。

        Returns:
            解析出的目标路径字符串。

        Raises:
            ValueError: 所有来源均未提供有效路径时抛出。
        """
        # Priority 1: explicit path
        path_value = str(arguments.get("path", "")).strip()
        if path_value:
            return path_value

        # Priority 2: payload path hint
        payload = arguments.get("payload")
        if payload is None:
            payload = arguments.get("canonical_payload")
        if isinstance(payload, dict):
            for key in ("path", "filename"):
                value = str(payload.get(key, "")).strip()
                if value:
                    return value
            # Legacy artifact support (envelope mode)
            artifact = payload.get("artifact")
            if isinstance(artifact, dict):
                for key in ("path", "filename"):
                    value = str(artifact.get(key, "")).strip()
                    if value:
                        return value

        # Priority 3: fallback_path
        fallback = str(arguments.get("fallback_path", "")).strip()
        if fallback:
            return fallback

        raise ValueError(
            "file_writer requires a non-empty 'path' (or 'fallback_path')."
        )

    async def execute(
        self,
        arguments: Dict[str, Any],
        *,
        context: Optional[ToolContext] = None,
    ) -> Any:
        """将文本内容写入目标文件。

        流程包括：解析路径 → 工作区沙箱校验 → 敏感路径拦截 →
        自动创建父目录 → 写入内容 → 返回结果。

        Args:
            arguments: 工具入参，需包含 path 与 content。
            context: 工具执行上下文。

        Returns:
            Dict[str, Any]: 包含 written、path、bytes 及上下文摘要的结果字典。

        Raises:
            ValueError: 路径越界或命中敏感路径规则时抛出。
        """
        require_tool_capability(context, "file_write", self.tool_name)
        path_value = self._resolve_path(arguments)
        target_path = Path(path_value)
        if self._is_workspace_restricted(context):
            workspace_root = self._resolve_workspace_root(context)
            if workspace_root is not None:
                if not target_path.is_absolute():
                    target_path = workspace_root / target_path
                target_resolved = target_path.resolve()
                if not self._path_is_within_root(target_resolved, workspace_root):
                    raise ValueError(
                        f"file_writer path '{target_path}' is outside workspace root '{workspace_root}'."
                    )
                target_path = target_resolved
        content_value = arguments.get("content")
        if content_value is None:
            content_value = arguments.get("input", "")
        content = str(content_value)
        self._reject_sensitive_path(target_path, context)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")
        return {
            "written": True,
            "path": str(target_path),
            "bytes": len(content.encode("utf-8")),
            "context": {
                "agent_id": context.agent_id if context else None,
                "node_id": context.node_id if context else None,
                "rounds": context.rounds if context else None,
                "workspace_mode": context.workspace_mode if context else None,
                "workspace_root": str(context.workspace_root) if context and context.workspace_root else None,
            },
        }

    def _is_workspace_restricted(self, context: Optional[ToolContext]) -> bool:
        """判断当前上下文是否处于受限工作区模式。

        Args:
            context: 工具上下文。

        Returns:
            True 表示需要沙箱校验。
        """
        if context is None:
            return True
        return str(getattr(context, "workspace_mode", "workspace")).strip() != "full_access"

    def _resolve_workspace_root(self, context: Optional[ToolContext]) -> Optional[Path]:
        """解析当前工作区的根目录路径。

        Args:
            context: 工具上下文。

        Returns:
            工作区绝对路径，或当前进程目录。
        """
        if context is None:
            return Path.cwd().resolve()
        workspace_root = getattr(context, "workspace_root", None)
        if workspace_root is None:
            return Path.cwd().resolve()
        return Path(workspace_root).resolve()

    def _path_is_within_root(self, target_path: Path, workspace_root: Path) -> bool:
        """判断目标路径是否位于工作区根目录之下。

        Args:
            target_path: 待检查路径。
            workspace_root: 工作区根路径。

        Returns:
            True 表示位于工作区内。
        """
        try:
            return target_path == workspace_root or workspace_root in target_path.parents
        except RuntimeError:
            return False

    def _reject_sensitive_path(self, target_path: Path, context: Optional[ToolContext]) -> None:
        """拦截对敏感路径或配置文件的写入请求。

        禁止写入 .git、虚拟环境、shell 配置文件等；
        对于 config.toml / .env 等配置文件，需要显式具备 config_write 能力。

        Args:
            target_path: 目标文件路径。
            context: 工具上下文。

        Raises:
            ValueError: 命中敏感路径规则时抛出。
        """
        parts = {part.lower() for part in target_path.parts}
        blocked_parts = {".git", ".venv", ".lvenv", "__pycache__"}
        if parts & blocked_parts:
            raise ValueError(f"file_writer refuses to write sensitive path '{target_path}'.")
        blocked_names = {".bashrc", ".profile", ".zshrc"}
        if target_path.name.lower() in blocked_names:
            raise ValueError(f"file_writer refuses to write sensitive path '{target_path}'.")
        config_names = {"config.toml", ".env", ".env.local", ".env.production"}
        if target_path.name.lower() in config_names and not (
            context is not None and context.has_capability("config_write")
        ):
            raise ValueError(
                f"file_writer refuses to write configuration path '{target_path}' without 'config_write'."
            )


TOOL = FileWriterTool()
