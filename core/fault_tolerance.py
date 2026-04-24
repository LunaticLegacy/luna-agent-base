from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .policy import ExecutionGraph

if TYPE_CHECKING:
    from .policy import Node


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class FailureEvent:
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
    timestamp: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
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
            "timestamp": self.timestamp,
        }


@dataclass
class ArchitectureRegulation:
    action: str
    scope: str
    message: str
    applied: bool = False
    quarantined_nodes: List[int] = field(default_factory=list)
    rerouted_from: List[int] = field(default_factory=list)
    rerouted_to: Optional[int] = None
    metadata_patch: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
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
            if fallback_node_id is not None and int(fallback_node_id) in graph.nodes:
                rerouted_to = int(fallback_node_id)
                action = "reroute_to_fallback"
                rerouted_from.append(int(node.node_id))
                metadata_patch["fallback_node_id"] = rerouted_to
                metadata_patch["quarantined"] = True
                metadata_patch["skip_policy"] = "fallback"
                node.metadata["fault_tolerance"] = metadata_patch
            elif normalized_kind in {"tool_error", "timeout", "agent_error"} and retry_budget > 0:
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
    try:
        return int(raw)
    except Exception:
        return default
