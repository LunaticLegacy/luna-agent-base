"""Fault-tolerance regulation for runtime failures.

When a node or branch fails, the ``ArchitectureRegulator`` inspects the
failure classification and node policy to decide whether to retry, reroute
to a fallback, quarantine, or pause the entire run.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .policy import ExecutionGraph

if TYPE_CHECKING:
    from .policy import Node


def _utc_now_iso() -> str:
    """Current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class FailureEvent:
    """Structured record of a runtime failure.

    Attributes:
        event_id: Unique identifier for this failure event.
        run_id: The execution run during which the failure occurred.
        swarm_name: Swarm context, if any.
        graph_revision: Graph revision at the time of failure.
        failure_scope: ``"node"``, ``"branch"``, ``"graph"``, or ``"swarm"``.
        failure_kind: Canonical failure kind string.
        node_id, node_name, node_type: Identity of the failing node, if applicable.
        message: Human-readable error description.
        state_snapshot: Serialisable execution state at failure time.
        recent_changes: Recent mutation records for forensic context.
        branch: Branch index, if the failure occurred inside a branch.
        recoverable, retryable: Flags from the classifier.
        suggested_action: Human-readable remediation hint.
        detail: Arbitrary extra context.
        timestamp: ISO timestamp of the event.
    """

    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    run_id: str = ""
    swarm_name: str = ""
    graph_revision: int = 0
    failure_scope: str = "node"
    failure_kind: str = "unknown"
    node_id: Optional[int] = None
    node_name: Optional[str] = None
    node_type: Optional[str] = None
    message: str = ""
    state_snapshot: Dict[str, Any] = field(default_factory=dict)
    recent_changes: List[Dict[str, Any]] = field(default_factory=list)
    branch: Optional[str] = None
    recoverable: Optional[bool] = None
    retryable: Optional[bool] = None
    suggested_action: Optional[str] = None
    detail: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict for logging and event emission."""
        return {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "swarm_name": self.swarm_name,
            "graph_revision": self.graph_revision,
            "failure_scope": self.failure_scope,
            "failure_kind": self.failure_kind,
            "node_id": self.node_id,
            "node_name": self.node_name,
            "node_type": self.node_type,
            "message": self.message,
            "state_snapshot": self.state_snapshot,
            "recent_changes": list(self.recent_changes),
            "branch": self.branch,
            "recoverable": self.recoverable,
            "retryable": self.retryable,
            "suggested_action": self.suggested_action,
            "detail": dict(self.detail),
            "timestamp": self.timestamp,
        }


@dataclass
class ArchitectureRegulation:
    """Decision produced by the regulator in response to a failure.

    Attributes:
        action: Canonical action such as ``"pause_run"``, ``"retry_node"``,
            ``"reroute_to_fallback"``, ``"degrade_node"``, ``"quarantine_node"``.
        scope: Scope the action applies to.
        message: Human-readable explanation.
        applied: Whether the regulation was actually enacted.
        quarantined_nodes: Node IDs placed in quarantine.
        rerouted_from: Source node IDs for a reroute.
        rerouted_to: Destination node ID for a reroute.
        metadata_patch: Extra metadata written back to the affected node(s).
    """

    action: str
    scope: str
    message: str
    applied: bool = False
    quarantined_nodes: List[int] = field(default_factory=list)
    rerouted_from: List[int] = field(default_factory=list)
    rerouted_to: Optional[int] = None
    metadata_patch: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict for logging and event emission."""
        return {
            "action": self.action,
            "scope": self.scope,
            "message": self.message,
            "applied": self.applied,
            "quarantined_nodes": list(self.quarantined_nodes),
            "rerouted_from": list(self.rerouted_from),
            "rerouted_to": self.rerouted_to,
            "metadata_patch": dict(self.metadata_patch),
        }


