from __future__ import annotations

from dataclasses import dataclass, field
from pprint import pformat
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING, Literal

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


@dataclass(init=False)
class AgentNode(Node):
    """Graph node that delegates execution to a managed agent."""

    blueprint_ref: str
    additional_prompt: Optional[str]
    instance_policy: Literal["singleton", "per_call"]

    def __init__(
        self,
        node_id: int,
        node_name: str,
        metadata: Optional[Dict[str, Any]] = None,
        blueprint_ref: str = "",
        additional_prompt: Optional[str] = None,
        instance_policy: Literal["singleton", "per_call"] = "singleton",
        *,
        agent_id: Optional[str] = None,
    ) -> None:
        self.node_id = node_id
        self.node_name = node_name
        self.next_node_ids: List[int] = []
        self.metadata = dict(metadata or {})
        self.blueprint_ref = str(blueprint_ref or agent_id or "").strip()
        self.additional_prompt = additional_prompt
        self.instance_policy = str(instance_policy or "singleton").strip().lower() or "singleton"

    @property
    def agent_id(self) -> str:
        """Backward-compatible alias for older graph definitions."""
        return self.blueprint_ref

    @agent_id.setter
    def agent_id(self, value: str) -> None:
        self.blueprint_ref = str(value or "").strip()


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
        self.graph_kind = "execution"
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

    def to_agent_graph(self) -> "ExecutionGraph":
        """Project the execution graph into a pure agent graph."""
        derived = ExecutionGraph(self.graph_name)
        derived.graph_kind = "agent"

        agent_ids = [node_id for node_id, node in self.nodes.items() if isinstance(node, AgentNode)]
        for node_id in agent_ids:
            node = self.nodes[node_id]
            derived.add_node(
                AgentNode(
                    node_id=node.node_id,
                    node_name=node.node_name,
                    metadata=dict(node.metadata),
                    blueprint_ref=node.blueprint_ref,
                    additional_prompt=node.additional_prompt,
                    instance_policy=node.instance_policy,
                )
            )

        def successor_agent_ids(start_node_id: int) -> list[int]:
            seen: set[int] = set()
            stack: list[int] = list(self.nodes[start_node_id].next_node_ids)
            resolved: list[int] = []
            while stack:
                current_id = stack.pop()
                if current_id in seen:
                    continue
                seen.add(current_id)
                current_node = self.nodes.get(current_id)
                if current_node is None:
                    continue
                if isinstance(current_node, AgentNode):
                    if current_id != start_node_id and current_id not in resolved:
                        resolved.append(current_id)
                    continue
                stack.extend(current_node.next_node_ids)
            return resolved

        edge_seen: set[tuple[int, int]] = set()
        for node_id in agent_ids:
            successors = successor_agent_ids(node_id)
            derived.nodes[node_id].next_node_ids = list(successors)
            for successor_id in successors:
                edge_key = (node_id, successor_id)
                if edge_key in edge_seen:
                    continue
                edge_seen.add(edge_key)
                derived.edges.append(
                    Edge(
                        from_node_id=node_id,
                        to_node_id=successor_id,
                        label="agent_route",
                        condition=None,
                        priority=0,
                    )
                )

        if self.entry_node_id in derived.nodes:
            derived.entry_node_id = self.entry_node_id
        else:
            derived.entry_node_id = next(iter(derived.nodes), None)
        if self.exit_node_id in derived.nodes:
            derived.exit_node_id = self.exit_node_id
        elif derived.nodes:
            sink_nodes = [node_id for node_id, node in derived.nodes.items() if not node.next_node_ids]
            derived.exit_node_id = sink_nodes[-1] if sink_nodes else next(reversed(derived.nodes), None)
        return derived

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
        return _node_is_transient(metadata)

    def purge_transient_nodes(self) -> List[int]:
        """Remove transient nodes from the graph and return their ids."""
        removed: List[int] = []
        for node_id, node in list(self.nodes.items()):
            metadata = node.metadata if isinstance(node.metadata, dict) else {}
            if _node_is_transient(metadata):
                self.remove_node(node_id)
                removed.append(node_id)
        return removed

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
                if not node.blueprint_ref:
                    errors.append(f"Agent node {node.node_id} has no blueprint_ref.")
                elif core is not None and not _core_has_agent_blueprint(core, node.blueprint_ref):
                    if self._allows_missing_binding(node):
                        warnings.append(
                            f"Agent node {node.node_id} references missing agent blueprint '{node.blueprint_ref}' "
                            "but is marked transient."
                        )
                    else:
                        errors.append(
                            f"Agent node {node.node_id} references missing agent blueprint '{node.blueprint_ref}'."
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
        cloned.graph_kind = self.graph_kind
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
                    f"            metadata={pformat(dict(node.metadata), sort_dicts=True)},",
                    f"            blueprint_ref={pformat(node.blueprint_ref, sort_dicts=True)},",
                    f"            additional_prompt={pformat(node.additional_prompt, sort_dicts=True)},",
                    f"            instance_policy={pformat(node.instance_policy, sort_dicts=True)},",
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
            metadata=dict(node.metadata),
            **self._node_specific_kwargs(node),
        )
        cloned.next_node_ids = list(node.next_node_ids)
        return cloned

    def _node_specific_kwargs(self, node: Node) -> Dict[str, Any]:
        if isinstance(node, AgentNode):
            return {
                "blueprint_ref": node.blueprint_ref,
                "additional_prompt": node.additional_prompt,
                "instance_policy": node.instance_policy,
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


def _node_is_transient(metadata: Dict[str, Any]) -> bool:
    if not isinstance(metadata, dict):
        return False

    runtime_transient = metadata.get("runtime_transient")
    if runtime_transient is not None:
        return bool(runtime_transient)

    node_lifecycle = metadata.get("node_lifecycle")
    if isinstance(node_lifecycle, dict):
        persistence = str(node_lifecycle.get("persistence", "")).strip().lower()
        lifetime_policy = str(node_lifecycle.get("lifetime_policy", "")).strip().lower()
        if persistence:
            return persistence in {"transient", "temporary", "ephemeral"}
        if lifetime_policy:
            return lifetime_policy in {"run", "session"}

    persistence = str(metadata.get("persistence", "")).strip().lower()
    if persistence:
        return persistence in {"transient", "temporary", "ephemeral"}

    lifetime_policy = str(metadata.get("lifetime_policy", "")).strip().lower()
    if lifetime_policy:
        return lifetime_policy in {"run", "session"}

    return bool(metadata.get("temporary"))


def _core_has_agent_blueprint(core: "Core", blueprint_ref: str) -> bool:
    has_blueprint = getattr(core, "has_agent_blueprint", None)
    if callable(has_blueprint):
        try:
            return bool(has_blueprint(blueprint_ref))
        except Exception:
            return False
    agents = getattr(core, "agents", {})
    return blueprint_ref in agents
