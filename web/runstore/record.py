from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

from core.results import ExecutionEvent
from web.utils import to_jsonable

from .serialization import _event_name, _utc_now_iso


@dataclass
class RunRecord:
    """In-memory state for one background graph run."""

    run_id: str
    swarm_name: str
    storage_dir: Optional[Path] = None
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
    _stop_type: Optional[str] = None
    _condition: threading.Condition = field(default_factory=threading.Condition, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.storage_dir is not None:
            self.bind_storage_dir(self.storage_dir)

    @property
    def events_path(self) -> Optional[Path]:
        if self.storage_dir is None:
            return None
        return self.storage_dir / "events.jsonl"

    @property
    def snapshot_path(self) -> Optional[Path]:
        if self.storage_dir is None:
            return None
        return self.storage_dir / "current.json"

    def bind_storage_dir(self, storage_dir: Path) -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def append_event(self, event: ExecutionEvent | Dict[str, Any]) -> Dict[str, Any]:
        """Store one event and update the live snapshot."""
        payload = to_jsonable(event)
        with self._condition:
            self.events.append(payload)
            self._apply_event(payload)
            self._persist_locked(payload)
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

    def stop(self, stop_type: str) -> bool:
        """Request a soft or hard stop for this run.

        The actual stopping is handled by the engine checking the core's stop event.
        This method records the intent and updates status.
        """
        with self._condition:
            if self._done:
                return False
            self._stop_type = stop_type
            if stop_type == "hard":
                self.status = "stopping_hard"
            else:
                self.status = "stopping_soft"
            return True

    def snapshot(self) -> Dict[str, Any]:
        """Return a JSON-ready view of the run."""
        with self._condition:
            events_url = f"/api/runs/{self.run_id}/events"
            status_url = f"/api/runs/{self.run_id}"
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

    def _persist_locked(self, event: Dict[str, Any]) -> None:
        if self.storage_dir is None:
            return
        events_path = self.events_path
        snapshot_path = self.snapshot_path
        if events_path is None or snapshot_path is None:
            return
        events_path.parent.mkdir(parents=True, exist_ok=True)
        with events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
        tmp_path = snapshot_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(self.snapshot(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(snapshot_path)