class ArchitectureRegulator:
    """Classify failures and adjust the live execution graph in place."""

    def regulate(self, failure: FailureEvent, graph: Optional[ExecutionGraph] = None) -> ArchitectureRegulation:
        """Produce a regulation decision for *failure* within *graph*.

        The decision flow is:
            1. If no graph is attached, pause the run.
            2. Load the node's failure policy (retry budget, fallback node).
            3. Based on failure kind and policy, choose retry, reroute,
               degrade, quarantine, or pause.
        """
        if graph is None:
            return ArchitectureRegulation(
                action="pause_run",
                scope=failure.failure_scope,
                message=failure.message or "No graph attached for regulation.",
            )

        node = graph.nodes.get(int(failure.node_id)) if failure.node_id is not None and int(failure.node_id) in graph.nodes else None
        policy = _node_failure_policy(node)
        failure_count = 0
        fallback_node_id = policy.get("fallback_node_id")
        retry_budget = _safe_int(policy.get("retry_budget"), 0)
        if node is not None:
            fault_state = node.metadata.setdefault("fault_tolerance", {})
            failure_count = int(fault_state.get("failure_count", 0) or 0) + 1
            fault_state["failure_count"] = failure_count
            fault_state["last_failure"] = failure.to_dict()
            fault_state["last_failure_kind"] = failure.failure_kind
            fault_state["last_failure_message"] = failure.message
            fault_state["last_failure_at"] = failure.timestamp
            if fallback_node_id is None and policy.get("fallback_node_id") is not None:
                fallback_node_id = policy.get("fallback_node_id")
            if retry_budget > 0:
                fault_state["retry_budget"] = max(0, retry_budget - 1)

        normalized_kind = str(failure.failure_kind or "").strip().lower()
        normalized_scope = str(failure.failure_scope or "node").strip().lower()
        action = "pause_run"
        message = failure.message or "Failure received."
        quarantined_nodes: List[int] = []
        rerouted_from: List[int] = []
        rerouted_to: Optional[int] = None
        metadata_patch: Dict[str, Any] = {}

        if node is not None:
            metadata_patch = dict(node.metadata.get("fault_tolerance", {}))
            if normalized_kind in {"tool_policy_denied", "tool_argument_error"}:
                action = "degrade_node" if policy.get("allow_toolless_fallback") else "request_tool_rewrite"
                metadata_patch["quarantined"] = False
                metadata_patch["skip_policy"] = "tool_rewrite"
                metadata_patch[normalized_kind] = True
                node.metadata["fault_tolerance"] = metadata_patch
            elif fallback_node_id is not None and int(fallback_node_id) in graph.nodes:
                rerouted_to = int(fallback_node_id)
                action = "reroute_to_fallback"
                rerouted_from.append(int(node.node_id))
                metadata_patch["fallback_node_id"] = rerouted_to
                metadata_patch["quarantined"] = True
                metadata_patch["skip_policy"] = "fallback"
                node.metadata["fault_tolerance"] = metadata_patch
            elif normalized_kind in {"tool_error", "timeout", "agent_error", "runtime_exception"} and retry_budget > 0:
                action = "retry_node"
                metadata_patch["quarantined"] = False
                metadata_patch["skip_policy"] = "retry"
                node.metadata["fault_tolerance"] = metadata_patch
            else:
                action = "quarantine_node"
                metadata_patch["quarantined"] = True
                metadata_patch["skip_policy"] = "advance"
                quarantined_nodes.append(int(node.node_id))
                node.metadata["fault_tolerance"] = metadata_patch

        if normalized_scope in {"graph", "swarm"} or normalized_kind in {"mutation_error", "invariant_violation"}:
            # Scope-wide or structural failures escalate to a full pause.
            action = "pause_run" if action == "retry_node" else action
            message = failure.message or "Graph-level failure detected."
            if node is not None:
                quarantined_nodes.append(int(node.node_id))
                node.metadata.setdefault("fault_tolerance", {})["quarantined"] = True

        regulation = ArchitectureRegulation(
            action=action,
            scope=normalized_scope,
            message=message,
            applied=True,
            quarantined_nodes=sorted(set(quarantined_nodes)),
            rerouted_from=sorted(set(rerouted_from)),
            rerouted_to=rerouted_to,
            metadata_patch=metadata_patch,
        )
        return regulation


def _node_failure_policy(node: Optional["Node"]) -> Dict[str, Any]:
    """Extract the failure policy dict from a node's metadata, if any."""
    if node is None:
        return {}
    metadata = node.metadata if isinstance(node.metadata, dict) else {}
    policy = metadata.get("failure_policy")
    if isinstance(policy, dict):
        return dict(policy)
    if isinstance(policy, str) and policy.strip():
        return {"mode": policy.strip()}
    result: Dict[str, Any] = {}
    for key in ("fallback_node_id", "retry_budget", "mode", "strategy"):
        if key in metadata:
            result[key] = metadata[key]
    return result


def _safe_int(raw: Any, default: int) -> int:
    """Coerce *raw* to int, falling back to *default* on any error."""
    try:
        return int(raw)
    except Exception:
        return default
