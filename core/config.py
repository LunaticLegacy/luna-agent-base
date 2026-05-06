"""Minimal compatibility config objects for the runtime core."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class AgentConfig:
    api_url: str
    api_key: str
    model: str
    provider: str = "openai"
    timeout: float = 60.0
    max_retries: int = 0
    name: Optional[str] = None

