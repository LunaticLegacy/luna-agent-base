"""Global concurrency limiter for the Angelus runtime.

Prevents run-away parallelism on LLM calls, tool calls, and execution-graph
branches by wrapping asyncio semaphores around the three resource classes.
The limiter is created once per :class:`Core` and shared by all agents and
the tool scheduler.

Exports:
    - :class:`ConcurrencyLimiter`
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional


class ConcurrencyLimiter:
    """Global concurrency limiter for LLM calls, tool calls, and branch parallelism.

    Attributes:
        config: Raw configuration dictionary (e.g. from ``config.toml``).
        llm_semaphore: Semaphore controlling concurrent LLM requests.
        tool_semaphore: Semaphore controlling concurrent tool executions.
        max_parallel_branches: Upper bound on parallel branch evaluation.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialise semaphores from *config* or sensible defaults.

        Args:
            config: Optional dictionary with keys:
                ``max_parallel_llm_calls`` (default 5),
                ``max_parallel_tool_calls`` (default 10),
                ``max_parallel_branches`` (default 3).
        """
        self.config = config or {}
        self.llm_semaphore = asyncio.Semaphore(self.config.get("max_parallel_llm_calls", 5))
        self.tool_semaphore = asyncio.Semaphore(self.config.get("max_parallel_tool_calls", 10))
        self.max_parallel_branches = self.config.get("max_parallel_branches", 3)

    async def acquire_llm(self) -> None:
        """Acquire the LLM semaphore (blocks when the limit is reached)."""
        await self.llm_semaphore.acquire()

    def release_llm(self) -> None:
        """Release the LLM semaphore, allowing another pending call to proceed."""
        self.llm_semaphore.release()

    async def acquire_tool(self) -> None:
        """Acquire the tool semaphore (blocks when the limit is reached)."""
        await self.tool_semaphore.acquire()

    def release_tool(self) -> None:
        """Release the tool semaphore, allowing another pending call to proceed."""
        self.tool_semaphore.release()

    def get_branch_batch_size(self, total_branches: int) -> int:
        """Return the number of branches that may run in parallel.

        Args:
            total_branches: Total branches waiting to be evaluated.

        Returns:
            The smaller of *total_branches* and ``max_parallel_branches``.
        """
        return min(total_branches, self.max_parallel_branches)
