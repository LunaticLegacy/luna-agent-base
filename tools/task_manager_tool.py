from __future__ import annotations

import json
from typing import Any, Dict, Optional

from core.task_graph import Task, TaskGraph
from core.toodefl import ToolContext, ToolDefinition


class TaskManagerTool(ToolDefinition):
    """Tool for agents to create, update, delete and link tasks in the shared TaskGraph.

    This enables agents to collaboratively build and modify the swarm-level task DAG
    at runtime.
    """

    tool_name = "task_manager"
    description = (
        "Manage tasks in the shared swarm task graph. "
        "Supports: create_task, update_task, delete_task, link_tasks, unlink_tasks, list_tasks, get_task."
    )

    def get_openai_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.tool_name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": [
                                "create_task",
                                "update_task",
                                "delete_task",
                                "link_tasks",
                                "unlink_tasks",
                                "list_tasks",
                                "get_task",
                            ],
                            "description": "The operation to perform on the task graph.",
                        },
                        "task_id": {
                            "type": "string",
                            "description": "Required for update, delete, get, link, unlink.",
                        },
                        "name": {
                            "type": "string",
                            "description": "Task name. Required for create_task.",
                        },
                        "description": {
                            "type": "string",
                            "description": "Optional task description.",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["pending", "running", "success", "failed", "cancelled"],
                            "description": "Task status.",
                        },
                        "priority": {
                            "type": "string",
                            "enum": ["low", "medium", "high", "urgent"],
                            "description": "Task priority.",
                        },
                        "agent_id": {
                            "type": "string",
                            "description": "Agent responsible for this task.",
                        },
                        "input": {
                            "type": "object",
                            "description": "Optional input payload for the task.",
                        },
                        "output": {
                            "type": "object",
                            "description": "Optional output payload for the task.",
                        },
                        "dependencies": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of task_ids this task depends on.",
                        },
                        "next_tasks": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of task_ids that depend on this task.",
                        },
                        "to_task_id": {
                            "type": "string",
                            "description": "Target task_id for link/unlink operations.",
                        },
                        "metadata": {
                            "type": "object",
                            "description": "Optional metadata dictionary.",
                        },
                    },
                    "required": ["action"],
                },
            },
        }

    def validate(self, arguments: Dict[str, Any], context: ToolContext) -> None:
        action = str(arguments.get("action", "")).strip()
        if not action:
            raise ValueError("Missing required 'action' parameter.")
        valid_actions = {
            "create_task",
            "update_task",
            "delete_task",
            "link_tasks",
            "unlink_tasks",
            "list_tasks",
            "get_task",
        }
        if action not in valid_actions:
            raise ValueError(f"Invalid action: {action}. Must be one of {valid_actions}.")

    async def execute(self, arguments: Dict[str, Any], context: ToolContext) -> str:
        self.validate(arguments, context)
        action = str(arguments.get("action", "")).strip()

        core = context.core
        if core is None:
            return json.dumps({"error": "No core reference available."}, ensure_ascii=False)

        task_graph: Optional[TaskGraph] = core.get_task_graph()
        if task_graph is None:
            return json.dumps({"error": "No task graph attached to this swarm."}, ensure_ascii=False)

        try:
            result = ""
            if action == "create_task":
                result = self._create_task(arguments, task_graph)
            elif action == "update_task":
                result = self._update_task(arguments, task_graph)
            elif action == "delete_task":
                result = self._delete_task(arguments, task_graph)
            elif action == "link_tasks":
                result = self._link_tasks(arguments, task_graph)
            elif action == "unlink_tasks":
                result = self._unlink_tasks(arguments, task_graph)
            elif action == "list_tasks":
                result = self._list_tasks(arguments, task_graph)
            elif action == "get_task":
                result = self._get_task(arguments, task_graph)
            else:
                return json.dumps({"error": "Unhandled action."}, ensure_ascii=False)
            core.persist_task_graph()
            return result
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

    def _create_task(self, arguments: Dict[str, Any], task_graph: TaskGraph) -> str:
        name = str(arguments.get("name", "")).strip()
        if not name:
            raise ValueError("'name' is required for create_task.")
        task = Task(
            task_id="",
            name=name,
            description=str(arguments.get("description", "")),
            status=str(arguments.get("status", "pending")),
            priority=str(arguments.get("priority", "medium")),
            agent_id=arguments.get("agent_id"),
            input=arguments.get("input"),
            output=arguments.get("output"),
            dependencies=list(arguments.get("dependencies", [])),
            next_tasks=list(arguments.get("next_tasks", [])),
            metadata=dict(arguments.get("metadata", {})),
        )
        task_graph.add_task(task)
        return json.dumps({"success": True, "task": task.snapshot()}, ensure_ascii=False)

    def _update_task(self, arguments: Dict[str, Any], task_graph: TaskGraph) -> str:
        task_id = str(arguments.get("task_id", "")).strip()
        patch = {k: v for k, v in arguments.items() if k not in {"action", "task_id"}}
        task = task_graph.update_task(task_id, patch)
        return json.dumps({"success": True, "task": task.snapshot()}, ensure_ascii=False)

    def _delete_task(self, arguments: Dict[str, Any], task_graph: TaskGraph) -> str:
        task_id = str(arguments.get("task_id", "")).strip()
        task = task_graph.remove_task(task_id)
        return json.dumps({"success": True, "deleted_task_id": task.task_id}, ensure_ascii=False)

    def _link_tasks(self, arguments: Dict[str, Any], task_graph: TaskGraph) -> str:
        from_id = str(arguments.get("task_id", "")).strip()
        to_id = str(arguments.get("to_task_id", "")).strip()
        task_graph.link_tasks(from_id, to_id)
        return json.dumps({"success": True, "from_task_id": from_id, "to_task_id": to_id}, ensure_ascii=False)

    def _unlink_tasks(self, arguments: Dict[str, Any], task_graph: TaskGraph) -> str:
        from_id = str(arguments.get("task_id", "")).strip()
        to_id = str(arguments.get("to_task_id", "")).strip()
        task_graph.unlink_tasks(from_id, to_id)
        return json.dumps({"success": True, "from_task_id": from_id, "to_task_id": to_id}, ensure_ascii=False)

    def _list_tasks(self, arguments: Dict[str, Any], task_graph: TaskGraph) -> str:
        status = arguments.get("status")
        agent_id = arguments.get("agent_id")
        tasks = task_graph.list_tasks(
            status=str(status) if status else None,
            agent_id=str(agent_id) if agent_id else None,
        )
        return json.dumps(
            {"success": True, "count": len(tasks), "tasks": [t.snapshot() for t in tasks]},
            ensure_ascii=False,
        )

    def _get_task(self, arguments: Dict[str, Any], task_graph: TaskGraph) -> str:
        task_id = str(arguments.get("task_id", "")).strip()
        task = task_graph.get_task(task_id)
        return json.dumps({"success": True, "task": task.snapshot()}, ensure_ascii=False)
