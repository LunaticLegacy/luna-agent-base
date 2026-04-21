from __future__ import annotations

import json
from typing import Any, Dict, Optional

from core.toodefl import ToolContext, ToolDefinition


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
        from duckduckgo_search import DDGS

        query = str(arguments.get("query", "")).strip()
        if not query:
            return {"error": "Query is required."}

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
