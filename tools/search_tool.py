"""工作区文本搜索工具。

本模块提供 ``SearchTool``，用于在工作区内按关键词搜索文件内容。
支持 glob 过滤、结果数量上限、二进制文件跳过以及工作区沙箱校验。

主要导出内容：
    - :class:`SearchTool`: 文本搜索工具定义。
    - ``TOOL``: 模块级单例实例。
"""

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
        """在工作区内执行关键词搜索。

        流程包括：解析查询 → 解析搜索路径 → 沙箱校验 → 遍历文件 →
        逐行匹配 → 结果封装。二进制文件会被自动跳过。

        Args:
            arguments: 工具入参，需包含 ``query``。
            context: 工具执行上下文，用于权限与路径校验。

        Returns:
            Dict[str, Any]: 包含 query、matches（列表）与 total_matches 的结果字典。

        Raises:
            ValueError: query 为空、路径越界或路径不存在时抛出。
        """
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
            # 跳过二进制文件，避免无意义的乱码匹配与性能浪费
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
                    # 当 total_matches 与 matches 均达到上限时可提前退出两层循环
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
        """通过读取前 8192 字节检测文件是否为二进制。

        若发现空字节（\x00）则视为二进制，同时捕获 OSError 以防权限问题导致崩溃。

        Args:
            file_path: 待检测文件路径。

        Returns:
            True 表示为二进制文件。
        """
        try:
            with file_path.open("rb") as f:
                chunk = f.read(8192)
                if b"\x00" in chunk:
                    return True
        except OSError:
            return True
        return False

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

    def _resolve_workspace_root(self, context: Optional[ToolContext]) -> Path:
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


TOOL = SearchTool()
