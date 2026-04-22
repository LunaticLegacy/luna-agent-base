from __future__ import annotations

from dataclasses import dataclass, field
from pprint import pformat
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from .results import ExecutionEvent, ExecutionState, GraphValidationResult

if TYPE_CHECKING:
    from .core import Core


@dataclass
class Node:
    """Base node definition for the execution graph."""

    node_id: int
    node_name: str
    next_node_ids: List[int] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Edge:
    """Directed edge between two execution nodes."""

    from_node_id: int
    to_node_id: int
    label: Optional[str] = None
    condition: Optional[str] = None
    priority: int = 0


@dataclass
class AgentNode(Node):
    """Graph node that delegates execution to a managed agent."""

    agent_id: str = ""
    additional_prompt: Optional[str] = None


@dataclass
class ToolNode(Node):
    """Graph node that delegates execution to a standard tool."""

    tool_name: str = ""
    input_mapping: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionStep:
    """One step in a graph execution trace."""

    node_id: int
    node_name: str
    node_type: str
    input_payload: Any
    output_payload: Any
    status: str = "ok"
    error: Optional[str] = None
    branch: Optional[str] = None


class ExecutionGraph:
    """Execution graph engine for agents and tools."""

    def __init__(self, graph_name: str) -> None:
        self.graph_name = graph_name
        self.nodes: Dict[int, Node] = {}
        self.edges: List[Edge] = []
        self.entry_node_id: Optional[int] = None
        self.exit_node_id: Optional[int] = None

    def add_node(self, node: Node) -> None:
        """Add a node to the graph."""
        if node.node_id in self.nodes:
            raise ValueError(f"Duplicate node_id: {node.node_id}")
        self.nodes[node.node_id] = node

    def add_edge(
        self,
        from_node_id: int,
        to_node_id: int,
        *,
        label: Optional[str] = None,
        condition: Optional[str] = None,
        priority: int = 0,
    ) -> None:
        """Connect two nodes by id."""
        if from_node_id not in self.nodes:
            raise KeyError(f"Unknown from_node_id: {from_node_id}")
        if to_node_id not in self.nodes:
            raise KeyError(f"Unknown to_node_id: {to_node_id}")
        if to_node_id not in self.nodes[from_node_id].next_node_ids:
            self.nodes[from_node_id].next_node_ids.append(to_node_id)
        if not self._edge_exists(from_node_id, to_node_id, label=label, condition=condition):
            self.edges.append(
                Edge(
                    from_node_id=from_node_id,
                    to_node_id=to_node_id,
                    label=label,
                    condition=condition,
                    priority=priority,
                )
            )

    def replace_next(self, from_node_id: int, to_node_ids: List[int]) -> None:
        """Replace the outgoing edges for a node."""
        if from_node_id not in self.nodes:
            raise KeyError(f"Unknown from_node_id: {from_node_id}")
        for to_node_id in to_node_ids:
            if to_node_id not in self.nodes:
                raise KeyError(f"Unknown to_node_id: {to_node_id}")
        self.nodes[from_node_id].next_node_ids = list(dict.fromkeys(to_node_ids))
        self.edges = [edge for edge in self.edges if edge.from_node_id != from_node_id]
        for to_node_id in self.nodes[from_node_id].next_node_ids:
            self.edges.append(Edge(from_node_id=from_node_id, to_node_id=to_node_id))

    def remove_edge(self, from_node_id: int, to_node_id: int) -> None:
        """Remove one outgoing edge."""
        if from_node_id not in self.nodes:
            raise KeyError(f"Unknown from_node_id: {from_node_id}")
        self.nodes[from_node_id].next_node_ids = [
            existing for existing in self.nodes[from_node_id].next_node_ids
            if existing != to_node_id
        ]
        self.edges = [
            edge
            for edge in self.edges
            if not (edge.from_node_id == from_node_id and edge.to_node_id == to_node_id)
        ]

    def remove_node(self, node_id: int) -> None:
        """Remove a node and detach all incoming edges."""
        if node_id not in self.nodes:
            raise KeyError(f"Unknown node_id: {node_id}")
        del self.nodes[node_id]
        for node in self.nodes.values():
            node.next_node_ids = [next_id for next_id in node.next_node_ids if next_id != node_id]
        self.edges = [
            edge
            for edge in self.edges
            if edge.from_node_id != node_id and edge.to_node_id != node_id
        ]
        if self.entry_node_id == node_id:
            self.entry_node_id = None
        if self.exit_node_id == node_id:
            self.exit_node_id = None

    def set_entry(self, node_id: int) -> None:
        """Set the entry node for the graph."""
        self._ensure_node_exists(node_id)
        self.entry_node_id = node_id

    def set_exit(self, node_id: int) -> None:
        """Set the exit node for the graph."""
        self._ensure_node_exists(node_id)
        self.exit_node_id = node_id

    def _ensure_node_exists(self, node_id: int) -> None:
        if node_id not in self.nodes:
            raise KeyError(f"Unknown node_id: {node_id}")

    def _allows_missing_binding(self, node: Node) -> bool:
        metadata = node.metadata if isinstance(node.metadata, dict) else {}
        return bool(metadata.get("runtime_transient") or metadata.get("temporary"))

    def validate(self, core: Optional["Core"] = None) -> GraphValidationResult:
        """Validate graph structure and runtime bindings."""
        errors: List[str] = []
        warnings: List[str] = []

        if not self.nodes:
            errors.append("Graph has no nodes.")
        if not self.edges and len(self.nodes) > 1:
            warnings.append(
                "Graph has multiple nodes but no explicit edges; execution will fall back to node order."
            )
        if self.entry_node_id is None:
            errors.append("Graph entry node is not set.")
        if self.exit_node_id is None:
            warnings.append("Graph exit node is not set.")

        seen_edges: set[tuple[int, int, Optional[str], Optional[str]]] = set()
        for edge in self.edges:
            edge_key = (edge.from_node_id, edge.to_node_id, edge.label, edge.condition)
            if edge_key in seen_edges:
                warnings.append(
                    f"Duplicate edge from {edge.from_node_id} to {edge.to_node_id} with the same label or condition."
                )
            seen_edges.add(edge_key)
            if edge.from_node_id not in self.nodes:
                errors.append(f"Edge references unknown from_node_id {edge.from_node_id}.")
            if edge.to_node_id not in self.nodes:
                errors.append(f"Edge references unknown to_node_id {edge.to_node_id}.")

        for node in self.nodes.values():
            for next_node_id in node.next_node_ids:
                if next_node_id not in self.nodes:
                    errors.append(
                        f"Node {node.node_id} references unknown next node {next_node_id}."
                    )

            if isinstance(node, AgentNode):
                if not node.agent_id:
                    errors.append(f"Agent node {node.node_id} has no agent_id.")
                elif core is not None and node.agent_id not in core.agents:
                    if self._allows_missing_binding(node):
                        warnings.append(
                            f"Agent node {node.node_id} references missing agent '{node.agent_id}' "
                            "but is marked transient."
                        )
                    else:
                        errors.append(
                            f"Agent node {node.node_id} references missing agent '{node.agent_id}'."
                        )

            if isinstance(node, ToolNode):
                if not node.tool_name:
                    errors.append(f"Tool node {node.node_id} has no tool_name.")
                elif core is not None and node.tool_name not in core.tools:
                    if self._allows_missing_binding(node):
                        warnings.append(
                            f"Tool node {node.node_id} references missing tool '{node.tool_name}' "
                            "but is marked transient."
                        )
                    else:
                        errors.append(
                            f"Tool node {node.node_id} references missing tool '{node.tool_name}'."
                        )

        if self.entry_node_id is not None and self.entry_node_id not in self.nodes:
            errors.append("Graph entry node references a missing node.")
        if self.exit_node_id is not None and self.exit_node_id not in self.nodes:
            errors.append("Graph exit node references a missing node.")

        return GraphValidationResult(
            is_valid=not errors,
            errors=errors,
            warnings=warnings,
        )

    def is_available(self, core: Optional["Core"] = None) -> bool:
        """Return whether the graph is ready for execution."""
        return self.validate(core).is_valid

    def is_complete(self, core: Optional["Core"] = None) -> bool:
        """Return whether the graph is complete enough for runtime use."""
        result = self.validate(core)
        return result.is_valid and not result.warnings

    async def run(
        self,
        core: "Core",
        initial_payload: Any,
        *,
        rounds: int = 0,
        run_id: Optional[str] = None,
        swarm_name: Optional[str] = None,
        event_sink: Optional[Callable[[ExecutionEvent], None]] = None,
    ) -> ExecutionState:
        """Execute the graph from its entry node."""
        from .executor import GraphExecutor

        executor = GraphExecutor()
        return await executor.execute(
            self,
            core,
            initial_payload,
            rounds=rounds,
            run_id=run_id,
            swarm_name=swarm_name,
            event_sink=event_sink,
        )

    def to_python_source(self) -> str:
        """Render the graph as a standalone Python module."""
        lines: List[str] = [
            "from core import AgentNode, ExecutionGraph, ToolNode",
            "",
            "",
            "def build_graph(core):",
            f"    graph = ExecutionGraph({pformat(self.graph_name, sort_dicts=True)})",
        ]

        for node in sorted(self.nodes.values(), key=lambda item: item.node_id):
            lines.extend(self._render_node_source(node))

        for edge in sorted(
            self.edges,
            key=lambda item: (
                item.from_node_id,
                item.priority,
                item.to_node_id,
                item.label or "",
                item.condition or "",
            ),
        ):
            lines.append(
                "    graph.add_edge("
                f"{edge.from_node_id}, {edge.to_node_id}, "
                f"label={pformat(edge.label, sort_dicts=True)}, "
                f"condition={pformat(edge.condition, sort_dicts=True)}, "
                f"priority={edge.priority})"
            )

        if self.entry_node_id is not None:
            lines.append(f"    graph.set_entry({self.entry_node_id})")
        if self.exit_node_id is not None:
            lines.append(f"    graph.set_exit({self.exit_node_id})")

        lines.append("    return graph")
        lines.append("")
        return "\n".join(lines)

    def clone(self) -> "ExecutionGraph":
        """Create a shallow clone of the graph structure."""
        cloned = ExecutionGraph(self.graph_name)
        cloned.nodes = {
            node_id: self._clone_node(node)
            for node_id, node in self.nodes.items()
        }
        cloned.edges = [
            Edge(
                from_node_id=edge.from_node_id,
                to_node_id=edge.to_node_id,
                label=edge.label,
                condition=edge.condition,
                priority=edge.priority,
            )
            for edge in self.edges
        ]
        cloned.entry_node_id = self.entry_node_id
        cloned.exit_node_id = self.exit_node_id
        return cloned

    def _render_node_source(self, node: Node) -> List[str]:
        lines: List[str] = ["    graph.add_node("]
        if isinstance(node, AgentNode):
            lines.extend(
                [
                    "        AgentNode(",
                    f"            node_id={node.node_id},",
                    f"            node_name={pformat(node.node_name, sort_dicts=True)},",
                    f"            next_node_ids={pformat(list(node.next_node_ids), sort_dicts=True)},",
                    f"            metadata={pformat(dict(node.metadata), sort_dicts=True)},",
                    f"            agent_id={pformat(node.agent_id, sort_dicts=True)},",
                    f"            additional_prompt={pformat(node.additional_prompt, sort_dicts=True)},",
                    "        ),",
                ]
            )
        elif isinstance(node, ToolNode):
            lines.extend(
                [
                    "        ToolNode(",
                    f"            node_id={node.node_id},",
                    f"            node_name={pformat(node.node_name, sort_dicts=True)},",
                    f"            next_node_ids={pformat(list(node.next_node_ids), sort_dicts=True)},",
                    f"            metadata={pformat(dict(node.metadata), sort_dicts=True)},",
                    f"            tool_name={pformat(node.tool_name, sort_dicts=True)},",
                    f"            input_mapping={pformat(dict(node.input_mapping), sort_dicts=True)},",
                    "        ),",
                ]
            )
        else:
            lines.extend(
                [
                    "        Node(",
                    f"            node_id={node.node_id},",
                    f"            node_name={pformat(node.node_name, sort_dicts=True)},",
                    f"            next_node_ids={pformat(list(node.next_node_ids), sort_dicts=True)},",
                    f"            metadata={pformat(dict(node.metadata), sort_dicts=True)},",
                    "        ),",
                ]
            )
        lines.append("    )")
        return lines

    def outgoing_edges(self, node_id: int) -> List[Edge]:
        """Return the outgoing edges for a node sorted by priority."""
        return sorted(
            [edge for edge in self.edges if edge.from_node_id == node_id],
            key=lambda edge: edge.priority,
            reverse=True,
        )

    def _clone_node(self, node: Node) -> Node:
        cloned = type(node)(
            node_id=node.node_id,
            node_name=node.node_name,
            next_node_ids=list(node.next_node_ids),
            metadata=dict(node.metadata),
            **self._node_specific_kwargs(node),
        )
        return cloned

    def _node_specific_kwargs(self, node: Node) -> Dict[str, Any]:
        if isinstance(node, AgentNode):
            return {
                "agent_id": node.agent_id,
                "additional_prompt": node.additional_prompt,
            }
        if isinstance(node, ToolNode):
            return {
                "tool_name": node.tool_name,
                "input_mapping": dict(node.input_mapping),
            }
        return {}

    def _edge_exists(
        self,
        from_node_id: int,
        to_node_id: int,
        *,
        label: Optional[str] = None,
        condition: Optional[str] = None,
    ) -> bool:
        return any(
            edge.from_node_id == from_node_id
            and edge.to_node_id == to_node_id
            and edge.label == label
            and edge.condition == condition
            for edge in self.edges
        )
