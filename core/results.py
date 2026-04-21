from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


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
