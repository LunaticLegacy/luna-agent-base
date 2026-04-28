"""运行时执行图动态编辑工具。

本模块提供 ``GraphEditorTool``，用于在任务执行期间通过事务化方式
修改执行图（ExecutionGraph）。支持增删节点/边、设置入口/出口、
替换后继节点等操作，并在每次变更后自动记录运行时审计日志。

主要导出内容：
    - :class:`GraphEditorTool`: 图编辑工具定义。
    - ``TOOL``: 模块级单例实例。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from core import AgentNode, ExecutionGraph, Node, ToolNode
from core.graph_transaction import GraphMutationRecord, GraphTransaction
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
        """执行图编辑操作。

        先规范化入参并解析控制来源，再根据 action 分发到对应分支。
        所有变更均通过 ``GraphTransaction`` 提交，保证原子性。

        Args:
            arguments: 工具入参字典。
            context: 工具执行上下文，需包含 graph 与 core。

        Returns:
            Dict[str, Any]: 包含 success、action、graph_name、node_count、entry_node_id、
            exit_node_id、metadata_patch 的结果字典。

        Raises:
            ValueError: 缺少 action、图对象无效或变更参数非法时抛出。
        """
        require_tool_capability(context, "graph_mutation", self.tool_name)
        if context is None or context.graph is None:
            raise ValueError("graph_editor requires a runtime graph context.")

        graph = context.graph
        if not isinstance(graph, ExecutionGraph):
            raise ValueError("graph_editor received an invalid graph object.")

        normalized = self._normalize_arguments(arguments)
        runtime_metadata = dict(context.metadata or {})
        control_source = self._resolve_control_source(normalized, runtime_metadata)
        action = str(
            normalized.get("action")
            or normalized.get("operation")
            or control_source.get("action")
            or control_source.get("operation")
            or ""
        ).strip().lower()
        if not action:
            raise ValueError("graph_editor requires an 'action'.")

        content_passthrough = self._extract_content_passthrough(normalized)
        metadata_patch: Dict[str, Any] = {
            "graph_action": action,
            "graph_name": graph.graph_name,
        }
        route_after_mutation = self._coerce_bool(
            self._pick_optional_value(control_source, runtime_metadata, "route_after_mutation", False)
        )
        if route_after_mutation and action not in {"add_agent_node", "add_tool_node"}:
            raise ValueError("route_after_mutation is only supported for node insertion actions.")
        route_target_id: Optional[int] = None

        transaction = GraphTransaction(graph, core=context.core)
        author = str(context.agent_id or runtime_metadata.get("agent_id") or "graph_editor")
        reason = str(normalized.get("reason") or normalized.get("change_reason") or action)

        # Dispatch to action-specific handler --------------------------------
        if action == "add_agent_node":
            patch, route_target_id = await self._execute_add_agent_node(
                graph, control_source, runtime_metadata, transaction, author, reason, context
            )
        elif action == "add_tool_node":
            patch, route_target_id = await self._execute_add_tool_node(
                graph, control_source, runtime_metadata, transaction, author, reason, context
            )
        elif action == "remove_node":
            patch = await self._execute_remove_node(
                graph, control_source, runtime_metadata, transaction, author, reason, context
            )
        elif action == "replace_next":
            patch = await self._execute_replace_next(
                graph, control_source, runtime_metadata, transaction, author, reason, context
            )
        elif action == "add_edge":
            patch = await self._execute_add_edge(
                graph, control_source, runtime_metadata, transaction, author, reason, context
            )
        elif action == "remove_edge":
            patch = await self._execute_remove_edge(
                graph, control_source, runtime_metadata, transaction, author, reason, context
            )
        elif action == "set_entry":
            patch = await self._execute_set_entry(
                graph, control_source, runtime_metadata, transaction, author, reason, context
            )
        elif action == "set_exit":
            patch = await self._execute_set_exit(
                graph, control_source, runtime_metadata, transaction, author, reason, context
            )
        else:
            raise ValueError(f"Unknown graph_editor action: {action}")

        metadata_patch.update(patch)

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
        if route_after_mutation:
            if route_target_id is None:
                raise ValueError("route_after_mutation is only supported for node insertion actions.")
            if route_target_id not in graph.nodes:
                raise ValueError(f"route_after_mutation target {route_target_id} does not exist after mutation.")
            response["next_node_id"] = route_target_id
        if action == "remove_node":
            response["metadata_clear"] = self._cleanup_metadata_keys()
        return response

    async def _execute_add_agent_node(
        self,
        graph: ExecutionGraph,
        control_source: Dict[str, Any],
        runtime_metadata: Dict[str, Any],
        transaction: GraphTransaction,
        author: str,
        reason: str,
        context: Optional[ToolContext],
    ) -> tuple[Dict[str, Any], int]:
        """Add or replace an :class:`AgentNode` in the execution graph.

        When ``replace_existing`` is true and no explicit successors are
        provided, the existing outgoing edges are preserved to avoid breaking
        the graph.

        Args:
            graph: The graph to mutate.
            control_source: Resolved control instruction dictionary.
            runtime_metadata: Runtime metadata from the tool context.
            transaction: Active graph transaction.
            author: Change author identifier.
            reason: Change reason string.
            context: Tool execution context (for recording runtime changes).

        Returns:
            A tuple of *(metadata_patch, route_target_id)*.
        """
        replace_existing = self._coerce_bool(
            self._pick_optional_value(control_source, runtime_metadata, "replace_existing", False)
        )
        node_id = self._resolve_node_id(control_source, runtime_metadata, graph, replace_existing=replace_existing)
        node_name = str(self._pick_value(control_source, runtime_metadata, "node_name"))
        agent_id = str(self._pick_value(control_source, runtime_metadata, "agent_id"))
        additional_prompt = self._pick_optional_value(
            control_source, runtime_metadata, "additional_prompt"
        )
        lifecycle = self._resolve_node_lifecycle(control_source, runtime_metadata, default_transient=True)
        has_next_node_ids = self._has_any_key(control_source, runtime_metadata, "next_node_ids")
        next_node_ids = self._coerce_node_id_list(
            self._pick_optional_value(control_source, runtime_metadata, "next_node_ids") or []
        )
        # Preserve outgoing edges when replacing a node without explicit successors.
        if replace_existing and node_id in graph.nodes and not has_next_node_ids:
            next_node_ids = [
                edge.to_node_id
                for edge in graph.outgoing_edges(node_id)
                if edge.to_node_id != node_id
            ]

        def mutate_add_agent(target_graph: ExecutionGraph) -> None:
            if replace_existing and node_id in target_graph.nodes:
                incoming_edges, _outgoing_edges, was_entry, was_exit = self._capture_existing_node_links(
                    target_graph, node_id,
                )
                target_graph.remove_node(node_id)
            node = AgentNode(
                node_id=node_id,
                node_name=node_name,
                agent_id=agent_id,
                additional_prompt=additional_prompt,
                metadata=lifecycle,
            )
            node.next_node_ids = next_node_ids
            target_graph.add_node(node)
            if replace_existing and "incoming_edges" in locals():
                for edge in incoming_edges:
                    target_graph.add_edge(
                        edge.from_node_id,
                        node_id,
                        label=edge.label,
                        condition=edge.condition,
                        priority=edge.priority,
                    )
                if was_entry:
                    target_graph.set_entry(node_id)
                if was_exit:
                    target_graph.set_exit(node_id)
            for next_node_id in next_node_ids:
                target_graph.add_edge(node_id, next_node_id)

        await self._commit_graph_edit(
            transaction,
            action="add_agent_node",
            detail={
                "graph_node_id": node_id,
                "graph_node_name": node_name,
                "graph_node_agent_id": agent_id,
                "graph_node_next_node_ids": list(next_node_ids),
                "instance_policy": "singleton",
                "replace_existing": replace_existing,
            },
            mutate=mutate_add_agent,
            author=author,
            reason=reason,
        )
        metadata_patch = {
            "graph_node_id": node_id,
            "graph_node_name": node_name,
            "graph_node_agent_id": agent_id,
            "graph_node_next_node_ids": list(next_node_ids),
            "graph_node_runtime_transient": lifecycle["runtime_transient"],
            "graph_node_persistence": lifecycle["persistence"],
            "graph_node_lifetime_policy": lifecycle["lifetime_policy"],
            "graph_node_lifecycle": dict(lifecycle["node_lifecycle"]),
        }
        if context is not None and context.core is not None:
            context.core.record_runtime_change(
                action="graph_add_agent_node",
                subject_kind="graph",
                subject_id=graph.graph_name,
                detail=metadata_patch,
            )
        return metadata_patch, node_id

    async def _execute_add_tool_node(
        self,
        graph: ExecutionGraph,
        control_source: Dict[str, Any],
        runtime_metadata: Dict[str, Any],
        transaction: GraphTransaction,
        author: str,
        reason: str,
        context: Optional[ToolContext],
    ) -> tuple[Dict[str, Any], int]:
        """Add or replace a :class:`ToolNode` in the execution graph.

        Edge-preservation logic for ``replace_existing`` mirrors
        :meth:`_execute_add_agent_node`.

        Args:
            graph: The graph to mutate.
            control_source: Resolved control instruction dictionary.
            runtime_metadata: Runtime metadata from the tool context.
            transaction: Active graph transaction.
            author: Change author identifier.
            reason: Change reason string.
            context: Tool execution context.

        Returns:
            A tuple of *(metadata_patch, route_target_id)*.
        """
        replace_existing = self._coerce_bool(
            self._pick_optional_value(control_source, runtime_metadata, "replace_existing", False)
        )
        node_id = self._resolve_node_id(control_source, runtime_metadata, graph, replace_existing=replace_existing)
        node_name = str(self._pick_value(control_source, runtime_metadata, "node_name"))
        tool_name = str(self._pick_value(control_source, runtime_metadata, "tool_name"))
        input_mapping = dict(self._pick_optional_value(control_source, runtime_metadata, "input_mapping", {}) or {})
        lifecycle = self._resolve_node_lifecycle(control_source, runtime_metadata, default_transient=True)
        has_next_node_ids = self._has_any_key(control_source, runtime_metadata, "next_node_ids")
        next_node_ids = self._coerce_node_id_list(
            self._pick_optional_value(control_source, runtime_metadata, "next_node_ids") or []
        )
        if replace_existing and node_id in graph.nodes and not has_next_node_ids:
            next_node_ids = [
                edge.to_node_id
                for edge in graph.outgoing_edges(node_id)
                if edge.to_node_id != node_id
            ]

        def mutate_add_tool(target_graph: ExecutionGraph) -> None:
            if replace_existing and node_id in target_graph.nodes:
                incoming_edges, _outgoing_edges, was_entry, was_exit = self._capture_existing_node_links(
                    target_graph, node_id,
                )
                target_graph.remove_node(node_id)
            node = ToolNode(
                node_id=node_id,
                node_name=node_name,
                tool_name=tool_name,
                input_mapping=input_mapping,
                next_node_ids=next_node_ids,
                metadata=lifecycle,
            )
            target_graph.add_node(node)
            if replace_existing and "incoming_edges" in locals():
                for edge in incoming_edges:
                    target_graph.add_edge(
                        edge.from_node_id,
                        node_id,
                        label=edge.label,
                        condition=edge.condition,
                        priority=edge.priority,
                    )
                if was_entry:
                    target_graph.set_entry(node_id)
                if was_exit:
                    target_graph.set_exit(node_id)
            for next_node_id in next_node_ids:
                target_graph.add_edge(node_id, next_node_id)

        await self._commit_graph_edit(
            transaction,
            action="add_tool_node",
            detail={
                "graph_node_id": node_id,
                "graph_node_name": node_name,
                "graph_node_tool_name": tool_name,
                "graph_node_next_node_ids": list(next_node_ids),
                "replace_existing": replace_existing,
            },
            mutate=mutate_add_tool,
            author=author,
            reason=reason,
        )
        metadata_patch = {
            "graph_node_id": node_id,
            "graph_node_name": node_name,
            "graph_node_tool_name": tool_name,
            "graph_node_next_node_ids": list(next_node_ids),
            "graph_node_runtime_transient": lifecycle["runtime_transient"],
            "graph_node_persistence": lifecycle["persistence"],
            "graph_node_lifetime_policy": lifecycle["lifetime_policy"],
            "graph_node_lifecycle": dict(lifecycle["node_lifecycle"]),
        }
        if context is not None and context.core is not None:
            context.core.record_runtime_change(
                action="graph_add_tool_node",
                subject_kind="graph",
                subject_id=graph.graph_name,
                detail=metadata_patch,
            )
        return metadata_patch, node_id

    async def _execute_remove_node(
        self,
        graph: ExecutionGraph,
        control_source: Dict[str, Any],
        runtime_metadata: Dict[str, Any],
        transaction: GraphTransaction,
        author: str,
        reason: str,
        context: Optional[ToolContext],
    ) -> Dict[str, Any]:
        """Remove a node from the execution graph.

        Args:
            graph: The graph to mutate.
            control_source: Resolved control instruction dictionary.
            runtime_metadata: Runtime metadata from the tool context.
            transaction: Active graph transaction.
            author: Change author identifier.
            reason: Change reason string.
            context: Tool execution context.

        Returns:
            Metadata patch dictionary.
        """
        node_id = int(self._pick_value(control_source, runtime_metadata, "node_id"))
        await self._commit_graph_edit(
            transaction,
            action="remove_node",
            detail={"graph_node_id": node_id},
            mutate=lambda target_graph: target_graph.remove_node(node_id),
            author=author,
            reason=reason,
        )
        metadata_patch = {"graph_node_id": node_id}
        if context is not None and context.core is not None:
            context.core.record_runtime_change(
                action="graph_remove_node",
                subject_kind="graph",
                subject_id=graph.graph_name,
                detail=metadata_patch,
            )
        return metadata_patch

    async def _execute_replace_next(
        self,
        graph: ExecutionGraph,
        control_source: Dict[str, Any],
        runtime_metadata: Dict[str, Any],
        transaction: GraphTransaction,
        author: str,
        reason: str,
        context: Optional[ToolContext],
    ) -> Dict[str, Any]:
        """Replace the outgoing edges of a node.

        Args:
            graph: The graph to mutate.
            control_source: Resolved control instruction dictionary.
            runtime_metadata: Runtime metadata from the tool context.
            transaction: Active graph transaction.
            author: Change author identifier.
            reason: Change reason string.
            context: Tool execution context.

        Returns:
            Metadata patch dictionary.
        """
        from_node_id = int(self._pick_value(control_source, runtime_metadata, "from_node_id"))
        to_node_ids = self._coerce_node_id_list(
            self._pick_optional_value(control_source, runtime_metadata, "to_node_ids") or []
        )
        await self._commit_graph_edit(
            transaction,
            action="replace_next",
            detail={
                "graph_from_node_id": from_node_id,
                "graph_to_node_ids": list(to_node_ids),
            },
            mutate=lambda target_graph: target_graph.replace_next(from_node_id, to_node_ids),
            author=author,
            reason=reason,
        )
        metadata_patch = {
            "graph_from_node_id": from_node_id,
            "graph_to_node_ids": list(to_node_ids),
        }
        if context is not None and context.core is not None:
            context.core.record_runtime_change(
                action="graph_replace_next",
                subject_kind="graph",
                subject_id=graph.graph_name,
                detail=metadata_patch,
            )
        return metadata_patch

    async def _execute_add_edge(
        self,
        graph: ExecutionGraph,
        control_source: Dict[str, Any],
        runtime_metadata: Dict[str, Any],
        transaction: GraphTransaction,
        author: str,
        reason: str,
        context: Optional[ToolContext],
    ) -> Dict[str, Any]:
        """Add an edge between two nodes.

        Args:
            graph: The graph to mutate.
            control_source: Resolved control instruction dictionary.
            runtime_metadata: Runtime metadata from the tool context.
            transaction: Active graph transaction.
            author: Change author identifier.
            reason: Change reason string.
            context: Tool execution context.

        Returns:
            Metadata patch dictionary.
        """
        from_node_id = int(self._pick_value(control_source, runtime_metadata, "from_node_id"))
        to_node_id = int(self._pick_value(control_source, runtime_metadata, "to_node_id"))
        await self._commit_graph_edit(
            transaction,
            action="add_edge",
            detail={
                "graph_from_node_id": from_node_id,
                "graph_to_node_id": to_node_id,
            },
            mutate=lambda target_graph: target_graph.add_edge(from_node_id, to_node_id),
            author=author,
            reason=reason,
        )
        metadata_patch = {
            "graph_from_node_id": from_node_id,
            "graph_to_node_id": to_node_id,
        }
        if context is not None and context.core is not None:
            context.core.record_runtime_change(
                action="graph_add_edge",
                subject_kind="graph",
                subject_id=graph.graph_name,
                detail=metadata_patch,
            )
        return metadata_patch

    async def _execute_remove_edge(
        self,
        graph: ExecutionGraph,
        control_source: Dict[str, Any],
        runtime_metadata: Dict[str, Any],
        transaction: GraphTransaction,
        author: str,
        reason: str,
        context: Optional[ToolContext],
    ) -> Dict[str, Any]:
        """Remove an edge between two nodes.

        Args:
            graph: The graph to mutate.
            control_source: Resolved control instruction dictionary.
            runtime_metadata: Runtime metadata from the tool context.
            transaction: Active graph transaction.
            author: Change author identifier.
            reason: Change reason string.
            context: Tool execution context.

        Returns:
            Metadata patch dictionary.
        """
        from_node_id = int(self._pick_value(control_source, runtime_metadata, "from_node_id"))
        to_node_id = int(self._pick_value(control_source, runtime_metadata, "to_node_id"))
        await self._commit_graph_edit(
            transaction,
            action="remove_edge",
            detail={
                "graph_from_node_id": from_node_id,
                "graph_to_node_id": to_node_id,
            },
            mutate=lambda target_graph: target_graph.remove_edge(from_node_id, to_node_id),
            author=author,
            reason=reason,
        )
        metadata_patch = {
            "graph_from_node_id": from_node_id,
            "graph_to_node_id": to_node_id,
        }
        if context is not None and context.core is not None:
            context.core.record_runtime_change(
                action="graph_remove_edge",
                subject_kind="graph",
                subject_id=graph.graph_name,
                detail=metadata_patch,
            )
        return metadata_patch

    async def _execute_set_entry(
        self,
        graph: ExecutionGraph,
        control_source: Dict[str, Any],
        runtime_metadata: Dict[str, Any],
        transaction: GraphTransaction,
        author: str,
        reason: str,
        context: Optional[ToolContext],
    ) -> Dict[str, Any]:
        """Set the entry node of the graph.

        Args:
            graph: The graph to mutate.
            control_source: Resolved control instruction dictionary.
            runtime_metadata: Runtime metadata from the tool context.
            transaction: Active graph transaction.
            author: Change author identifier.
            reason: Change reason string.
            context: Tool execution context.

        Returns:
            Metadata patch dictionary.
        """
        node_id = int(self._pick_value(control_source, runtime_metadata, "node_id"))
        await self._commit_graph_edit(
            transaction,
            action="set_entry",
            detail={"graph_node_id": node_id},
            mutate=lambda target_graph: target_graph.set_entry(node_id),
            author=author,
            reason=reason,
        )
        metadata_patch = {"graph_node_id": node_id}
        if context is not None and context.core is not None:
            context.core.record_runtime_change(
                action="graph_set_entry",
                subject_kind="graph",
                subject_id=graph.graph_name,
                detail=metadata_patch,
            )
        return metadata_patch

    async def _execute_set_exit(
        self,
        graph: ExecutionGraph,
        control_source: Dict[str, Any],
        runtime_metadata: Dict[str, Any],
        transaction: GraphTransaction,
        author: str,
        reason: str,
        context: Optional[ToolContext],
    ) -> Dict[str, Any]:
        """Set the exit node of the graph.

        Args:
            graph: The graph to mutate.
            control_source: Resolved control instruction dictionary.
            runtime_metadata: Runtime metadata from the tool context.
            transaction: Active graph transaction.
            author: Change author identifier.
            reason: Change reason string.
            context: Tool execution context.

        Returns:
            Metadata patch dictionary.
        """
        node_id = int(self._pick_value(control_source, runtime_metadata, "node_id"))
        await self._commit_graph_edit(
            transaction,
            action="set_exit",
            detail={"graph_node_id": node_id},
            mutate=lambda target_graph: target_graph.set_exit(node_id),
            author=author,
            reason=reason,
        )
        metadata_patch = {"graph_node_id": node_id}
        if context is not None and context.core is not None:
            context.core.record_runtime_change(
                action="graph_set_exit",
                subject_kind="graph",
                subject_id=graph.graph_name,
                detail=metadata_patch,
            )
        return metadata_patch


    def _normalize_arguments(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """将工具入参规范化成可直接使用的字典。

        优先保留已含 action/operation 的字典；若不存在，
        则尝试从 ``input`` 字段解析 JSON 对象。

        Args:
            arguments: 原始工具入参。

        Returns:
            规范化后的参数字典。

        Raises:
            ValueError: 无法解析出有效字典时抛出。
        """
        if "action" in arguments or "operation" in arguments:
            return dict(arguments)
        if any(isinstance(arguments.get(key), dict) for key in ("graph_edit", "control", "spawn", "cleanup")):
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
        """确定实际承载控制指令的字典来源。

        先在 normalized 中查找 graph_edit/control/spawn/cleanup 子字典；
        找不到时再到 runtime_metadata 中查找，最后回退到顶层字典本身。

        Args:
            normalized: 规范化后的工具入参。
            runtime_metadata: 运行时元数据字典。

        Returns:
            包含控制指令的字典。
        """
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
        """提取需要透传给下游的内容。

        优先取 ``content`` 字段，其次取 ``input`` 字段的字符串形式。

        Args:
            normalized: 规范化后的工具入参。

        Returns:
            透传内容字符串，或 None。
        """
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
        """从 control_source 或 runtime_metadata 中获取必填值。

        Args:
            control_source: 控制指令字典。
            runtime_metadata: 运行时元数据。
            key: 要查找的键。

        Returns:
            找到的非 None 值。

        Raises:
            ValueError: 当键对应值为 None 时抛出。
        """
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
        """按别名链查找可选值。

        先遍历 key 的所有别名，在 control_source 中命中则返回；
        未命中则再到 runtime_metadata 中查找；最终返回 default。

        Args:
            control_source: 控制指令字典。
            runtime_metadata: 运行时元数据。
            key: 主键名。
            default: 默认值。

        Returns:
            查找结果或 default。
        """
        for candidate_key in self._alias_keys(key):
            if candidate_key in control_source and control_source[candidate_key] is not None:
                return control_source[candidate_key]
            if candidate_key in runtime_metadata and runtime_metadata[candidate_key] is not None:
                return runtime_metadata[candidate_key]
        return default

    def _coerce_node_id_list(self, raw: Any) -> List[int]:
        """将原始输入强制转换为整数节点 ID 列表。

        Args:
            raw: 原始输入（None、list 或单个值）。

        Returns:
            整数节点 ID 列表。
        """
        if raw is None:
            return []
        if isinstance(raw, list):
            return [int(item) for item in raw]
        return [int(raw)]

    def _resolve_node_id(
        self,
        control_source: Dict[str, Any],
        runtime_metadata: Dict[str, Any],
        graph: ExecutionGraph,
        *,
        replace_existing: bool,
    ) -> int:
        """解析节点 ID，支持自动分配。

        若未提供 node_id 或显式传入 "auto"，则使用 ``_next_available_node_id``
        自动生成；若指定了已有 ID 且未开启 replace_existing，则抛出错误。

        Args:
            control_source: 控制指令字典。
            runtime_metadata: 运行时元数据。
            graph: 当前执行图。
            replace_existing: 是否允许替换已有节点。

        Returns:
            解析后的整数节点 ID。

        Raises:
            ValueError: 节点 ID 已存在且不允许替换时抛出。
        """
        raw_node_id = self._pick_optional_value(control_source, runtime_metadata, "node_id")
        if raw_node_id is None or (isinstance(raw_node_id, str) and raw_node_id.strip().lower() == "auto"):
            return self._next_available_node_id(graph)
        node_id = int(raw_node_id)
        if node_id in graph.nodes and not replace_existing:
            raise ValueError(
                f"graph_editor node_id {node_id} already exists; set replace_existing=true or use node_id='auto'."
            )
        return node_id

    def _next_available_node_id(self, graph: ExecutionGraph) -> int:
        """返回图中当前最大的节点 ID + 1，并跳过已存在的值。

        Args:
            graph: 当前执行图。

        Returns:
            可用的整数节点 ID。
        """
        candidate = max(graph.nodes.keys(), default=0) + 1
        while candidate in graph.nodes:
            candidate += 1
        return candidate

    def _has_any_key(
        self,
        control_source: Dict[str, Any],
        runtime_metadata: Dict[str, Any],
        key: str,
    ) -> bool:
        """检查 control_source 或 runtime_metadata 中是否包含 key 的任一别名。

        Args:
            control_source: 控制指令字典。
            runtime_metadata: 运行时元数据。
            key: 主键名。

        Returns:
            True 表示至少有一个别名存在。
        """
        return any(
            candidate_key in control_source or candidate_key in runtime_metadata
            for candidate_key in self._alias_keys(key)
        )

    def _capture_existing_node_links(self, graph: ExecutionGraph, node_id: int):
        """捕获指定节点的现有边连接与入口/出口状态。

        在替换节点前调用，用于在删除旧节点后恢复其入边、出边以及 entry/exit 标志。

        Args:
            graph: 当前执行图。
            node_id: 要捕获的节点 ID。

        Returns:
            Tuple[List[Edge], List[Edge], bool, bool]: 入边列表、出边列表、
            是否为入口节点、是否为出口节点。
        """
        incoming_edges = [
            edge
            for edge in graph.edges
            if edge.to_node_id == node_id and edge.from_node_id != node_id
        ]
        outgoing_edges = [
            edge
            for edge in graph.outgoing_edges(node_id)
            if edge.to_node_id != node_id
        ]
        return (
            incoming_edges,
            outgoing_edges,
            graph.entry_node_id == node_id,
            graph.exit_node_id == node_id,
        )

    def _coerce_bool(self, raw: Any) -> bool:
        """将多种原始值强制转换为布尔值。

        支持 bool、None、str（"1"/"true"/"yes"/"on"）以及 Python 真值判断。

        Args:
            raw: 原始值。

        Returns:
            对应的布尔值。
        """
        if isinstance(raw, bool):
            return raw
        if raw is None:
            return False
        if isinstance(raw, str):
            return raw.strip().lower() in {"1", "true", "yes", "on"}
        return bool(raw)

    async def _commit_graph_edit(
        self,
        transaction: GraphTransaction,
        *,
        action: str,
        detail: Dict[str, Any],
        mutate,
        author: str,
        reason: str,
    ) -> None:
        """将具体的图变更封装为事务记录并提交。

        Args:
            transaction: 图事务对象。
            action: 变更动作名称。
            detail: 变更详情字典。
            mutate: 实际修改图结构的可调用对象。
            author: 变更作者标识。
            reason: 变更原因说明。
        """
        transaction.prepare(
            GraphMutationRecord(
                action=action,
                detail=detail,
                author=author,
                reason=reason,
            ),
            mutate,
        )
        await transaction.commit()

    def _cleanup_metadata_keys(self) -> List[str]:
        """返回需要在节点移除后清理的元数据键列表。

        Returns:
            需要清除的键名列表。
        """
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
        """解析节点生命周期配置。

        从 control_source / runtime_metadata 中提取 persistence、lifetime_policy
        与 runtime_transient，并在缺失时应用合理的默认值。

        Args:
            control_source: 控制指令字典。
            runtime_metadata: 运行时元数据。
            default_transient: 是否默认将节点视为 transient。

        Returns:
            包含 runtime_transient、persistence、lifetime_policy、node_lifecycle 的字典。
        """
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
        """根据优先级将原始值转换为布尔型的 runtime_transient 标志。

        优先级：显式值 > persistence 暗示 > lifetime_policy 暗示 > default_transient。

        Args:
            raw_runtime_transient: 显式传入的 runtime_transient 值。
            persistence: 已解析的持久化策略。
            lifetime_policy: 已解析的生命周期策略。
            default_transient: 最终回退默认值。

        Returns:
            节点是否为运行时瞬态。
        """
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
        """返回某个键的所有已知别名，用于兼容不同调用约定。

        Args:
            key: 主键名。

        Returns:
            包含主键及别名的列表。
        """
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
            "route_after_mutation": ["route_after_mutation", "activate_new_node"],
        }
        return alias_map.get(key, [key])


TOOL = GraphEditorTool()
