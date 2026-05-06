"""Web search tool using DuckDuckGo.

Returns a list of results with title, snippet, and URL.
"""

from __future__ import annotations

from typing import Any, List

from modules.llm_fetcher.tool import Tool


def create_web_search_tools() -> List[Tool]:
    """Create web search tools."""

    async def _web_search(**kwargs: Any) -> Any:
        try:
            from duckduckgo_search import DDGS
        except Exception as exc:
            return {"error": f"duckduckgo_search not available: {exc}"}

        query = str(kwargs.get("query", "")).strip()
        if not query:
            return {"error": "Query is required."}

        max_results = min(int(kwargs.get("max_results", 5)), 10)

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

    return [
        Tool(
            name="web_search",
            description=(
                "Search the web for information on a given query. "
                "Returns a list of results with title, snippet, and URL."
            ),
            parameters={
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
            handler=_web_search,
        ),
    ]
