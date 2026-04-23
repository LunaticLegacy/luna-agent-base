from __future__ import annotations

import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class Task:
    """A first-class task entity within a swarm.

    Tasks form a directed acyclic graph via ``dependencies`` and ``next_tasks``,
    and are shared by all agents in the swarm.
    """

    task_id: str
    name: str
    description: str = ""
    status: str = "pending"  # pending | running | success | failed | cancelled
    priority: str = "medium"  # low | medium | high | urgent
    swarm_name: str = ""
    agent_id: Optional[str] = None
    input: Any = None
    output: Any = None
    dependencies: List[str] = field(default_factory=list)  # task_ids that must finish first
    next_tasks: List[str] = field(default_factory=list)    # task_ids that depend on this one
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    executed_count: int = 0
    failed_count: int = 0
    completed_count: int = 0

    def snapshot(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "priority": self.priority,
            "swarm_name": self.swarm_name,
            "agent_id": self.agent_id,
            "input": self.input,
            "output": self.output,
            "dependencies": list(self.dependencies),
            "next_tasks": list(self.next_tasks),
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "executed_count": self.executed_count,
            "failed_count": self.failed_count,
            "completed_count": self.completed_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        return cls(
            task_id=str(data.get("task_id", "")),
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            status=str(data.get("status", "pending")),
            priority=str(data.get("priority", "medium")),
            swarm_name=str(data.get("swarm_name", "")),
            agent_id=data.get("agent_id"),
            input=data.get("input"),
            output=data.get("output"),
            dependencies=list(data.get("dependencies", [])),
            next_tasks=list(data.get("next_tasks", [])),
            metadata=dict(data.get("metadata", {})),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
            executed_count=int(data.get("executed_count", 0)),
            failed_count=int(data.get("failed_count", 0)),
            completed_count=int(data.get("completed_count", 0)),
        )


class TaskGraph:
    """Directed acyclic graph of tasks shared by all agents in a swarm."""

    def __init__(self, graph_id: str = "") -> None:
        self.graph_id = graph_id or f"task_graph_{uuid.uuid4().hex[:8]}"
        self.tasks: Dict[str, Task] = {}

    # ------------------------------------------------------------------ #
    # CRUD
    # ------------------------------------------------------------------ #

    def add_task(self, task: Task) -> Task:
        if not task.task_id:
            task.task_id = f"task-{uuid.uuid4().hex[:8]}"
        if task.task_id in self.tasks:
            raise ValueError(f"Task already exists: {task.task_id}")
        self.tasks[task.task_id] = task
        return task

    def get_task(self, task_id: str) -> Task:
        if task_id not in self.tasks:
            raise KeyError(f"Unknown task: {task_id}")
        return self.tasks[task_id]

    def update_task(self, task_id: str, patch: Dict[str, Any]) -> Task:
        task = self.get_task(task_id)
        allowed = {
            "name",
            "description",
            "status",
            "priority",
            "agent_id",
            "input",
            "output",
            "metadata",
        }
        for key, value in patch.items():
            if key in allowed:
                setattr(task, key, value)
        # Re-hydrate list fields if provided explicitly
        if "dependencies" in patch:
            task.dependencies = list(patch["dependencies"])
        if "next_tasks" in patch:
            task.next_tasks = list(patch["next_tasks"])
        return task

    def remove_task(self, task_id: str) -> Task:
        task = self.tasks.pop(task_id)
        # Clean up references from other tasks
        for other in self.tasks.values():
            if task_id in other.dependencies:
                other.dependencies.remove(task_id)
            if task_id in other.next_tasks:
                other.next_tasks.remove(task_id)
        return task

    def list_tasks(
        self,
        *,
        swarm_name: Optional[str] = None,
        status: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> List[Task]:
        result = list(self.tasks.values())
        if swarm_name:
            result = [t for t in result if t.swarm_name == swarm_name]
        if status:
            result = [t for t in result if t.status == status]
        if agent_id:
            result = [t for t in result if t.agent_id == agent_id]
        return result

    # ------------------------------------------------------------------ #
    # Graph edges
    # ------------------------------------------------------------------ #

    def link_tasks(self, from_task_id: str, to_task_id: str) -> None:
        """Add a dependency edge: ``to`` depends on ``from``."""
        if from_task_id == to_task_id:
            raise ValueError("Self-dependency is not allowed.")
        from_task = self.get_task(from_task_id)
        to_task = self.get_task(to_task_id)
        if to_task_id not in from_task.next_tasks:
            from_task.next_tasks.append(to_task_id)
        if from_task_id not in to_task.dependencies:
            to_task.dependencies.append(from_task_id)
        if self._would_cycle(to_task_id):
            # Rollback
            from_task.next_tasks.remove(to_task_id)
            to_task.dependencies.remove(from_task_id)
            raise ValueError("Adding this dependency would create a cycle.")

    def unlink_tasks(self, from_task_id: str, to_task_id: str) -> None:
        """Remove a dependency edge."""
        from_task = self.get_task(from_task_id)
        to_task = self.get_task(to_task_id)
        if to_task_id in from_task.next_tasks:
            from_task.next_tasks.remove(to_task_id)
        if from_task_id in to_task.dependencies:
            to_task.dependencies.remove(from_task_id)

    # ------------------------------------------------------------------ #
    # DAG utilities
    # ------------------------------------------------------------------ #

    def _would_cycle(self, start_task_id: str) -> bool:
        visited: Set[str] = set()
        stack = [start_task_id]
        while stack:
            current = stack.pop()
            if current in visited:
                return True
            visited.add(current)
            task = self.tasks.get(current)
            if task:
                for dep_id in task.dependencies:
                    stack.append(dep_id)
        return False

    def validate(self) -> List[str]:
        errors: List[str] = []
        for task in self.tasks.values():
            for dep_id in task.dependencies:
                if dep_id not in self.tasks:
                    errors.append(f"Task {task.task_id} references unknown dependency: {dep_id}")
            for next_id in task.next_tasks:
                if next_id not in self.tasks:
                    errors.append(f"Task {task.task_id} references unknown next_task: {next_id}")
        if self._would_cycle(next(iter(self.tasks), "")):
            errors.append("Graph contains a cycle.")
        return errors

    def topological_order(self) -> List[str]:
        """Return task IDs in topological order (ready-first)."""
        in_degree: Dict[str, int] = {tid: 0 for tid in self.tasks}
        for task in self.tasks.values():
            for dep_id in task.dependencies:
                if dep_id in self.tasks:
                    in_degree[task.task_id] += 1
        queue = [tid for tid, deg in in_degree.items() if deg == 0]
        order: List[str] = []
        while queue:
            current = queue.pop(0)
            order.append(current)
            task = self.tasks.get(current)
            if task:
                for next_id in task.next_tasks:
                    if next_id in in_degree:
                        in_degree[next_id] -= 1
                        if in_degree[next_id] == 0:
                            queue.append(next_id)
        if len(order) != len(self.tasks):
            raise ValueError("Task graph contains cycles; cannot produce topological order.")
        return order

    def ready_tasks(self) -> List[Task]:
        """Return tasks whose dependencies are all satisfied (status == success)."""
        ready = []
        for task in self.tasks.values():
            if task.status != "pending":
                continue
            if all(
                self.tasks.get(dep_id, Task(task_id=dep_id)).status == "success"
                for dep_id in task.dependencies
            ):
                ready.append(task)
        return ready

    # ------------------------------------------------------------------ #
    # Serialization
    # ------------------------------------------------------------------ #

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "tasks": {tid: task.snapshot() for tid, task in self.tasks.items()},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskGraph":
        graph = cls(graph_id=str(data.get("graph_id", "")))
        for task_data in data.get("tasks", {}).values():
            graph.tasks[task_data["task_id"]] = Task.from_dict(task_data)
        return graph

    def save(self, path: Any) -> None:
        """Persist the task graph to a JSON file."""
        from pathlib import Path
        import json

        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(p)

    @classmethod
    def load(cls, path: Any) -> "TaskGraph":
        """Load a task graph from a JSON file."""
        from pathlib import Path
        import json

        p = Path(path)
        if not p.exists():
            return cls(graph_id=p.stem)
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return cls.from_dict(data)
        except Exception:
            return cls(graph_id=p.stem)
