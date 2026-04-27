from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AgentContextSnapshot:
    """Immutable view of one agent's isolated context."""

    messages: List[Dict[str, str]] = field(default_factory=list)
    compressed_blocks: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolRequest:
    """One tool request emitted by an agent in external mode."""

    id: str
    tool: str
    args: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    required: bool = True
    on_success: str = "continue"
    on_failure: str = "return_to_agent"
    timeout_ms: int = 30000
    resources: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    """Result of executing one tool request."""

    request_id: str
    tool: str
    status: str  # "success" | "failed"
    output: Any = None
    error: Optional[Dict[str, Any]] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_ms: int = 0


@dataclass
class ToolBatchResult:
    """Aggregated result of executing a batch of tool requests."""

    node_id: Optional[int] = None
    agent_id: Optional[str] = None
    tool_round: int = 0
    results: List[ToolResult] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)


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
    tool_requests: Optional[List[ToolRequest]] = None


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

    # Summary thresholds for lightweight snapshots
    _MAX_STRING_SUMMARY = 500
    _MAX_PREVIEW = 200
    _MAX_LIST_ITEMS = 10
    _MAX_DICT_KEYS = 50

    def clone(self) -> "ExecutionState":
        """Create a detached copy of the execution state."""
        return ExecutionState(
            payload=copy.deepcopy(self.payload),
            rounds=self.rounds,
            metadata=copy.deepcopy(self.metadata),
            trace=[dict(item) for item in self.trace],
            branch_results=copy.deepcopy(self.branch_results),
        )

    def snapshot(self) -> Dict[str, Any]:
        """Create a lightweight runtime snapshot for tracing and live streaming.

        Large string fields (original_request, raw_input.text, outputs,
        trace payloads) are replaced with summaries to avoid recursive
        payload bloat in events and persistence.
        """
        return {
            "payload": self._summarize_payload(self.payload),
            "rounds": self.rounds,
            "metadata": self._summarize_metadata(self.metadata),
            "trace": [self._summarize_step(s) for s in self.trace],
            "branch_results": copy.deepcopy(self.branch_results),
        }

    # ------------------------------------------------------------------
    # Lightweight snapshot helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _summarize_payload(payload: Any) -> Any:
        return ExecutionState._summarize_value(payload)

    @staticmethod
    def _summarize_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(metadata)
        if "outputs" in result and isinstance(result["outputs"], dict):
            result["outputs"] = {
                k: ExecutionState._summarize_value(v) for k, v in result["outputs"].items()
            }
        return result

    @staticmethod
    def _summarize_step(step: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(step)
        if "input_payload" in result:
            result["input_payload"] = ExecutionState._summarize_value(result["input_payload"])
        if "output_payload" in result:
            result["output_payload"] = ExecutionState._summarize_value(result["output_payload"])
        return result

    @staticmethod
    def _summarize_value(value: Any) -> Any:
        if isinstance(value, str):
            if len(value) > ExecutionState._MAX_STRING_SUMMARY:
                return {
                    "_type": "str",
                    "_length": len(value),
                    "_preview": value[: ExecutionState._MAX_PREVIEW],
                }
            return value
        if isinstance(value, list):
            if len(value) > ExecutionState._MAX_LIST_ITEMS:
                return {
                    "_type": "list",
                    "_length": len(value),
                    "_items": [ExecutionState._summarize_value(v) for v in value[: ExecutionState._MAX_LIST_ITEMS]],
                }
            return [ExecutionState._summarize_value(v) for v in value]
        if isinstance(value, dict):
            if len(value) > ExecutionState._MAX_DICT_KEYS:
                summarized = {
                    k: ExecutionState._summarize_value(v)
                    for k, v in list(value.items())[: ExecutionState._MAX_DICT_KEYS]
                }
                summarized["_truncated_keys"] = len(value) - ExecutionState._MAX_DICT_KEYS
                return summarized
            return {k: ExecutionState._summarize_value(v) for k, v in value.items()}
        return value


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
