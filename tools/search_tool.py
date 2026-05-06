"""Workspace text search tool.

Searches for text patterns in files within the workspace with glob filtering.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.llm_fetcher.tool import Tool


DEFAULT_WORKSPACE_ROOT = Path.cwd().resolve()


def _resolve_search_path(path_str: str, workspace_root: Path) -> Path:
    search_path = Path(path_str)
    if search_path.is_absolute():
        return search_path.resolve()
    return (workspace_root / search_path).resolve()


def _path_is_within_root(target_path: Path, workspace_root: Path) -> bool:
    try:
        return target_path == workspace_root or workspace_root in target_path.parents
    except RuntimeError:
        return False


def _is_binary(file_path: Path) -> bool:
    try:
        with file_path.open("rb") as f:
            chunk = f.read(8192)
            if b"\x00" in chunk:
                return True
    except OSError:
        return True
    return False


def create_search_tools(
    workspace_root: Optional[Path] = None,
) -> List[Tool]:
    """Create search tools.

    Args:
        workspace_root: Sandbox root for path restriction. Defaults to cwd.
    """
    root = Path(workspace_root or DEFAULT_WORKSPACE_ROOT).resolve()

    async def _search(**kwargs: Any) -> Any:
        query = str(kwargs.get("query", "")).strip()
        if not query:
            raise ValueError("search requires a non-empty 'query'.")

        path_str = str(kwargs.get("path", ".")).strip()
        glob_pattern = str(kwargs.get("glob", "*.py")).strip() or "*"
        max_results = int(kwargs.get("max_results", 20))
        if max_results <= 0:
            max_results = 20

        search_path = _resolve_search_path(path_str, root)
        if not _path_is_within_root(search_path, root):
            raise ValueError(
                f"search path '{search_path}' is outside workspace root '{root}'."
            )
        if not search_path.exists():
            raise ValueError(f"search path '{search_path}' does not exist.")

        matches: List[Dict[str, Any]] = []
        total_matches = 0
        query_lower = query.lower()
        files = [search_path] if search_path.is_file() else search_path.rglob(glob_pattern)

        for file_path in files:
            if not file_path.is_file():
                continue
            if _is_binary(file_path):
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
                            rel_file = str(file_path.relative_to(root))
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

    return [
        Tool(
            name="search",
            description="Search for text patterns in files within the workspace.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Text pattern to search for.",
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory or file to search in (default: workspace root).",
                    },
                    "glob": {
                        "type": "string",
                        "description": "Glob pattern for file filtering (default: *.py).",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of matches to return.",
                    },
                },
                "required": ["query"],
            },
            handler=_search,
        ),
    ]
