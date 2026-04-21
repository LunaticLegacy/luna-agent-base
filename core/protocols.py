from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable

from .results import AgentContextSnapshot


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
