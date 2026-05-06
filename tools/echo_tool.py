"""Debug echo tool.

Returns the received arguments as-is for quick smoke-testing.
"""

from __future__ import annotations

from typing import Any, List

from modules.llm_fetcher.tool import Tool


def create_echo_tools() -> List[Tool]:
    """Create echo tools."""

    async def _echo(**kwargs: Any) -> Any:
        return {"echo": kwargs}

    return [
        Tool(
            name="echo",
            description="Echo the input payload back for debugging and wiring checks.",
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            },
            handler=_echo,
        ),
    ]
