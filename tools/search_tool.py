from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from core.toodefl import ToolContext, ToolDefinition, require_tool_capability


class SearchTool(ToolDefinition):
    """Search for text patterns in files within the workspace."""

    def __init__(self) -> None:
        super().__init__(tool_name="search", description="Search for text patterns in files within the workspace.")

    async def execute(
        self,
        arguments: Dict[str, Any],
        *,
        context: Optional[ToolContext] = None,
    ) -> Any:
        require_tool_capability(context, "file_read", self.tool_name)
        query = str(arguments.get("query", "")).strip()
        if not query:
            raise ValueError("search requires a non-empty 'query'.")
        path_str = str(arguments.get("path", ".")).strip()
        glob_pattern = str(arguments.get("glob", "*.py")).strip()
        if not glob_pattern:
            glob_pattern = "*"
        max_results = int(arguments.get("max_results", 20))
        if max_results <= 0:
            max_results = 20
        workspace_root = self._resolve_workspace_root(context)
        search_path = Path(path_str)
        if search_path.is_absolute():
            search_path = search_path.resolve()
            if self._is_workspace_restricted(context):
                if not self._path_is_within_root(search_path, workspace_root):
                    raise ValueError(
                        f"search path '{search_path}' is outside workspace root '{workspace_root}'."
                    )
        else:
            search_path = (workspace_root / search_path).resolve()
            if self._is_workspace_restricted(context):
                if not self._path_is_within_root(search_path, workspace_root):
                    raise ValueError(
                        f"search path '{search_path}' is outside workspace root '{workspace_root}'."
                    )
        if not search_path.exists():
            raise ValueError(f"search path '{search_path}' does not exist.")
        matches: List[Dict[str, Any]] = []
        total_matches = 0
        query_lower = query.lower()
        if search_path.is_file():
            files = [search_path]
        else:
            files = search_path.rglob(glob_pattern)
        for file_path in files:
            if not file_path.is_file():
                continue
            if self._is_binary(file_path):
                continue
            try:
                text = file_path.read_text(encoding="utf-8", errors="ignore")
            except (OSError, UnicodeDecodeError):
                continue
            lines = text.splitlines()
            for line_number, line_text in enumerate(lines, start=1):
                if query_lower in line_text.lower():
                    total_matches += 1
                    if len(matches) < max_results:
                        try:
                            rel_file = str(file_path.relative_to(workspace_root))
                        except ValueError:
                            rel_file = str(file_path)
                        matches.append({
                            "file": rel_file,
                            "line": line_number,
                            "text": line_text,
                        })
                    if total_matches >= max_results and len(matches) >= max_results:
                        break
            if total_matches >= max_results and len(matches) >= max_results:
                break
        return {
            "query": query,
            "matches": matches,
            "total_matches": total_matches,
        }

    def _is_binary(self, file_path: Path) -> bool:
        try:
            with file_path.open("rb") as f:
                chunk = f.read(8192)
                if b"\x00" in chunk:
                    return True
        except OSError:
            return True
        return False

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


TOOL = SearchTool()
