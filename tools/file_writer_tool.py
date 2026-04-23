from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from core.toodefl import ToolContext, ToolDefinition


class FileWriterTool(ToolDefinition):
    """Write text content to a file path."""

    def __init__(self) -> None:
        super().__init__(tool_name="file_writer", description="Write text to a file.")

    async def execute(
        self,
        arguments: Dict[str, Any],
        *,
        context: Optional[ToolContext] = None,
    ) -> Any:
        path_value = str(arguments.get("path", "")).strip()
        if not path_value:
            raise ValueError("file_writer requires a non-empty 'path'.")
        target_path = Path(path_value)
        if self._is_workspace_restricted(context):
            workspace_root = self._resolve_workspace_root(context)
            if workspace_root is not None:
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
        if context is None:
            return True
        return str(getattr(context, "workspace_mode", "workspace")).strip() != "full_access"

    def _resolve_workspace_root(self, context: Optional[ToolContext]) -> Optional[Path]:
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


TOOL = FileWriterTool()
