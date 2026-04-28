"""Execution graph lifecycle helpers for a runtime core.

This mixin (:class:`ExecutionGraphStateMixin`) manages the serialisation,
deserialisation, and persistence of the swarm's :class:`ExecutionGraph`.
It stores graph state as JSON under ``runtime_info/graph_state/`` and
supports atomic writes so that crashes never leave a half-written file.

Exports:
    - :class:`ExecutionGraphStateMixin`
    - :func:`_serialize_execution_graph`
    - :func:`_serialize_node`
    - :func:`_serialize_edge`
    - :func:`_deserialize_graph`
    - :func:`_deserialize_node`
    - :func:`_write_json_atomic`
    - :func:`_graph_snapshot`
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING

from ..results import GraphValidationResult
from ..policy import AgentNode, Edge, ExecutionGraph, Node, ToolNode

if TYPE_CHECKING:
    from ..policy import ExecutionGraph


class ExecutionGraphStateMixin:
    """Execution graph lifecycle helpers for a runtime core.

    Expected to be mixed into :class:`Core`.
    """

    def set_execution_graph(self, graph: "ExecutionGraph") -> None:
        """Attach an execution graph, preferring a previously persisted one.

        When a runtime snapshot exists on disk, it is loaded and used instead
        of the freshly built *graph* so that dynamic mutations survive restarts.

        Args:
            graph: The newly constructed execution graph.
        """
        runtime_graph = self.load_runtime_execution_graph()
        self._execution_graph = runtime_graph or graph
        self._record_runtime_change(
            action="set_execution_graph",
            subject_kind="graph",
            subject_id=getattr(self._execution_graph, "graph_name", None),
            detail={
                "entry_node_id": getattr(self._execution_graph, "entry_node_id", None),
                "exit_node_id": getattr(self._execution_graph, "exit_node_id", None),
                "loaded_from_runtime_state": runtime_graph is not None,
            },
        )

    def set_execution_graph_artifacts(self, *, source_path: Path, backup_path: Path) -> None:
        """Record the source and backup paths for the graph module.

        Also initialises the runtime state directory structure.

        Args:
            source_path: Path to the original ``build_graph`` module.
            backup_path: Path to the backup copy.
        """
        self._execution_graph_source_path = Path(source_path)
        self._execution_graph_backup_path = Path(backup_path)
        runtime_root = getattr(self, "_runtime_info_dir", None)
        if runtime_root is None:
            runtime_root = self.workspace_root / "runtime_info"
        runtime_root = Path(runtime_root)
        self._runtime_graph_state_dir = runtime_root / "graph_state"
        self._runtime_graph_revision_dir = self._runtime_graph_state_dir / "revisions"
        self._runtime_graph_current_path = self._runtime_graph_state_dir / "current.json"

    def ensure_execution_graph_backup(self, *, overwrite: bool = False) -> Optional[Path]:
        """Return the backup path (actual copy logic lives elsewhere).

        Args:
            overwrite: Whether to overwrite an existing backup.

        Returns:
            The backup path.
        """
        return self._execution_graph_backup_path

    def persist_execution_graph(
        self,
        *,
        graph: Optional["ExecutionGraph"] = None,
        change: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Atomically persist the graph and its revision history.

        Writes to both ``current.json`` and a timestamped revision file.

        Args:
            graph: Optional graph to persist (defaults to the core's graph).
            change: Optional change metadata for the revision.

        Returns:
            Persistence metadata dict, or ``None`` if paths are not initialised.
        """
        target_graph = graph or self._execution_graph
        current_path = getattr(self, "_runtime_graph_current_path", None)
        revision_dir = getattr(self, "_runtime_graph_revision_dir", None)
        if target_graph is None or current_path is None or revision_dir is None:
            return None

        current_path.parent.mkdir(parents=True, exist_ok=True)
        revision_dir.mkdir(parents=True, exist_ok=True)

        current_revision = 0
        state_getter = getattr(self, "get_graph_runtime_state", None)
        if callable(state_getter):
            try:
                current_revision = int(state_getter().get("revision") or 0)
            except Exception:
                current_revision = 0
        next_revision = current_revision + 1
        payload = self._build_runtime_graph_payload(
            target_graph,
            revision=next_revision,
            change=change or {},
        )

        revision_path = revision_dir / f"graph_state_v{next_revision}.json"
        _write_json_atomic(revision_path, payload)
        _write_json_atomic(current_path, payload)
        return {
            "revision": next_revision,
            "runtime_path": str(current_path),
            "revision_path": str(revision_path),
        }

    def get_execution_graph(self) -> Optional["ExecutionGraph"]:
        """Return the currently attached execution graph, if any."""
        return self._execution_graph

    def load_runtime_execution_graph(self) -> Optional["ExecutionGraph"]:
        """Load the graph from the latest runtime snapshot.

        Returns:
            A deserialised :class:`ExecutionGraph`, or ``None`` if no snapshot
            exists or parsing fails.
        """
        current_path = getattr(self, "_runtime_graph_current_path", None)
        if current_path is None:
            return None
        path = Path(current_path)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        graph_payload = payload.get("graph") if isinstance(payload, dict) else None
        if not isinstance(graph_payload, dict):
            return None
        try:
            return _deserialize_graph(graph_payload)
        except Exception:
            return None

    def get_agent_graph(self) -> Optional["ExecutionGraph"]:
        """Return the agent-only projection of the current graph."""
        graph = self._execution_graph
        if graph is None:
            return None
        return graph.to_agent_graph()

    def get_agent_graph_snapshot(self) -> dict:
        """Return a JSON-serialisable snapshot of the agent-only graph.

        Returns:
            Dictionary with graph metadata and serialised nodes/edges.
        """
        graph = self.get_agent_graph()
        if graph is None:
            return {
                "graph_name": None,
                "graph_kind": "agent",
                "entry_node_id": None,
                "exit_node_id": None,
                "node_count": 0,
                "edge_count": 0,
                "nodes": [],
                "edges": [],
            }
        return _graph_snapshot(graph)

    def check_execution_graph_available(self) -> GraphValidationResult:
        """Validate that the graph is ready for execution.

        Returns:
            A :class:`GraphValidationResult`.
        """
        if self._execution_graph is None:
            return GraphValidationResult(
                is_valid=False,
                errors=["Execution graph is not attached."],
            )
        return self._execution_graph.validate(self)

    def check_execution_graph_complete(self) -> GraphValidationResult:
        """Validate that the graph is fully configured.

        Returns:
            A :class:`GraphValidationResult`.
        """
        if self._execution_graph is None:
            return GraphValidationResult(
                is_valid=False,
                errors=["Execution graph is not attached."],
            )
        return self._execution_graph.validate(self)

    def _build_runtime_graph_payload(
        self,
        graph: "ExecutionGraph",
        *,
        revision: int,
        change: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build the JSON payload for a persisted graph snapshot.

        Args:
            graph: The graph to serialise.
            revision: Monotonic revision number.
            change: Change metadata dict.

        Returns:
            Dictionary ready for JSON serialization.
        """
        return {
            "revision": revision,
            "graph": _serialize_execution_graph(graph),
            "change": dict(change),
        }


def _serialize_execution_graph(graph: ExecutionGraph) -> Dict[str, Any]:
    """Serialise an :class:`ExecutionGraph` to a plain dictionary."""
    return {
        "graph_name": graph.graph_name,
        "graph_kind": getattr(graph, "graph_kind", "execution"),
        "entry_node_id": graph.entry_node_id,
        "exit_node_id": graph.exit_node_id,
        "nodes": [_serialize_node(node) for node in sorted(graph.nodes.values(), key=lambda item: item.node_id)],
        "edges": [_serialize_edge(edge) for edge in graph.edges],
    }


def _serialize_node(node: Node) -> Dict[str, Any]:
    """Serialise a single :class:`Node` to a plain dictionary."""
    payload: Dict[str, Any] = {
        "node_id": node.node_id,
        "node_name": node.node_name,
        "node_type": node.__class__.__name__,
        "next_node_ids": list(node.next_node_ids),
        "metadata": dict(node.metadata),
    }
    if isinstance(node, AgentNode):
        payload.update(
            {
                "blueprint_ref": node.blueprint_ref,
                "additional_prompt": node.additional_prompt,
                "instance_policy": node.instance_policy,
            }
        )
    elif isinstance(node, ToolNode):
        payload.update(
            {
                "tool_name": node.tool_name,
                "input_mapping": dict(node.input_mapping),
            }
        )
    return payload


def _serialize_edge(edge: Edge) -> Dict[str, Any]:
    """Serialise a single :class:`Edge` to a plain dictionary."""
    return {
        "from_node_id": edge.from_node_id,
        "to_node_id": edge.to_node_id,
        "label": edge.label,
        "condition": edge.condition,
        "priority": edge.priority,
    }


def _deserialize_graph(payload: Dict[str, Any]) -> ExecutionGraph:
    """Reconstruct an :class:`ExecutionGraph` from a plain dictionary.

    Args:
        payload: Dictionary previously produced by :func:`_serialize_execution_graph`.

    Returns:
        A fully populated :class:`ExecutionGraph`.
    """
    graph = ExecutionGraph(str(payload.get("graph_name", "")))
    graph.graph_kind = str(payload.get("graph_kind", "execution"))
    for node_payload in payload.get("nodes", []) or []:
        node = _deserialize_node(node_payload)
        graph.add_node(node)
    for edge_payload in payload.get("edges", []) or []:
        if not isinstance(edge_payload, dict):
            continue
        graph.add_edge(
            int(edge_payload["from_node_id"]),
            int(edge_payload["to_node_id"]),
            label=edge_payload.get("label"),
            condition=edge_payload.get("condition"),
            priority=int(edge_payload.get("priority", 0) or 0),
        )
    entry_node_id = payload.get("entry_node_id")
    exit_node_id = payload.get("exit_node_id")
    if entry_node_id is not None:
        graph.set_entry(int(entry_node_id))
    if exit_node_id is not None:
        graph.set_exit(int(exit_node_id))
    return graph


def _deserialize_node(payload: Dict[str, Any]) -> Node:
    """Reconstruct a concrete :class:`Node` subclass from a plain dictionary.

    Args:
        payload: Dictionary previously produced by :func:`_serialize_node`.

    Returns:
        A :class:`Node`, :class:`AgentNode`, or :class:`ToolNode` instance.
    """
    node_type = str(payload.get("node_type", "Node"))
    common_kwargs = {
        "node_id": int(payload["node_id"]),
        "node_name": str(payload.get("node_name", "")),
        "metadata": dict(payload.get("metadata", {}) or {}),
    }
    next_node_ids = [int(item) for item in payload.get("next_node_ids", []) or []]
    if node_type == "AgentNode":
        node = AgentNode(
            **common_kwargs,
            blueprint_ref=str(payload.get("blueprint_ref") or payload.get("agent_id") or ""),
            additional_prompt=payload.get("additional_prompt"),
            instance_policy=str(payload.get("instance_policy", "singleton") or "singleton"),
        )
        node.next_node_ids = next_node_ids
        return node
    if node_type == "ToolNode":
        return ToolNode(
            **common_kwargs,
            next_node_ids=next_node_ids,
            tool_name=str(payload.get("tool_name", "")),
            input_mapping=dict(payload.get("input_mapping", {}) or {}),
        )
    return Node(**common_kwargs, next_node_ids=next_node_ids)


def _write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
    """Write *payload* to *path* atomically via a temporary file.

    This prevents readers from observing a half-written file if the process
    crashes mid-write.

    Args:
        path: Destination path.
        payload: Dictionary to serialise as JSON.
    """
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    tmp_path.replace(path)


def _graph_snapshot(graph: ExecutionGraph) -> Dict[str, Any]:
    """Build a lightweight snapshot of *graph* for API responses.

    Args:
        graph: The graph to snapshot.

    Returns:
        Dictionary with counts, metadata, and sorted node/edge lists.
    """
    return {
        "graph_name": graph.graph_name,
        "graph_kind": getattr(graph, "graph_kind", "execution"),
        "entry_node_id": graph.entry_node_id,
        "exit_node_id": graph.exit_node_id,
        "node_count": len(graph.nodes),
        "edge_count": len(graph.edges),
        "nodes": [_serialize_node(node) for node in sorted(graph.nodes.values(), key=lambda item: item.node_id)],
        "edges": [
            _serialize_edge(edge)
            for edge in sorted(
                graph.edges,
                key=lambda item: (
                    item.from_node_id,
                    item.priority,
                    item.to_node_id,
                    item.label or "",
                    item.condition or "",
                ),
            )
        ],
    }
