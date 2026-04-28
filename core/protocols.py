"""Runtime protocol definitions for the Angelus core.

This module declares the :class:`AgentLike` protocol — the minimal interface
that any runtime agent must satisfy in order to be managed by :class:`Core`.
Protocols allow the core to remain decoupled from concrete agent
implementations while still providing static-type checking.

Exports:
    - :class:`AgentLike`
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable

from .results import AgentContextSnapshot


@runtime_checkable
class AgentLike(Protocol):
    """Protocol for a runtime agent managed by Core.

    Any object registered as an agent must expose at least these attributes
    and methods so that the execution graph and scheduler can interact with
    it uniformly.

    Attributes:
        agent_id: Unique identifier for this agent instance.
        character_prompt: The system-level prompt that defines the agent's persona.
    """

    agent_id: str
    character_prompt: str

    async def round_call(
        self,
        rounds: int,
        user_message: str,
        additional_prompt: Optional[str] = None,
    ) -> Any:
        """Execute one round of dialogue.

        Args:
            rounds: The current round number (0-based or 1-based depending on caller).
            user_message: The incoming user message for this round.
            additional_prompt: Optional extra prompt text to append to the system prompt.

        Returns:
            The raw result of the round (type is agent-specific).
        """
        ...

    def get_context_snapshot(self) -> AgentContextSnapshot:
        """Return an immutable snapshot of the agent's current context.

        Returns:
            A :class:`AgentContextSnapshot` capturing messages and metadata.
        """
        ...

    def reset_context(self) -> None:
        """Clear the agent's conversation context and return to initial state."""
        ...
