from __future__ import annotations

import asyncio
import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, Optional

from core.policy import AgentNode, Edge, ExecutionGraph, Node, ToolNode
from core.results import ExecutionEvent
from web.utils import to_jsonable


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event_name(event: Dict[str, Any]) -> str:
    event_type = str(event.get("event_type") or "message").strip()
    return event_type.replace(" ", ".")


def serialize_node(node: Node) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "node_id": node.node_id,
        "node_name": node.node_name,
        "node_type": node.__class__.__name__,
        "next_node_ids": list(node.next_node_ids),
        "metadata": to_jsonable(node.metadata),
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
                "input_mapping": to_jsonable(node.input_mapping),
            }
        )
    return payload


def serialize_edge(edge: Edge) -> Dict[str, Any]:
    return {
        "from_node_id": edge.from_node_id,
        "to_node_id": edge.to_node_id,
        "label": edge.label,
        "condition": edge.condition,
        "priority": edge.priority,
    }


def serialize_graph_snapshot(graph: ExecutionGraph) -> Dict[str, Any]:
    return {
        "graph_name": graph.graph_name,
        "entry_node_id": graph.entry_node_id,
        "exit_node_id": graph.exit_node_id,
        "node_count": len(graph.nodes),
        "edge_count": len(graph.edges),
        "nodes": [serialize_node(node) for node in sorted(graph.nodes.values(), key=lambda item: item.node_id)],
        "edges": [serialize_edge(edge) for edge in sorted(
            graph.edges,
            key=lambda item: (item.from_node_id, item.priority, item.to_node_id, item.label or "", item.condition or ""),
        )],
    }


def serialize_swarm_summary(swarm) -> Dict[str, Any]:
    """Create a compact summary for one loaded swarm."""
    validation = swarm.core.check_execution_graph_available()
    return {
        "swarm_name": swarm.manifest.swarm_name,
        "package_path": str(swarm.package_path),
        "manifest_path": str(swarm.manifest_path),
        "graph_file": swarm.manifest.graph_file,
        "agent_count": len(swarm.core.list_agents()),
        "skill_count": len(swarm.core.list_skills()),
        "tool_count": len(swarm.core.tools),
        "graph_attached": swarm.core.get_execution_graph() is not None,
        "graph_valid": validation.is_valid,
        "graph_errors": validation.errors,
        "graph_warnings": validation.warnings,
    }


def serialize_swarm_detail(swarm) -> Dict[str, Any]:
    """Create a detailed view for one loaded swarm."""
    payload = serialize_swarm_summary(swarm)
    payload["agent_files"] = list(swarm.manifest.agent_files)
    payload["graph"] = (
        serialize_graph_snapshot(swarm.core.get_execution_graph())
        if swarm.core.get_execution_graph() is not None
        else None
    )
    return payload


@dataclass
class RunRecord:
    """In-memory state for one background graph run."""

    run_id: str
    swarm_name: str
    status: str = "queued"
    created_at: str = field(default_factory=_utc_now_iso)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    rounds: int = 0
    current_node_id: Optional[int] = None
    current_node_name: Optional[str] = None
    current_node_type: Optional[str] = None
    current_state: Dict[str, Any] = field(default_factory=dict)
    final_state: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    events: list[Dict[str, Any]] = field(default_factory=list)
    _done: bool = False
    _condition: threading.Condition = field(default_factory=threading.Condition, repr=False, compare=False)

    def append_event(self, event: ExecutionEvent | Dict[str, Any]) -> Dict[str, Any]:
        """Store one event and update the live snapshot."""
        payload = to_jsonable(event)
        with self._condition:
            self.events.append(payload)
            self._apply_event(payload)
            self._condition.notify_all()
        return payload

    def _apply_event(self, event: Dict[str, Any]) -> None:
        event_type = str(event.get("event_type") or "").strip()
        timestamp = event.get("timestamp")
        data = event.get("data") if isinstance(event.get("data"), dict) else {}

        if event.get("rounds") is not None:
            try:
                self.rounds = int(event["rounds"])
            except Exception:
                pass

        if event_type == "run.started":
            self.status = "running"
            self.started_at = self.started_at or _utc_now_iso()
            if data.get("state_snapshot") is not None:
                self.current_state = to_jsonable(data["state_snapshot"])
        elif event_type == "run.completed":
            self.status = "completed"
            self.finished_at = self.finished_at or _utc_now_iso()
            if data.get("state_snapshot") is not None:
                self.final_state = to_jsonable(data["state_snapshot"])
                self.current_state = dict(self.final_state)
            self._done = True
        elif event_type == "run.failed":
            self.status = "failed"
            self.finished_at = self.finished_at or _utc_now_iso()
            self.error = str(data.get("error") or event.get("error") or "run failed")
            if data.get("state_snapshot") is not None:
                self.current_state = to_jsonable(data["state_snapshot"])
            self._done = True
        else:
            node_id = event.get("node_id")
            if node_id is not None:
                try:
                    self.current_node_id = int(node_id)
                except Exception:
                    self.current_node_id = None
            self.current_node_name = event.get("node_name") or self.current_node_name
            self.current_node_type = event.get("node_type") or self.current_node_type
            if data.get("state_snapshot") is not None:
                self.current_state = to_jsonable(data["state_snapshot"])
            if event_type == "node.failed":
                self.error = str(data.get("error") or event.get("error") or "node failed")

        if timestamp is not None and self.started_at is None and event_type in {"run.started", "node.started"}:
            self.started_at = _utc_now_iso()

    def snapshot(self) -> Dict[str, Any]:
        """Return a JSON-ready view of the run."""
        with self._condition:
            events_url = f"/api/swarms/runs/{self.run_id}/events"
            status_url = f"/api/swarms/runs/{self.run_id}"
            return {
                "success": self.status == "completed",
                "run_id": self.run_id,
                "swarm": self.swarm_name,
                "status": self.status,
                "created_at": self.created_at,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "rounds": self.rounds,
                "current_node_id": self.current_node_id,
                "current_node_name": self.current_node_name,
                "current_node_type": self.current_node_type,
                "state": to_jsonable(self.current_state),
                "final_state": to_jsonable(self.final_state),
                "error": self.error,
                "event_count": len(self.events),
                "events_url": events_url,
                "status_url": status_url,
            }

    def stream_events(self, *, after: int = 0, heartbeat_seconds: float = 15.0) -> Iterator[str]:
        """Yield SSE frames for the run."""
        index = max(after, 0)
        while True:
            frames: list[str] = []
            needs_keepalive = False
            with self._condition:
                while index >= len(self.events) and not self._done:
                    self._condition.wait(timeout=heartbeat_seconds)
                    if index >= len(self.events) and not self._done:
                        needs_keepalive = True
                        break
                while index < len(self.events):
                    event = self.events[index]
                    index += 1
                    frames.append(f"event: {_event_name(event)}\n")
                    frames.append(f"data: {json.dumps(to_jsonable(event), ensure_ascii=False)}\n\n")
                done = self._done and index >= len(self.events)
            if needs_keepalive:
                yield ": keepalive\n\n"
                continue
            for frame in frames:
                yield frame
            if done:
                    break


