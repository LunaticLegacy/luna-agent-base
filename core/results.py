from __future__ import annotations

import copy
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
    branch_results: Dict[str, Any] = field(default_factory=dict)

    def clone(self) -> "ExecutionState":
        """Create a detached copy of the execution state."""
        return ExecutionState(
            payload=copy.deepcopy(self.payload),
            rounds=self.rounds,
            metadata=copy.deepcopy(self.metadata),
            trace=[dict(item) for item in self.trace],
            branch_results=copy.deepcopy(self.branch_results),
        )


@dataclass
class GraphValidationResult:
    """Validation result for execution graph availability and completeness."""

    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
