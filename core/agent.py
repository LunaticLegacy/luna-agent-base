from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from modules.llm_fetcher import LLMContext, LLMFetcher

from .results import AgentContextSnapshot, AgentRoundResult


@dataclass
class AgentContext:
    """Isolated per-agent context storage."""

    messages: List[Dict[str, str]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class Agent:
    """Runtime agent with isolated context and one LLM backend."""

    def __init__(
        self,
        agent_id: str,
        llm_handler: LLMFetcher,
        character_prompt: str,
        name: Optional[str] = None,
    ) -> None:
        self.agent_id = agent_id
        self.name = name or agent_id
        self.llm_handler = llm_handler
        self.character_prompt = character_prompt
        self._context = AgentContext()

    def append_context(self, role: str, content: str) -> None:
        """Append one message into the agent-local context."""
        self._context.messages.append({"role": role, "content": content})

    def get_context_snapshot(self) -> AgentContextSnapshot:
        """Return a safe snapshot of the agent context."""
        return AgentContextSnapshot(
            messages=[dict(item) for item in self._context.messages],
            metadata=dict(self._context.metadata),
        )

    def reset_context(self) -> None:
        """Clear the isolated agent context."""
        self._context.messages.clear()
        self._context.metadata.clear()

    def _build_system_prompt(self, additional_prompt: Optional[str] = None) -> str:
        prompts = [self.character_prompt.strip()]
        if additional_prompt:
            prompts.append(additional_prompt.strip())
        return "\n\n".join(prompt for prompt in prompts if prompt)

    def _extract_assistant_message(self, response: Any) -> Optional[str]:
        choices = getattr(response, "choices", None)
        if not choices:
            return None
        first_choice = choices[0]
        message = getattr(first_choice, "message", None)
        if message is None and isinstance(first_choice, dict):
            message = first_choice.get("message")
        if message is None:
            return None
        return getattr(message, "content", None) if not isinstance(message, dict) else message.get("content")

    async def round_call(
        self,
        rounds: int,
        user_message: str,
        additional_prompt: Optional[str] = None,
    ) -> AgentRoundResult:
        """Execute one agent round with isolated context."""
        self.append_context("user", user_message)
        system_prompt = self._build_system_prompt(additional_prompt)
        prev_messages = [LLMContext(role=item["role"], content=item["content"]) for item in self._context.messages[:-1]]

        raw_response = self.llm_handler.fetch(
            msg=user_message,
            system_prompt=system_prompt or None,
            prev_messages=prev_messages or None,
        )
        assistant_message = self._extract_assistant_message(raw_response)

        if assistant_message:
            self.append_context("assistant", assistant_message)

        self._context.metadata["last_round"] = rounds
        self._context.metadata["turns"] = len(self._context.messages)

        return AgentRoundResult(
            rounds=rounds,
            user_message=user_message,
            assistant_message=assistant_message,
            raw_response=raw_response,
            additional_prompt=additional_prompt,
        )
