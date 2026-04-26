from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class AgentConfig:
    """Shared runtime configuration used to construct default agent backends."""

    api_url: str
    api_key: str
    model: Optional[str] = None
    provider: str = "openai"


@dataclass
class RuntimeConfig:
    """Runtime concurrency and retry configuration."""

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
