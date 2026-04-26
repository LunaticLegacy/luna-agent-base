from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional


class ConcurrencyLimiter:
    """Global concurrency limiter for LLM calls, tool calls, and branch parallelism."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {}
        self.llm_semaphore = asyncio.Semaphore(self.config.get("max_parallel_llm_calls", 5))
        self.tool_semaphore = asyncio.Semaphore(self.config.get("max_parallel_tool_calls", 10))
        self.max_parallel_branches = self.config.get("max_parallel_branches", 3)

    async def acquire_llm(self) -> None:
        await self.llm_semaphore.acquire()

    def release_llm(self) -> None:
        self.llm_semaphore.release()

    async def acquire_tool(self) -> None:
        await self.tool_semaphore.acquire()

    def release_tool(self) -> None:
        self.tool_semaphore.release()

    def get_branch_batch_size(self, total_branches: int) -> int:
        return min(total_branches, self.max_parallel_branches)
