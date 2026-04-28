"""基于 DuckDuckGo 的网络搜索工具。

本模块提供 ``WebSearchTool``，用于对给定查询执行网络搜索并返回标题、
摘要与 URL 列表。结果数量上限被限制为 10 条，防止响应体过大。

主要导出内容：
    - :class:`WebSearchTool`: 网络搜索工具定义。
    - ``TOOL``: 模块级单例实例。
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from core.toodefl import ToolContext, ToolDefinition, require_tool_capability


class WebSearchTool(ToolDefinition):
    """Search the web using DuckDuckGo."""

    def __init__(self) -> None:
        super().__init__(
            tool_name="web_search",
            description="Search the web for information on a given query. Returns a list of results with title, snippet, and URL.",
            schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query string.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default 5, max 10).",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        )

    async def execute(
        self,
        arguments: Dict[str, Any],
        *,
        context: Optional[ToolContext] = None,
    ) -> Any:
        """使用 DuckDuckGo 执行网络搜索。

        Args:
            arguments: 工具入参，需包含 ``query``。
            context: 工具执行上下文，用于校验 network_access 能力。

        Returns:
            Dict[str, Any]: 包含 query 与 results（列表）的结果字典；
            出错时返回 ``{"error": ...}``。
        """
        require_tool_capability(context, "network_access", self.tool_name)
        from duckduckgo_search import DDGS

        query = str(arguments.get("query", "")).strip()
        if not query:
            return {"error": "Query is required."}

        # 将 max_results 硬上限设为 10，避免单次返回过多条目拖慢下游处理
        max_results = min(int(arguments.get("max_results", 5)), 10)

        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
                return {
                    "query": query,
                    "results": [
                        {
                            "title": r.get("title", ""),
                            "snippet": r.get("body", ""),
                            "url": r.get("href", ""),
                        }
                        for r in results
                    ],
                }
        except Exception as exc:
            return {"error": f"Search failed: {exc}"}


TOOL = WebSearchTool()
