from __future__ import annotations

import json
import threading
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.task_graph import Task, TaskGraph


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)


@dataclass
class TaskStore:
    """Persistent store for task graphs, one per swarm."""

    data_dir: Path
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)
    _graphs: Dict[str, TaskGraph] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        self.data_dir = Path(self.data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._load_all()

    @classmethod
    def from_runtime_registry(cls, data_dir: Path, runtime_registry: Any) -> "TaskStore":
        return cls(data_dir=Path(data_dir))

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #

    def _graph_path(self, swarm_name: str) -> Path:
        return self.data_dir / f"tasks_{swarm_name}.json"

    def _load_all(self) -> None:
        for path in self.data_dir.glob("tasks_*.json"):
            swarm_name = path.stem[len("tasks_"):]
            raw = _read_json(path)
            if raw and raw.get("tasks"):
                self._graphs[swarm_name] = TaskGraph.from_dict(raw)

    def _persist(self, swarm_name: str) -> None:
        graph = self._graphs.get(swarm_name)
        if graph is not None:
            _write_json(self._graph_path(swarm_name), graph.to_dict())

    # ------------------------------------------------------------------ #
    # Graph-level
    # ------------------------------------------------------------------ #

    def get_graph(self, swarm_name: str) -> TaskGraph:
        with self._lock:
            if swarm_name not in self._graphs:
                self._graphs[swarm_name] = TaskGraph(graph_id=f"tasks_{swarm_name}")
            return self._graphs[swarm_name]

    def delete_graph(self, swarm_name: str) -> bool:
        with self._lock:
            if swarm_name in self._graphs:
                del self._graphs[swarm_name]
            path = self._graph_path(swarm_name)
            if path.exists():
                path.unlink()
                return True
            return False

    def get_graph_snapshot(self, swarm_name: str) -> Dict[str, Any]:
        with self._lock:
            graph = self.get_graph(swarm_name)
            return graph.snapshot()

    # ------------------------------------------------------------------ #
    # Task CRUD
    # ------------------------------------------------------------------ #

    def create_task(self, swarm_name: str, payload: Dict[str, Any]) -> Task:
        with self._lock:
            graph = self.get_graph(swarm_name)
            now = _utc_now_iso()
            task = Task(
                task_id=str(payload.get("task_id", "") or f"task-{uuid.uuid4().hex[:8]}"),
                name=str(payload.get("name", "")),
                description=str(payload.get("description", "")),
                status=str(payload.get("status", "pending")),
                priority=str(payload.get("priority", "medium")),
                swarm_name=swarm_name,
                agent_id=payload.get("agent_id"),
                input=payload.get("input"),
                output=payload.get("output"),
                dependencies=list(payload.get("dependencies", [])),
                next_tasks=list(payload.get("next_tasks", [])),
                metadata=dict(payload.get("metadata", {})),
                created_at=now,
                updated_at=now,
            )
            graph.add_task(task)
            self._persist(swarm_name)
            return deepcopy(task)

    def get_task(self, swarm_name: str, task_id: str) -> Task:
        with self._lock:
            graph = self.get_graph(swarm_name)
            task = graph.get_task(task_id)
            return deepcopy(task)

    def update_task(self, swarm_name: str, task_id: str, payload: Dict[str, Any]) -> Task:
        with self._lock:
            graph = self.get_graph(swarm_name)
            task = graph.update_task(task_id, payload)
            task.updated_at = _utc_now_iso()
            self._persist(swarm_name)
            return deepcopy(task)

    def transition_task(self, swarm_name: str, task_id: str, payload: Dict[str, Any]) -> Task:
        with self._lock:
            graph = self.get_graph(swarm_name)
            task = graph.transition_task(
                task_id,
                status=payload.get("status"),
                agent_id=payload.get("agent_id"),
                input=payload.get("input"),
                output=payload.get("output"),
                metadata=dict(payload.get("metadata", {}) or {}),
            )
            task.updated_at = _utc_now_iso()
            self._persist(swarm_name)
            return deepcopy(task)

    def claim_ready_tasks(self, swarm_name: str, *, agent_id: Optional[str] = None, limit: Optional[int] = None) -> List[Task]:
        with self._lock:
            graph = self.get_graph(swarm_name)
            ready = graph.ready_tasks()
            if agent_id is not None:
                ready = [task for task in ready if task.agent_id in (None, "", agent_id)]
            if limit is not None:
                ready = ready[: max(0, int(limit))]
            claimed: List[Task] = []
            for task in ready:
                updated = graph.transition_task(
                    task.task_id,
                    status="running",
                    agent_id=agent_id or task.agent_id,
                )
                updated.updated_at = _utc_now_iso()
                claimed.append(deepcopy(updated))
            if claimed:
                self._persist(swarm_name)
            return claimed

    def delete_task(self, swarm_name: str, task_id: str) -> Task:
        with self._lock:
            graph = self.get_graph(swarm_name)
            task = graph.remove_task(task_id)
            self._persist(swarm_name)
            return deepcopy(task)

    def list_tasks(
        self,
        swarm_name: Optional[str] = None,
        status: Optional[str] = None,
        agent_id: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> Dict[str, Any]:
        with self._lock:
            all_tasks: List[Task] = []
            if swarm_name:
                all_tasks = self.get_graph(swarm_name).list_tasks(
                    swarm_name=swarm_name, status=status, agent_id=agent_id
                )
            else:
                for graph in self._graphs.values():
                    all_tasks.extend(graph.list_tasks(status=status, agent_id=agent_id))

            total = len(all_tasks)
            page = max(1, int(page or 1))
            limit = max(1, int(limit or 20))
            start = (page - 1) * limit
            page_items = all_tasks[start : start + limit]

            stats = {
                "pending": sum(1 for t in all_tasks if t.status == "pending"),
                "running": sum(1 for t in all_tasks if t.status == "running"),
                "success": sum(1 for t in all_tasks if t.status == "success"),
                "failed": sum(1 for t in all_tasks if t.status == "failed"),
                "cancelled": sum(1 for t in all_tasks if t.status == "cancelled"),
                "avg_duration_ms": 0,  # placeholder
            }

            return {
                "total": total,
                "page": page,
                "limit": limit,
                "items": [t.snapshot() for t in page_items],
                "stats": stats,
            }

    def link_tasks(self, swarm_name: str, from_task_id: str, to_task_id: str) -> None:
        with self._lock:
            graph = self.get_graph(swarm_name)
            graph.link_tasks(from_task_id, to_task_id)
            self._persist(swarm_name)

    def unlink_tasks(self, swarm_name: str, from_task_id: str, to_task_id: str) -> None:
        with self._lock:
            graph = self.get_graph(swarm_name)
            graph.unlink_tasks(from_task_id, to_task_id)
            self._persist(swarm_name)
