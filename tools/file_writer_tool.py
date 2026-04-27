from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from core.toodefl import ToolContext, ToolDefinition, require_tool_capability


class FileWriterTool(ToolDefinition):
    """Write text content to a file path."""

    def __init__(self) -> None:
        super().__init__(tool_name="file_writer", description="Write text to a file.")

    def _resolve_path(self, arguments: Dict[str, Any]) -> str:
        """Resolve target path with priority:
        explicit path > payload path hint > fallback_path.
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

    def _reject_sensitive_path(self, target_path: Path, context: Optional[ToolContext]) -> None:
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
