"""Shared result and state dataclasses for the Angelus runtime.

These types are used across the execution graph, agent rounds, and tool
scheduler.  They are intentionally lightweight (dataclasses) so that they
can be serialised cheaply for tracing and live streaming.

Exports:
    - :class:`AgentContextSnapshot`
    - :class:`ToolRequest`
    - :class:`ToolResult`
    - :class:`ToolBatchResult`
    - :class:`AgentRoundResult`
    - :class:`NodeExecutionResult`
    - :class:`ExecutionState`
    - :class:`GraphValidationResult`
    - :class:`ExecutionEvent`
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AgentContextSnapshot:
    """Immutable view of one agent's isolated context.

    Attributes:
        messages: Conversation history as a list of ``{"role": ..., "content": ...}`` dicts.
        compressed_blocks: Previously compressed context blocks.
        metadata: Free-form metadata for extensibility.
    """

    messages: List[Dict[str, str]] = field(default_factory=list)
    compressed_blocks: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolRequest:
    """One tool request emitted by an agent in external mode.

    Attributes:
        id: Unique identifier for this request (used for dependency tracking).
        tool: Name of the tool to invoke.
        args: Keyword arguments for the tool.
        depends_on: IDs of other tool requests that must complete first.
        required: Whether failure of this request aborts the batch.
        on_success: Action to take after successful execution.
        on_failure: Action to take after failed execution.
        timeout_ms: Maximum wall-clock time for the tool call.
        resources: Declared resource requirements.
        metadata: Free-form metadata for extensibility.
    """

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
    """Result of executing one tool request.

    Attributes:
        request_id: ID of the corresponding :class:`ToolRequest`.
        tool: Name of the tool that was invoked.
        status: ``"success"`` or ``"failed"``.
        output: Tool-specific return value (if success).
        error: Structured error dict (if failure).
        started_at: ISO-8601 timestamp when execution began.
        finished_at: ISO-8601 timestamp when execution ended.
        duration_ms: Wall-clock duration in milliseconds.
    """

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
    """Aggregated result of executing a batch of tool requests.

    Attributes:
        node_id: Execution-graph node that triggered the batch.
        agent_id: Agent that emitted the requests.
        tool_round: Round counter for this batch.
        results: Ordered list of :class:`ToolResult` objects.
        summary: Free-form summary metadata.
    """

    node_id: Optional[int] = None
    agent_id: Optional[str] = None
    tool_round: int = 0
    results: List[ToolResult] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentRoundResult:
    """Result object returned from one agent round.

    Attributes:
        rounds: The round number.
        user_message: The incoming user message.
        assistant_message: The agent's textual response.
        raw_response: Unparsed raw response from the LLM.
        additional_prompt: Extra prompt text that was appended.
        cognitive_graph_snapshot: Full cognitive graph at the end of the round.
        cognitive_graph_delta: Delta emitted during this round.
        tool_requests: Tool requests emitted in external mode.
        llm_input: Exact payload sent to the LLM (for debugging).
    """

    rounds: int
    user_message: str
    assistant_message: Optional[str] = None
    raw_response: Any = None
    additional_prompt: Optional[str] = None
    cognitive_graph_snapshot: Optional[Dict[str, Any]] = None
    cognitive_graph_delta: Optional[Dict[str, Any]] = None
    tool_requests: Optional[List[ToolRequest]] = None
    llm_input: Optional[Dict[str, Any]] = None


@dataclass
class NodeExecutionResult:
    """Normalized result produced by one graph node.

    Attributes:
        output_payload: Primary output forwarded to the next node.
        routing_payload: Optional payload used for conditional routing.
        state_payload: Mutable state update for the execution state.
        next_node_override: Hard override for the next node ID.
        metadata_patch: Delta to merge into node metadata.
        control_patch: Delta to merge into execution control flags.
    """

    output_payload: Any
    routing_payload: Any
    state_payload: Any
    next_node_override: Optional[int] = None
    metadata_patch: Dict[str, Any] = field(default_factory=dict)
    control_patch: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionState:
    """Mutable state passed through an execution graph.

    The state is cloned at branch points so that each branch receives an
    isolated copy.  A lightweight :meth:`snapshot` method is provided for
    live streaming without copying the full (potentially large) trace.

    Attributes:
        payload: The primary data payload (arbitrary type).
        rounds: Current round counter.
        metadata: Free-form metadata accumulated during execution.
        trace: Ordered list of execution-step records.
        branch_results: Results from completed branches (for join nodes).
    """

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
        """Create a detached copy of the execution state.

        Returns:
            A deep-copied :class:`ExecutionState` safe for branch isolation.
        """
        return ExecutionState(
            payload=copy.deepcopy(self.payload),
            rounds=self.rounds,
            metadata=copy.deepcopy(self.metadata),
            trace=[dict(item) for item in self.trace],
            branch_results=copy.deepcopy(self.branch_results),
        )

    def snapshot(self) -> Dict[str, Any]:
        """Create a lightweight runtime snapshot for tracing and live streaming.

        Trace is omitted from the snapshot to avoid O(n) bloat per event.
        Only a lightweight trace_summary (length + last step hint) is kept.

        Returns:
            Dictionary with summarised payload, metadata, and trace hints.
        """
        trace_summary: Dict[str, Any] = {"length": len(self.trace)}
        if self.trace:
            last = self.trace[-1]
            trace_summary["last_node_id"] = last.get("node_id")
            trace_summary["last_node_name"] = last.get("node_name")
            trace_summary["last_status"] = last.get("status", "ok")
        return {
            "payload": self._summarize_payload(self.payload),
            "rounds": self.rounds,
            "metadata": self._summarize_metadata(self.metadata),
            "trace_summary": trace_summary,
            "branch_results": copy.deepcopy(self.branch_results),
        }

    # ------------------------------------------------------------------
    # Lightweight snapshot helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _summarize_payload(payload: Any) -> Any:
        """Summarise the primary payload for snapshots."""
        return ExecutionState._summarize_value(payload)

    @staticmethod
    def _summarize_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Summarise metadata, recursing into ``outputs`` if present."""
        result = dict(metadata)
        if "outputs" in result and isinstance(result["outputs"], dict):
            result["outputs"] = {
                k: ExecutionState._summarize_value(v) for k, v in result["outputs"].items()
            }
        return result

    @staticmethod
    def _summarize_step(step: Dict[str, Any]) -> Dict[str, Any]:
        """Summarise a single trace-step dict."""
        result = dict(step)
        if "input_payload" in result:
            result["input_payload"] = ExecutionState._summarize_value(result["input_payload"])
        if "output_payload" in result:
            result["output_payload"] = ExecutionState._summarize_value(result["output_payload"])
        return result

    @staticmethod
    def _summarize_value(value: Any) -> Any:
        """Recursively summarise a value to keep snapshots small.

        Strings longer than ``_MAX_STRING_SUMMARY`` are truncated and annotated
        with their original length.  Lists and dicts exceeding item/key limits
        are similarly summarised.
        """
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
    """Validation result for execution graph availability and completeness.

    Attributes:
        is_valid: ``True`` when no blocking errors were found.
        errors: Blocking issues that prevent execution.
        warnings: Non-blocking issues that may affect behaviour.
    """

    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class ExecutionEvent:
    """One live runtime event emitted during graph execution.

    Attributes:
        run_id: Identifier of the current execution run.
        event_type: Dot-namespaced event type (e.g. ``"node.started"``).
        timestamp: Unix epoch timestamp.
        swarm_name: Name of the swarm being executed.
        node_id: Execution-graph node that emitted the event.
        node_name: Human-readable node name.
        node_type: Class name of the node (``"AgentNode"``, ``"ToolNode"``, …).
        branch: Branch label (for parallel branches).
        rounds: Current round counter.
        status: Execution status (``"running"``, ``"completed"``, ``"failed"``).
        data: Event-specific payload dictionary.
    """

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
