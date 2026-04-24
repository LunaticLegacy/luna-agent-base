from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from core import AgentNode, ExecutionGraph, Node, ToolNode
from core.toodefl import ToolContext, ToolDefinition, require_tool_capability


class GraphEditorTool(ToolDefinition):
    """Edit the live execution graph during runtime."""

    def __init__(self) -> None:
        super().__init__(
            tool_name="graph_editor",
            description="Modify the live execution graph.",
        )

    async def execute(
        self,
        arguments: Dict[str, Any],
        *,
        context: Optional[ToolContext] = None,
    ) -> Any:
        require_tool_capability(context, "graph_mutation", self.tool_name)
        if context is None or context.graph is None:
            raise ValueError("graph_editor requires a runtime graph context.")

        graph = context.graph
        if not isinstance(graph, ExecutionGraph):
            raise ValueError("graph_editor received an invalid graph object.")

        normalized = self._normalize_arguments(arguments)
        action = str(normalized.get("action", "")).strip()
        if not action:
            raise ValueError("graph_editor requires an 'action'.")

        content_passthrough = self._extract_content_passthrough(normalized)
        runtime_metadata = dict(context.metadata or {})
        control_source = self._resolve_control_source(normalized, runtime_metadata)
        metadata_patch: Dict[str, Any] = {
            "graph_action": action,
            "graph_name": graph.graph_name,
        }

        if action == "add_agent_node":
            node_id = int(self._pick_value(control_source, runtime_metadata, "node_id"))
            node_name = str(self._pick_value(control_source, runtime_metadata, "node_name"))
            agent_id = str(self._pick_value(control_source, runtime_metadata, "agent_id"))
            additional_prompt = self._pick_optional_value(
                control_source,
                runtime_metadata,
                "additional_prompt",
            )
            lifecycle = self._resolve_node_lifecycle(control_source, runtime_metadata, default_transient=True)
            next_node_ids = self._coerce_node_id_list(
                self._pick_optional_value(control_source, runtime_metadata, "next_node_ids") or []
            )
            replace_existing = bool(
                self._pick_optional_value(control_source, runtime_metadata, "replace_existing", False)
            )

            def mutate_add_agent(target_graph: ExecutionGraph) -> None:
                if replace_existing and node_id in target_graph.nodes:
                    target_graph.remove_node(node_id)
                node = AgentNode(
                    node_id=node_id,
                    node_name=node_name,
                    agent_id=agent_id,
                    additional_prompt=additional_prompt,
                    next_node_ids=next_node_ids,
                    metadata=lifecycle,
                )
                target_graph.add_node(node)
                for next_node_id in next_node_ids:
                    target_graph.add_edge(node_id, next_node_id)

            self._commit_graph_edit(graph, context, action, mutate_add_agent)
            metadata_patch.update(
                {
                    "graph_node_id": node_id,
                    "graph_node_name": node_name,
                    "graph_node_agent_id": agent_id,
                    "graph_node_next_node_ids": list(next_node_ids),
                    "graph_node_runtime_transient": lifecycle["runtime_transient"],
                    "graph_node_persistence": lifecycle["persistence"],
                    "graph_node_lifetime_policy": lifecycle["lifetime_policy"],
                    "graph_node_lifecycle": dict(lifecycle["node_lifecycle"]),
                    "next_node_id": node_id,
                }
            )
            if context.core is not None:
                context.core.record_runtime_change(
                    action="graph_add_agent_node",
                    subject_kind="graph",
                    subject_id=graph.graph_name,
                    detail=metadata_patch,
                )
        elif action == "add_tool_node":
            node_id = int(self._pick_value(control_source, runtime_metadata, "node_id"))
            node_name = str(self._pick_value(control_source, runtime_metadata, "node_name"))
            tool_name = str(self._pick_value(control_source, runtime_metadata, "tool_name"))
            input_mapping = dict(self._pick_optional_value(control_source, runtime_metadata, "input_mapping", {}) or {})
            lifecycle = self._resolve_node_lifecycle(control_source, runtime_metadata, default_transient=True)
            next_node_ids = self._coerce_node_id_list(
                self._pick_optional_value(control_source, runtime_metadata, "next_node_ids") or []
            )

            def mutate_add_tool(target_graph: ExecutionGraph) -> None:
                node = ToolNode(
                    node_id=node_id,
                    node_name=node_name,
                    tool_name=tool_name,
                    input_mapping=input_mapping,
                    next_node_ids=next_node_ids,
                    metadata=lifecycle,
                )
                target_graph.add_node(node)
                for next_node_id in next_node_ids:
                    target_graph.add_edge(node_id, next_node_id)

            self._commit_graph_edit(graph, context, action, mutate_add_tool)
            metadata_patch.update(
                {
                    "graph_node_id": node_id,
                    "graph_node_name": node_name,
                    "graph_node_tool_name": tool_name,
                    "graph_node_next_node_ids": list(next_node_ids),
                    "graph_node_runtime_transient": lifecycle["runtime_transient"],
                    "graph_node_persistence": lifecycle["persistence"],
                    "graph_node_lifetime_policy": lifecycle["lifetime_policy"],
                    "graph_node_lifecycle": dict(lifecycle["node_lifecycle"]),
                }
            )
            if context.core is not None:
                context.core.record_runtime_change(
                    action="graph_add_tool_node",
                    subject_kind="graph",
                    subject_id=graph.graph_name,
                    detail=metadata_patch,
                )
        elif action == "remove_node":
            node_id = int(self._pick_value(control_source, runtime_metadata, "node_id"))
            self._commit_graph_edit(
                graph,
                context,
                action,
                lambda target_graph: target_graph.remove_node(node_id),
            )
            metadata_patch.update({"graph_node_id": node_id})
            if context.core is not None:
                context.core.record_runtime_change(
                    action="graph_remove_node",
                    subject_kind="graph",
                    subject_id=graph.graph_name,
                    detail=metadata_patch,
                )
        elif action == "replace_next":
            from_node_id = int(self._pick_value(control_source, runtime_metadata, "from_node_id"))
            to_node_ids = self._coerce_node_id_list(
                self._pick_optional_value(control_source, runtime_metadata, "to_node_ids") or []
            )
            self._commit_graph_edit(
                graph,
                context,
                action,
                lambda target_graph: target_graph.replace_next(from_node_id, to_node_ids),
            )
            metadata_patch.update(
                {
                    "graph_from_node_id": from_node_id,
                    "graph_to_node_ids": list(to_node_ids),
                }
            )
            if context.core is not None:
                context.core.record_runtime_change(
                    action="graph_replace_next",
                    subject_kind="graph",
                    subject_id=graph.graph_name,
                    detail=metadata_patch,
                )
        elif action == "add_edge":
            from_node_id = int(self._pick_value(control_source, runtime_metadata, "from_node_id"))
            to_node_id = int(self._pick_value(control_source, runtime_metadata, "to_node_id"))
            self._commit_graph_edit(
                graph,
                context,
                action,
                lambda target_graph: target_graph.add_edge(from_node_id, to_node_id),
            )
            metadata_patch.update(
                {
                    "graph_from_node_id": from_node_id,
                    "graph_to_node_id": to_node_id,
                }
            )
            if context.core is not None:
                context.core.record_runtime_change(
                    action="graph_add_edge",
                    subject_kind="graph",
                    subject_id=graph.graph_name,
                    detail=metadata_patch,
                )
        elif action == "remove_edge":
            from_node_id = int(self._pick_value(control_source, runtime_metadata, "from_node_id"))
            to_node_id = int(self._pick_value(control_source, runtime_metadata, "to_node_id"))
            self._commit_graph_edit(
                graph,
                context,
                action,
                lambda target_graph: target_graph.remove_edge(from_node_id, to_node_id),
            )
            metadata_patch.update(
                {
                    "graph_from_node_id": from_node_id,
                    "graph_to_node_id": to_node_id,
                }
            )
            if context.core is not None:
                context.core.record_runtime_change(
                    action="graph_remove_edge",
                    subject_kind="graph",
                    subject_id=graph.graph_name,
                    detail=metadata_patch,
                )
        elif action == "set_entry":
            node_id = int(self._pick_value(control_source, runtime_metadata, "node_id"))
            self._commit_graph_edit(
                graph,
                context,
                action,
                lambda target_graph: target_graph.set_entry(node_id),
            )
            metadata_patch.update({"graph_node_id": node_id})
            if context.core is not None:
                context.core.record_runtime_change(
                    action="graph_set_entry",
                    subject_kind="graph",
                    subject_id=graph.graph_name,
                    detail=metadata_patch,
                )
        elif action == "set_exit":
            node_id = int(self._pick_value(control_source, runtime_metadata, "node_id"))
            self._commit_graph_edit(
                graph,
                context,
                action,
                lambda target_graph: target_graph.set_exit(node_id),
            )
            metadata_patch.update({"graph_node_id": node_id})
            if context.core is not None:
                context.core.record_runtime_change(
                    action="graph_set_exit",
                    subject_kind="graph",
                    subject_id=graph.graph_name,
                    detail=metadata_patch,
                )
        else:
            raise ValueError(f"Unknown graph_editor action: {action}")

        response = {
            "success": True,
            "action": action,
            "graph_name": graph.graph_name,
            "node_count": len(graph.nodes),
            "entry_node_id": graph.entry_node_id,
            "exit_node_id": graph.exit_node_id,
            "content": content_passthrough,
            "metadata_patch": metadata_patch,
        }
        if action in {"add_agent_node", "add_tool_node"}:
            response["next_node_id"] = node_id
        if action == "remove_node":
            response["metadata_clear"] = self._cleanup_metadata_keys()
        return response

    def _normalize_arguments(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if "action" in arguments:
            return dict(arguments)

        raw_input = arguments.get("input")
        if isinstance(raw_input, dict):
            return dict(raw_input)
        if isinstance(raw_input, str) and raw_input.strip():
            try:
                parsed = json.loads(raw_input)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "graph_editor expected JSON input when no direct action was provided."
                ) from exc
            if not isinstance(parsed, dict):
                raise ValueError("graph_editor JSON input must decode to an object.")
            return parsed
        raise ValueError("graph_editor requires either direct arguments or JSON input.")

    def _resolve_control_source(
        self,
        normalized: Dict[str, Any],
        runtime_metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        for key in ("graph_edit", "control", "spawn", "cleanup"):
            candidate = normalized.get(key)
            if isinstance(candidate, dict):
                return candidate
        for key in ("graph_edit", "control", "spawn", "cleanup"):
            candidate = runtime_metadata.get(key)
            if isinstance(candidate, dict):
                return candidate
        return normalized or runtime_metadata

    def _extract_content_passthrough(self, normalized: Dict[str, Any]) -> Optional[str]:
        content = normalized.get("content")
        if content is not None:
            return str(content)
        raw_input = normalized.get("input")
        if raw_input is None:
            return None
        return str(raw_input)

    def _pick_value(
        self,
        control_source: Dict[str, Any],
        runtime_metadata: Dict[str, Any],
        key: str,
    ) -> Any:
        value = self._pick_optional_value(control_source, runtime_metadata, key)
        if value is None:
            raise ValueError(f"graph_editor requires '{key}'.")
        return value

    def _pick_optional_value(
        self,
        control_source: Dict[str, Any],
        runtime_metadata: Dict[str, Any],
        key: str,
        default: Any = None,
    ) -> Any:
        for candidate_key in self._alias_keys(key):
            if candidate_key in control_source and control_source[candidate_key] is not None:
                return control_source[candidate_key]
            if candidate_key in runtime_metadata and runtime_metadata[candidate_key] is not None:
                return runtime_metadata[candidate_key]
        return default

    def _coerce_node_id_list(self, raw: Any) -> List[int]:
        if raw is None:
            return []
        if isinstance(raw, list):
            return [int(item) for item in raw]
        return [int(raw)]

    def _validate_graph(self, graph: ExecutionGraph, core: Any, action: str) -> None:
        validation = graph.validate(core)
        if not validation.is_valid:
            detail = "; ".join(validation.errors)
            raise ValueError(f"graph_editor action '{action}' left graph invalid: {detail}")

    def _commit_graph_edit(self, graph: ExecutionGraph, context: ToolContext, action: str, mutate) -> None:
        previous = graph.clone()
        candidate = graph.clone()
        mutate(candidate)
        self._validate_graph(candidate, context.core, action)
        self._copy_graph_state(graph, candidate)
        try:
            self._persist_graph(context)
        except Exception:
            self._copy_graph_state(graph, previous)
            raise

    def _copy_graph_state(self, target: ExecutionGraph, source: ExecutionGraph) -> None:
        target.graph_name = source.graph_name
        target.nodes = {
            node_id: source._clone_node(node)
            for node_id, node in source.nodes.items()
        }
        target.edges = [
            edge
            for edge in source.clone().edges
        ]
        target.entry_node_id = source.entry_node_id
        target.exit_node_id = source.exit_node_id

    def _persist_graph(self, context: ToolContext) -> None:
        if context.core is None:
            return
        persist = getattr(context.core, "persist_execution_graph", None)
        if callable(persist):
            persist()

    def _cleanup_metadata_keys(self) -> List[str]:
        return [
            "graph_action",
            "graph_name",
            "graph_node_id",
            "graph_node_name",
            "graph_node_agent_id",
            "graph_node_tool_name",
            "graph_node_next_node_ids",
            "graph_node_runtime_transient",
            "graph_node_persistence",
            "graph_node_lifetime_policy",
            "graph_node_lifecycle",
            "graph_from_node_id",
            "graph_to_node_id",
            "graph_to_node_ids",
            "next_node_id",
            "spawned_agent_id",
            "spawned_agent_name",
            "spawned_agent_prompt",
            "spawned_agent_skill",
            "spawned_agent_node_id",
            "spawned_agent_next_node_ids",
            "deleted_agent_id",
            "deleted_agent_name",
            "spawn",
            "graph_edit",
            "cleanup",
            "control",
        ]

    def _resolve_node_lifecycle(
        self,
        control_source: Dict[str, Any],
        runtime_metadata: Dict[str, Any],
        *,
        default_transient: bool,
    ) -> Dict[str, Any]:
        lifecycle_source = self._pick_optional_value(control_source, runtime_metadata, "node_lifecycle")
        if not isinstance(lifecycle_source, dict):
            lifecycle_source = self._pick_optional_value(control_source, runtime_metadata, "lifecycle")
        if not isinstance(lifecycle_source, dict):
            lifecycle_source = {}

        persistence = str(
            self._pick_optional_value(control_source, runtime_metadata, "persistence")
            or lifecycle_source.get("persistence")
            or ("transient" if default_transient else "persistent")
        ).strip().lower()
        if persistence not in {"transient", "persistent", "ephemeral", "temporary"}:
            persistence = "transient" if default_transient else "persistent"

        lifetime_policy = str(
            self._pick_optional_value(control_source, runtime_metadata, "lifetime_policy")
            or lifecycle_source.get("lifetime_policy")
            or ("run" if persistence in {"transient", "ephemeral", "temporary"} else "manual")
        ).strip().lower()
        if lifetime_policy not in {"run", "session", "swarm", "manual"}:
            lifetime_policy = "run" if persistence in {"transient", "ephemeral", "temporary"} else "manual"

        runtime_transient = self._coerce_lifecycle_transient(
            self._pick_optional_value(control_source, runtime_metadata, "runtime_transient"),
            persistence=persistence,
            lifetime_policy=lifetime_policy,
            default_transient=default_transient,
        )

        lifecycle = {
            "runtime_transient": runtime_transient,
            "persistence": "transient" if runtime_transient else "persistent",
            "lifetime_policy": lifetime_policy,
            "node_lifecycle": {
                "runtime_transient": runtime_transient,
                "persistence": "transient" if runtime_transient else "persistent",
                "lifetime_policy": lifetime_policy,
            },
        }
        return lifecycle

    def _coerce_lifecycle_transient(
        self,
        raw_runtime_transient: Any,
        *,
        persistence: str,
        lifetime_policy: str,
        default_transient: bool,
    ) -> bool:
        if raw_runtime_transient is not None:
            return bool(raw_runtime_transient)
        if persistence in {"transient", "ephemeral", "temporary"}:
            return True
        if persistence == "persistent":
            return False
        if lifetime_policy in {"run", "session"}:
            return True
        if lifetime_policy in {"swarm", "manual"}:
            return False
        return default_transient

    def _alias_keys(self, key: str) -> List[str]:
        alias_map = {
            "node_id": ["node_id", "graph_node_id", "spawned_agent_node_id", "cleanup_node_id"],
            "node_name": ["node_name", "graph_node_name", "spawned_agent_name"],
            "agent_id": ["agent_id", "graph_node_agent_id", "spawned_agent_id"],
            "tool_name": ["tool_name", "graph_node_tool_name"],
            "next_node_ids": ["next_node_ids", "graph_node_next_node_ids", "spawned_agent_next_node_ids"],
            "from_node_id": ["from_node_id", "graph_from_node_id"],
            "to_node_id": ["to_node_id", "graph_to_node_id"],
            "to_node_ids": ["to_node_ids", "graph_to_node_ids"],
            "next_node_id": ["next_node_id", "graph_node_id", "spawned_agent_node_id"],
            "additional_prompt": ["additional_prompt", "spawned_agent_prompt"],
            "replace_existing": ["replace_existing"],
            "persistence": ["persistence", "graph_node_persistence"],
            "lifetime_policy": ["lifetime_policy", "graph_node_lifetime_policy"],
            "node_lifecycle": ["node_lifecycle", "graph_node_lifecycle"],
            "runtime_transient": ["runtime_transient", "graph_node_runtime_transient"],
        }
        return alias_map.get(key, [key])


TOOL = GraphEditorTool()
