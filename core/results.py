from __future__ import annotations

import copy
import time
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
    cognitive_graph_snapshot: Optional[Dict[str, Any]] = None
    cognitive_graph_delta: Optional[Dict[str, Any]] = None


@dataclass
class NodeExecutionResult:
    """Normalized result produced by one graph node."""

    output_payload: Any
    routing_payload: Any
    state_payload: Any
    next_node_override: Optional[int] = None
    metadata_patch: Dict[str, Any] = field(default_factory=dict)
    control_patch: Dict[str, Any] = field(default_factory=dict)


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

    @property
    def is_envelope(self) -> bool:
        """True when the state uses the immutable envelope model.

        Envelope mode is auto-detected from the initial payload shape:
        a dict that contains either an ``original_request`` key or the
        ``_envelope`` sentinel.
        """
        return isinstance(self.payload, dict) and (
            "original_request" in self.payload or self.payload.get("_envelope") is True
        )

    def snapshot(self) -> Dict[str, Any]:
        """Create a lightweight runtime snapshot for tracing and live streaming."""
        return {
            "payload": copy.deepcopy(self.payload),
            "rounds": self.rounds,
            "metadata": copy.deepcopy(self.metadata),
            "trace": [dict(item) for item in self.trace],
            "branch_results": copy.deepcopy(self.branch_results),
        }


@dataclass
class GraphValidationResult:
    """Validation result for execution graph availability and completeness."""

    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class ExecutionEvent:
    """One live runtime event emitted during graph execution."""

    run_id: str
    event_type: str
    timestamp: float = field(default_factory=time.time)
    swarm_name: Optional[str] = None
    node_id: Optional[int] = None
    node_name: Optional[str] = None
    node_type: Optional[str] = None
    branch: Optional[str] = None
    rounds: Optional[int] = None
    status: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
