"""Runtime configuration dataclasses.

Defines immutable-ish configuration objects for agent backends,
execution concurrency / retry policies, and the alpha memory graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class AgentConfig:
    """Shared runtime configuration used to construct default agent backends.

    Attributes:
        api_url: Endpoint for the LLM provider.
        api_key: Authentication key for the LLM provider.
        model: Model name (e.g. ``"gpt-4o"``).  Optional so that the provider
            default can be used when omitted.
        provider: Identifier for the LLM SDK wrapper (default ``"openai"``).
    """

    api_url: str
    api_key: str
    model: Optional[str] = None
    provider: str = "openai"


@dataclass
class RuntimeConfig:
    """Runtime concurrency and retry configuration.

    Attributes:
        concurrency: Limits for parallel LLM calls, tool calls, and branches.
        branch_retry: Retry settings including backoff and retry policy name.
    """

    concurrency: Dict[str, Any] = field(default_factory=lambda: {
        "max_parallel_llm_calls": 5,
        "max_parallel_tool_calls": 10,
        "max_parallel_branches": 3,
    })
    branch_retry: Dict[str, Any] = field(default_factory=lambda: {
        "max_retries": 2,
        "backoff_ms": 1000,
        "backoff_multiplier": 2.0,
        "retry_policy": "full_branch",
    })


@dataclass
class MemoryGraphConfig:
    """Angelus Memory Graph alpha module configuration.

    Attributes:
        enabled: Whether the memory runtime is active.
        max_context_nodes: How many episode nodes to surface in a context plan.
        pack_keep_recent: Number of recent turns to preserve during compression.
        enable_usage_trace: Collect per-turn memory usage metrics.
        enable_candidate_memory: Allow candidate (uncommitted) memory items.
    """

    enabled: bool = True
    max_context_nodes: int = 6
    pack_keep_recent: int = 2
    enable_usage_trace: bool = True
    enable_candidate_memory: bool = True
