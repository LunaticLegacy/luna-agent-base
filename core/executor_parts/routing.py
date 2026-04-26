from __future__ import annotations

from typing import Any, List, Optional

from ..policy import ExecutionGraph, ToolNode, _node_is_transient


class RoutingHelperMixin:
    """Routing and branch resolution helpers for graph execution."""

    def _validate_next_targets(
        self,
        graph: ExecutionGraph,
        current_node: Any,
        next_targets: List[int],
    ) -> None:
        allowed_targets = {edge.to_node_id for edge in graph.outgoing_edges(current_node.node_id)}
        allowed_targets.update(current_node.next_node_ids)
        for next_node_id in next_targets:
            self._ensure_node_exists(
                graph,
                next_node_id,
                current_node_id=current_node.node_id,
                label="next_node_id",
            )
            if next_node_id in allowed_targets:
                continue
            if self._allows_dynamic_next_target(graph, current_node, next_node_id):
                continue
            raise ValueError(
                f"Node {current_node.node_id} resolved next_node_id {next_node_id}, "
                "but that target is not an allowed outgoing edge."
            )

    def _allows_dynamic_next_target(self, graph: ExecutionGraph, current_node: Any, next_node_id: int) -> bool:
        if not isinstance(current_node, ToolNode) or current_node.tool_name != "graph_editor":
            return False
        target = graph.nodes.get(next_node_id)
        metadata = getattr(target, "metadata", {}) if target is not None else {}
        return bool(isinstance(metadata, dict) and _node_is_transient(metadata))

    def _ensure_node_exists(
        self,
        graph: ExecutionGraph,
        node_id: int,
        *,
        current_node_id: int,
        label: str,
    ) -> None:
        if node_id not in graph.nodes:
            raise ValueError(
                f"Node {current_node_id} resolved {label} {node_id}, but that node does not exist."
            )

    def _resolve_next_targets(
        self,
        graph: ExecutionGraph,
        node: Any,
        payload: Any,
        next_node_override: Optional[int],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[int]:
        if next_node_override is not None:
            if next_node_override == node.node_id:
                next_node_override = None
            else:
                return [next_node_override]

        # Envelope mode: control decisions live in metadata["control"], not payload.
        control = metadata.get("control") if isinstance(metadata, dict) else None
        if isinstance(control, dict):
            # Per-node control takes precedence; fall back to flat control for backward compatibility.
            node_control = control.get(str(node.node_id))
            effective_control = node_control if isinstance(node_control, dict) else control
            next_node_ids = effective_control.get("next_node_ids")
            if isinstance(next_node_ids, list) and next_node_ids:
                return [int(item) for item in next_node_ids]

            branch = effective_control.get("branch")
            if branch is not None:
                matched = self._match_branch_targets(graph, node.node_id, branch)
                if matched:
                    return matched

            branches = effective_control.get("branches")
            if isinstance(branches, list) and branches:
                resolved: List[int] = []
                for item in branches:
                    resolved.extend(self._match_branch_targets(graph, node.node_id, item))
                if resolved:
                    return list(dict.fromkeys(resolved))

        # Legacy mode (and envelope fallback): inspect payload dict.
        if isinstance(payload, dict):
            next_node_ids = payload.get("next_node_ids")
            if isinstance(next_node_ids, list) and next_node_ids:
                return [int(item) for item in next_node_ids]

            branch = payload.get("branch")
            if branch is not None:
                matched = self._match_branch_targets(graph, node.node_id, branch)
                if matched:
                    return matched

            branches = payload.get("branches")
            if isinstance(branches, list) and branches:
                resolved: List[int] = []
                for item in branches:
                    resolved.extend(self._match_branch_targets(graph, node.node_id, item))
                if resolved:
                    return list(dict.fromkeys(resolved))

        outgoing = graph.outgoing_edges(node.node_id)
        if outgoing:
            return [edge.to_node_id for edge in outgoing]
        return list(node.next_node_ids)

    def _match_branch_targets(
        self,
        graph: ExecutionGraph,
        node_id: int,
        branch_value: Any,
    ) -> List[int]:
        branch_label = str(branch_value).strip()
        if not branch_label:
            return []
        if branch_label.isdigit():
            return [int(branch_label)]

        matched = [
            edge.to_node_id
            for edge in graph.outgoing_edges(node_id)
            if edge.label == branch_label or edge.condition == branch_label
        ]
        return list(dict.fromkeys(matched))
