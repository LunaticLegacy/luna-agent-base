from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .policy import AgentNode, Edge, ExecutionGraph, Node, ToolNode


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(item) for item in value]
    return str(value)


@dataclass
class RuntimeInfoManager:
    """Persist live runtime changes for one swarm package."""

    runtime_dir: Path
    agent_name: str
    state_filename: str = "current.json"
    events_filename: str = "events.jsonl"
    graph_events_filename: str = "graph_events.jsonl"
    _counter: int = 0
    last_event: Dict[str, Any] = field(default_factory=dict)
    _graph_revision: int = 0
    _graph_hash: str = ""
    _graph_updated_at: str = ""
    _graph_last_change: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.runtime_dir = self.runtime_dir.resolve()
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self._load_persisted_state()

    @property
    def state_path(self) -> Path:
        return self.runtime_dir / self.state_filename

    @property
    def events_path(self) -> Path:
        return self.runtime_dir / self.events_filename

    @property
    def graph_events_path(self) -> Path:
        return self.runtime_dir / self.graph_events_filename

    def record(
        self,
        *,
        action: str,
        subject_kind: str,
        subject_id: Optional[str] = None,
        detail: Optional[Dict[str, Any]] = None,
        core: Any = None,
    ) -> Dict[str, Any]:
        """Record one runtime change and refresh the latest snapshot."""
        self._counter += 1
        safe_detail = _sanitize_detail(detail or {})
        current_event = {
            "sequence": self._counter,
            "timestamp": _utc_now_iso(),
            "agent_name": self.agent_name,
            "action": action,
            "subject_kind": subject_kind,
            "subject_id": subject_id,
            "detail": safe_detail,
        }
        self.last_event = current_event
        if subject_kind == "graph":
            graph_event = self._build_graph_event(
                action=action,
                subject_kind=subject_kind,
                subject_id=subject_id,
                detail=safe_detail,
                core=core,
                current_event=current_event,
            )
            self._append_graph_event(graph_event)
        snapshot = self._build_snapshot(core=core, current_event=current_event)
        event = {
            **current_event,
            "snapshot": snapshot,
        }
        self._append_event(event)
        self._write_snapshot(event)
        return event

    def _build_snapshot(self, *, core: Any = None, current_event: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        graph_snapshot = self._build_graph_state(core=core)

        return {
            "agent_name": self.agent_name,
            "updated_at": _utc_now_iso(),
            "agents": [
                getattr(agent, "agent_id", str(agent))
                for agent in (core.list_agents() if core is not None else [])
            ],
            "tools": sorted(list(core.tools.keys()) if core is not None else []),
            "skills": sorted([skill.name for skill in core.list_skills()] if core is not None else []),
            "graph": graph_snapshot,
            "last_event": {
                "sequence": (current_event or self.last_event).get("sequence"),
                "action": (current_event or self.last_event).get("action"),
                "subject_kind": (current_event or self.last_event).get("subject_kind"),
                "subject_id": (current_event or self.last_event).get("subject_id"),
            },
            "graph_state": self.get_graph_state(core=core),
        }

    def get_graph_state(self, *, core: Any = None) -> Dict[str, Any]:
        graph_snapshot = self._build_graph_state(core=core)
        graph_snapshot.update(
            {
                "revision": self._graph_revision,
                "hash": self._graph_hash,
                "updated_at": self._graph_updated_at,
                "last_change": self._graph_last_change or None,
            }
        )
        return graph_snapshot

    def get_graph_events(self, *, since_revision: int = 0) -> list[Dict[str, Any]]:
        events = self._load_graph_events()
        return [event for event in events if int(event.get("revision") or 0) > int(since_revision)]

    def get_graph_diff(self, *, since_revision: int, core: Any = None) -> Dict[str, Any]:
        events = self._load_graph_events()
        if not events:
            state = self.get_graph_state(core=core)
            return {
                "base_revision": since_revision,
                "current_revision": self._graph_revision,
                "graph_id": state.get("graph_name"),
                "is_gap_free": True,
                "operations": [],
                "last_change": self._graph_last_change or None,
            }

        current_event = events[-1]
        current_revision = int(current_event.get("revision") or 0)
        if since_revision >= current_revision:
            state = current_event.get("snapshot") or self._build_graph_state(core=core)
            return {
                "base_revision": since_revision,
                "current_revision": current_revision,
                "graph_id": state.get("graph_name"),
                "is_gap_free": True,
                "operations": [],
                "last_change": current_event.get("change") or None,
            }

        base_event = None
        for event in reversed(events):
            if int(event.get("revision") or 0) <= int(since_revision):
                base_event = event
                break

        base_snapshot = base_event.get("snapshot") if base_event is not None else {
            "graph_name": None,
            "entry_node_id": None,
            "exit_node_id": None,
            "node_count": 0,
            "edge_count": 0,
            "nodes": [],
            "edges": [],
        }
        current_snapshot = current_event.get("snapshot") or self._build_graph_state(core=core)
        operations = self._diff_graph_snapshots(base_snapshot, current_snapshot)
        return {
            "base_revision": since_revision,
            "current_revision": current_revision,
            "graph_id": current_snapshot.get("graph_name"),
            "is_gap_free": True,
            "operations": operations,
            "last_change": current_event.get("change") or None,
        }

    def _build_graph_state(self, *, core: Any = None) -> Dict[str, Any]:
        graph = core.get_execution_graph() if core is not None else None
        if graph is None:
            return {
                "graph_name": None,
                "entry_node_id": None,
                "exit_node_id": None,
                "node_count": 0,
                "edge_count": 0,
                "nodes": [],
                "edges": [],
            }
        return self._serialize_graph(graph)

    def _build_graph_event(
        self,
        *,
        action: str,
        subject_kind: str,
        subject_id: Optional[str],
        detail: Dict[str, Any],
        core: Any,
        current_event: Dict[str, Any],
    ) -> Dict[str, Any]:
        graph_snapshot = self._build_graph_state(core=core)
        self._graph_revision += 1
        self._graph_updated_at = current_event["timestamp"]
        self._graph_hash = self._graph_hash_for_snapshot(graph_snapshot)
        self._graph_last_change = {
            "change_id": f"graph-{self._graph_revision:08d}",
            "kind": action,
            "subject": {
                "type": subject_kind,
                "id": subject_id,
            },
            "summary": self._summarize_graph_change(action, detail),
        }
        return {
            "sequence": current_event["sequence"],
            "revision": self._graph_revision,
            "timestamp": current_event["timestamp"],
            "agent_name": self.agent_name,
            "action": action,
            "subject_kind": subject_kind,
            "subject_id": subject_id,
            "detail": detail,
            "change": self._graph_last_change,
            "snapshot": graph_snapshot,
            "graph_hash": self._graph_hash,
        }

    def _append_graph_event(self, event: Dict[str, Any]) -> None:
        with self.graph_events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
            handle.write("\n")

    def _load_persisted_state(self) -> None:
        current_state = self._read_json_file(self.state_path)
        if isinstance(current_state, dict):
            self._counter = int(current_state.get("sequence") or self._counter)
            snapshot = current_state.get("snapshot")
            if isinstance(snapshot, dict):
                graph_state = snapshot.get("graph_state")
                if isinstance(graph_state, dict):
                    self._graph_revision = int(graph_state.get("revision") or self._graph_revision)
                    self._graph_hash = str(graph_state.get("hash") or self._graph_hash)
                    self._graph_updated_at = str(graph_state.get("updated_at") or self._graph_updated_at)
                    last_change = graph_state.get("last_change")
                    if isinstance(last_change, dict):
                        self._graph_last_change = last_change
                elif isinstance(snapshot.get("graph"), dict):
                    graph = snapshot["graph"]
                    self._graph_revision = int(graph.get("revision") or self._graph_revision)
                    self._graph_hash = str(graph.get("hash") or self._graph_hash)
                    self._graph_updated_at = str(graph.get("updated_at") or self._graph_updated_at)
                    last_change = graph.get("last_change")
                    if isinstance(last_change, dict):
                        self._graph_last_change = last_change

        graph_events = self._load_graph_events()
        if graph_events:
            latest = graph_events[-1]
            self._graph_revision = int(latest.get("revision") or self._graph_revision)
            self._graph_hash = str(latest.get("graph_hash") or self._graph_hash)
            self._graph_updated_at = str(latest.get("timestamp") or self._graph_updated_at)
            change = latest.get("change")
            if isinstance(change, dict):
                self._graph_last_change = change

    def _load_graph_events(self) -> list[Dict[str, Any]]:
        events: list[Dict[str, Any]] = []
        if not self.graph_events_path.exists():
            return events
        try:
            lines = self.graph_events_path.read_text(encoding="utf-8").splitlines()
        except Exception:
            return events
        for raw in lines:
            raw = raw.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except Exception:
                continue
            if isinstance(payload, dict):
                events.append(payload)
        events.sort(key=lambda item: int(item.get("revision") or 0))
        return events

    def _read_json_file(self, path: Path) -> Dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    def _serialize_graph(self, graph: ExecutionGraph) -> Dict[str, Any]:
        return {
            "graph_name": graph.graph_name,
            "entry_node_id": graph.entry_node_id,
            "exit_node_id": graph.exit_node_id,
            "node_count": len(graph.nodes),
            "edge_count": len(graph.edges),
            "nodes": [self._serialize_node(node) for node in sorted(graph.nodes.values(), key=lambda item: item.node_id)],
            "edges": [self._serialize_edge(edge) for edge in sorted(
                graph.edges,
                key=lambda item: (item.from_node_id, item.priority, item.to_node_id, item.label or "", item.condition or ""),
            )],
        }

    def _serialize_node(self, node: Node) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "node_id": node.node_id,
            "node_name": node.node_name,
            "node_type": node.__class__.__name__,
            "next_node_ids": list(node.next_node_ids),
            "metadata": _to_jsonable(node.metadata),
        }
        if isinstance(node, AgentNode):
            payload.update(
                {
                    "agent_id": node.agent_id,
                    "additional_prompt": node.additional_prompt,
                }
            )
        elif isinstance(node, ToolNode):
            payload.update(
                {
                    "tool_name": node.tool_name,
                    "input_mapping": _to_jsonable(node.input_mapping),
                }
            )
        return payload

    def _serialize_edge(self, edge: Edge) -> Dict[str, Any]:
        return {
            "from_node_id": edge.from_node_id,
            "to_node_id": edge.to_node_id,
            "label": edge.label,
            "condition": edge.condition,
            "priority": edge.priority,
        }

    def _graph_hash_for_snapshot(self, snapshot: Dict[str, Any]) -> str:
        encoded = json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return f"sha256:{hashlib.sha256(encoded).hexdigest()}"

    def _summarize_graph_change(self, action: str, detail: Dict[str, Any]) -> str:
        if action in {"set_execution_graph"}:
            return "initialized execution graph"
        if action == "graph_add_agent_node":
            return f"added agent node {detail.get('graph_node_id')}"
        if action == "graph_add_tool_node":
            return f"added tool node {detail.get('graph_node_id')}"
        if action == "graph_remove_node":
            node_ids = detail.get("graph_node_ids")
            if isinstance(node_ids, list) and node_ids:
                if len(node_ids) == 1:
                    return f"removed node {node_ids[0]}"
                return f"removed {len(node_ids)} transient nodes"
            return f"removed node {detail.get('graph_node_id')}"
        if action == "graph_replace_next":
            return f"replaced next nodes for {detail.get('graph_from_node_id')}"
        if action == "graph_add_edge":
            return f"added edge {detail.get('graph_from_node_id')} -> {detail.get('graph_to_node_id')}"
        if action == "graph_remove_edge":
            return f"removed edge {detail.get('graph_from_node_id')} -> {detail.get('graph_to_node_id')}"
        if action == "graph_set_entry":
            return f"set entry node to {detail.get('graph_node_id')}"
        if action == "graph_set_exit":
            return f"set exit node to {detail.get('graph_node_id')}"
        return action

    def _diff_graph_snapshots(self, base_snapshot: Dict[str, Any], current_snapshot: Dict[str, Any]) -> list[Dict[str, Any]]:
        base_nodes = {int(node["node_id"]): node for node in base_snapshot.get("nodes", []) if isinstance(node, dict) and "node_id" in node}
        current_nodes = {int(node["node_id"]): node for node in current_snapshot.get("nodes", []) if isinstance(node, dict) and "node_id" in node}
        base_edges = {
            self._edge_key(edge)
            for edge in base_snapshot.get("edges", [])
            if isinstance(edge, dict)
        }
        current_edges = {
            self._edge_key(edge)
            for edge in current_snapshot.get("edges", [])
            if isinstance(edge, dict)
        }

        operations: list[Dict[str, Any]] = []
        for node_id in sorted(current_nodes.keys() - base_nodes.keys()):
            operations.append({"op": "upsert_node", "node": current_nodes[node_id]})
        for node_id in sorted(base_nodes.keys() - current_nodes.keys()):
            operations.append({"op": "remove_node", "node_id": node_id})
        for node_id in sorted(base_nodes.keys() & current_nodes.keys()):
            if base_nodes[node_id] != current_nodes[node_id]:
                operations.append({"op": "upsert_node", "node": current_nodes[node_id]})

        for edge_key in sorted(current_edges - base_edges):
            operations.append({"op": "add_edge", "edge": self._edge_from_key(edge_key)})
        for edge_key in sorted(base_edges - current_edges):
            operations.append({"op": "remove_edge", **self._edge_from_key(edge_key)})

        if base_snapshot.get("entry_node_id") != current_snapshot.get("entry_node_id") or base_snapshot.get("exit_node_id") != current_snapshot.get("exit_node_id"):
            operations.append(
                {
                    "op": "update_graph_meta",
                    "entry_node_id": current_snapshot.get("entry_node_id"),
                    "exit_node_id": current_snapshot.get("exit_node_id"),
                }
            )

        return operations

    def _edge_key(self, edge: Dict[str, Any]) -> tuple[Any, Any, Any, Any, Any]:
        return (
            edge.get("from_node_id"),
            edge.get("to_node_id"),
            edge.get("label"),
            edge.get("condition"),
            edge.get("priority"),
        )

    def _edge_from_key(self, edge_key: tuple[Any, Any, Any, Any, Any]) -> Dict[str, Any]:
        return {
            "from_node_id": edge_key[0],
            "to_node_id": edge_key[1],
            "label": edge_key[2],
            "condition": edge_key[3],
            "priority": edge_key[4],
        }

    def _append_event(self, event: Dict[str, Any]) -> None:
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
            handle.write("\n")

    def _write_snapshot(self, event: Dict[str, Any]) -> None:
        tmp_path = self.state_path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(event, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        tmp_path.replace(self.state_path)


def _sanitize_detail(value: Any, *, max_string_length: int = 500) -> Any:
    if isinstance(value, dict):
        sanitized: Dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key).lower()
            if any(token in normalized_key for token in ("api_key", "token", "secret", "password")):
                sanitized[key] = "[redacted]"
            elif any(token in normalized_key for token in ("prompt", "content")):
                sanitized[key] = _truncate_string(str(item), max_string_length)
            else:
                sanitized[key] = _sanitize_detail(item, max_string_length=max_string_length)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_detail(item, max_string_length=max_string_length) for item in value]
    if isinstance(value, str):
        return _truncate_string(value, max_string_length)
    return value


def _truncate_string(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return f"{value[:max_length].rstrip()}...[truncated]"
