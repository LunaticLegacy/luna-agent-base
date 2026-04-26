from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from core.toodefl import ToolContext, ToolDefinition, require_tool_capability


class FileEditorTool(ToolDefinition):
    """Edit a file with precise replace/insert/delete operations."""

    def __init__(self) -> None:
        super().__init__(tool_name="file_editor", description="Edit a file with precise replace/insert/delete operations.")

    def _resolve_path(self, arguments: Dict[str, Any]) -> str:
        """Resolve target path with priority:
        explicit path > canonical_payload.artifact.path > canonical_payload.artifact.filename > fallback_path.
        """
        # Priority 1: explicit path
        path_value = str(arguments.get("path", "")).strip()
        if path_value:
            return path_value

        # Priority 2: canonical_payload artifact
        canonical = arguments.get("canonical_payload")
        if isinstance(canonical, dict):
            artifact = canonical.get("artifact")
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
            "file_editor requires a non-empty 'path' (or 'fallback_path', or canonical_payload.artifact.path)."
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
                        f"file_editor path '{target_path}' is outside workspace root '{workspace_root}'."
                    )
                target_path = target_resolved
        self._reject_sensitive_path(target_path, context)
        if not target_path.exists():
            raise ValueError(f"file_editor target file does not exist: '{target_path}'.")

        operation = str(arguments.get("operation", "")).strip().lower()
        if operation not in {"replace", "insert", "delete"}:
            raise ValueError(f"file_editor unsupported operation '{operation}'. Supported: replace, insert, delete.")

        content = target_path.read_text(encoding="utf-8")
        old_string = arguments.get("old_string", "")
        new_string = arguments.get("new_string", "")
        after = arguments.get("after", "")

        if operation == "replace":
            if old_string not in content:
                raise ValueError("file_editor replace operation: 'old_string' not found in file.")
            replacements = content.count(old_string)
            new_content = content.replace(old_string, new_string)
        elif operation == "insert":
            if after == "":
                new_content = new_string + content
                replacements = 1
            else:
                if after not in content:
                    raise ValueError("file_editor insert operation: 'after' string not found in file.")
                replacements = content.count(after)
                new_content = content.replace(after, after + new_string)
        else:  # delete
            if old_string not in content:
                raise ValueError("file_editor delete operation: 'old_string' not found in file.")
            replacements = content.count(old_string)
            new_content = content.replace(old_string, "")

        target_path.write_text(new_content, encoding="utf-8")
        return {
            "edited": True,
            "path": str(target_path),
            "operation": operation,
            "replacements": replacements,
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
            raise ValueError(f"file_editor refuses to edit sensitive path '{target_path}'.")
        blocked_names = {".bashrc", ".profile", ".zshrc"}
        if target_path.name.lower() in blocked_names:
            raise ValueError(f"file_editor refuses to edit sensitive path '{target_path}'.")
        config_names = {"config.toml", ".env", ".env.local", ".env.production"}
        if target_path.name.lower() in config_names and not (
            context is not None and context.has_capability("config_write")
        ):
            raise ValueError(
                f"file_editor refuses to edit configuration path '{target_path}' without 'config_write'."
            )


TOOL = FileEditorTool()