class RunRegistry:
    """Thread-safe registry for background graph runs."""

    def __init__(self) -> None:
        self._runs: Dict[str, RunRecord] = {}
        self._lock = threading.RLock()

    def launch_run(
        self,
        *,
        swarm_name: str,
        core,
        graph: ExecutionGraph,
        initial_payload: Any,
        rounds: int = 0,
        meta_mode: bool = False,
    ) -> RunRecord:
        """Create a run record and execute the graph in a daemon thread."""
        run_id = uuid.uuid4().hex
        record = RunRecord(run_id=run_id, swarm_name=swarm_name, rounds=rounds)
        with self._lock:
            self._runs[run_id] = record

        thread = threading.Thread(
            target=self._worker,
            kwargs={
                "record": record,
                "swarm_name": swarm_name,
                "core": core,
                "graph": graph,
                "initial_payload": initial_payload,
                "rounds": rounds,
                "meta_mode": meta_mode,
            },
            daemon=True,
            name=f"angelus-run-{run_id[:8]}",
        )
        thread.start()
        return record

    def get_run(self, run_id: str) -> Optional[RunRecord]:
        """Return a run record by id, if present."""
        with self._lock:
            return self._runs.get(run_id)

    def list_runs(self, swarm_name: Optional[str] = None) -> List[RunRecord]:
        """Return run records in insertion order, optionally filtered by swarm."""
        with self._lock:
            runs = list(self._runs.values())
        if swarm_name is None:
            return runs
        return [record for record in runs if record.swarm_name == swarm_name]

    def snapshot(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Return the JSON-ready snapshot for one run."""
        record = self.get_run(run_id)
        if record is None:
            return None
        return record.snapshot()

    def active_run_count(self, swarm_name: Optional[str] = None) -> int:
        """Return the number of active runs, optionally filtered by swarm."""
        with self._lock:
            return sum(
                1
                for record in self._runs.values()
                if not record._done and (swarm_name is None or record.swarm_name == swarm_name)
            )

    def active_run_ids(self, swarm_name: Optional[str] = None) -> List[str]:
        """Return active run ids, optionally filtered by swarm."""
        with self._lock:
            return [
                record.run_id
                for record in self._runs.values()
                if not record._done and (swarm_name is None or record.swarm_name == swarm_name)
            ]

    def _worker(
        self,
        *,
        record: RunRecord,
        swarm_name: str,
        core,
        graph: ExecutionGraph,
        initial_payload: Any,
        rounds: int,
        meta_mode: bool = False,
    ) -> None:
        async def _execute() -> None:
            if meta_mode:
                from core.meta_executor import MetaExecutor
                meta = MetaExecutor(max_iterations=5)
                await meta.run(
                    graph,
                    core,
                    initial_payload,
                    rounds=rounds,
                    run_id=record.run_id,
                    swarm_name=swarm_name,
                    event_sink=record.append_event,
                )
            else:
                await graph.run(
                    core,
                    initial_payload,
                    rounds=rounds,
                    run_id=record.run_id,
                    swarm_name=swarm_name,
                    event_sink=record.append_event,
                )

        try:
            asyncio.run(_execute())
        except Exception as exc:
            if not record._done:
                record.append_event(
                    ExecutionEvent(
                        run_id=record.run_id,
                        swarm_name=swarm_name,
                        event_type="run.failed",
                        rounds=record.rounds,
                        status="failed",
                        data={
                            "error": str(exc),
                            "state_snapshot": record.current_state,
                        },
                    )
                )


def stream_run_events(record: RunRecord, *, after: int = 0) -> Iterator[str]:
    """Create an SSE stream for one run record."""
    yield f"event: run.snapshot\n"
    yield f"data: {json.dumps(record.snapshot(), ensure_ascii=False)}\n\n"
    yield from record.stream_events(after=after)
