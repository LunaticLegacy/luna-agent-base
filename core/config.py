from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class AgentConfig:
    """Shared runtime configuration used to construct default agent backends."""

    api_url: str
    api_key: str
    model: Optional[str] = None
    provider: str = "openai"
