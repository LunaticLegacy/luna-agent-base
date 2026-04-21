from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@dataclass
class AgentConfig:
    """Shared runtime configuration used to construct default agent backends."""

    api_url: str
    api_key: str
    model: Optional[str] = None
    provider: str = "openai"


@dataclass
class AgentContextSnapshot:
    """Immutable view of one agent's isolated context."""

    messages: List[Dict[str, str]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentRoundResult:
    """Result object returned from one agent round."""

    rounds: int
    user_message: str
    assistant_message: Optional[str] = None
    raw_response: Any = None
    additional_prompt: Optional[str] = None


@dataclass
class ExecutionState:
    """Mutable state passed through an execution graph."""

    payload: Any
    rounds: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    trace: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class GraphValidationResult:
    """Validation result for execution graph availability and completeness."""

    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@runtime_checkable
class AgentLike(Protocol):
    """Protocol for a runtime agent managed by Core."""

    agent_id: str
    character_prompt: str

    async def round_call(
        self,
        rounds: int,
        user_message: str,
        additional_prompt: Optional[str] = None,
    ) -> Any:
        ...

    def get_context_snapshot(self) -> AgentContextSnapshot:
        ...

    def reset_context(self) -> None:
        ...
