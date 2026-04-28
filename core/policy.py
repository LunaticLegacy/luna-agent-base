"""Execution graph engine for agents and tools.

The :class:`ExecutionGraph` is the central data structure that describes
how a swarm's agents and tools are wired together.  It supports:

* Three node types — :class:`Node` (base), :class:`AgentNode` (delegates to
  an agent), and :class:`ToolNode` (delegates to a tool).
* Directed edges with optional labels, conditions, and priorities.
* Validation against a runtime :class:`Core` to ensure every node binds to
  a real agent blueprint or registered tool.
* Projection to a pure "agent graph" that hides tool nodes for UI purposes.
* Python source-code generation so that graphs can be version-controlled.

Two module-level helpers are also provided:

* :func:`_node_is_transient` — determines whether a node is temporary.
* :func:`_core_has_agent_blueprint` — checks blueprint existence with
  graceful fallback.

Exports:
    - :class:`Node`
    - :class:`Edge`
    - :class:`AgentNode`
    - :class:`ToolNode`
    - :class:`ExecutionStep`
    - :class:`ExecutionGraph`
    - :func:`_node_is_transient`
    - :func:`_core_has_agent_blueprint`
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pprint import pformat
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING, Literal

from .results import ExecutionEvent, ExecutionState, GraphValidationResult

if TYPE_CHECKING:
    from .core import Core


@dataclass
class Node:
    """Base node definition for the execution graph.

    Attributes:
        node_id: Unique integer identifier.
        node_name: Human-readable name.
        next_node_ids: Outgoing adjacency list.
        metadata: Free-form metadata.
    """

    node_id: int
    node_name: str
    next_node_ids: List[int] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Edge:
    """Directed edge between two execution nodes.

    Attributes:
        from_node_id: Source node.
        to_node_id: Destination node.
        label: Optional human-readable label.
        condition: Optional routing condition expression.
        priority: Higher values are evaluated first when resolving outgoing edges.
    """

    from_node_id: int
    to_node_id: int
    label: Optional[str] = None
    condition: Optional[str] = None
    priority: int = 0


@dataclass(init=False)
class AgentNode(Node):
    """Graph node that delegates execution to a managed agent.

    Attributes:
        blueprint_ref: Identifier of the agent blueprint to instantiate.
        additional_prompt: Extra prompt text appended per execution.
        instance_policy: ``"singleton"`` (reuse one instance) or ``"per_call"``
            (fresh clone each time).
    """

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
        """Initialise an agent node.

        Args:
            node_id: Unique integer identifier.
            node_name: Human-readable name.
            metadata: Free-form metadata.
            blueprint_ref: Agent blueprint reference.
            additional_prompt: Extra prompt text.
            instance_policy: ``"singleton"`` or ``"per_call"``.
            agent_id: Deprecated alias for *blueprint_ref*.
        """
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
    """Graph node that delegates execution to a standard tool.

    Attributes:
        tool_name: Registered tool name to invoke.
        input_mapping: Optional mapping from payload keys to tool argument names.
    """

    tool_name: str = ""
    input_mapping: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionStep:
    """One step in a graph execution trace.

    Attributes:
        node_id: Executed node identifier.
        node_name: Human-readable node name.
        node_type: Class name of the node.
        input_payload: Payload received by the node.
        output_payload: Payload produced by the node.
        status: ``"ok"``, ``"failed"``, etc.
        error: Optional error message.
        branch: Branch label (for parallel branches).
    """

    node_id: int
    node_name: str
    node_type: str
    input_payload: Any
    output_payload: Any
    status: str = "ok"
    error: Optional[str] = None
    branch: Optional[str] = None


class ExecutionGraph:
    """Execution graph engine for agents and tools.

    Attributes:
        graph_name: Human-readable name.
        graph_kind: ``"execution"`` or ``"agent"`` (after projection).
        nodes: Map ``node_id -> Node``.
        edges: List of all :class:`Edge` objects.
        entry_node_id: First node to execute.
        exit_node_id: Last node in the graph.
    """

    def __init__(self, graph_name: str) -> None:
        """Initialise an empty graph.

        Args:
            graph_name: Human-readable name for the graph.
        """
        self.graph_name = graph_name
        self.graph_kind = "execution"
        self.nodes: Dict[int, Node] = {}
        self.edges: List[Edge] = []
        self.entry_node_id: Optional[int] = None
        self.exit_node_id: Optional[int] = None

    def add_node(self, node: Node) -> None:
        """Add a node to the graph.

        Args:
            node: The node instance to add.

        Raises:
            ValueError: If *node.node_id* already exists.
        """
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
        """Connect two nodes by id.

        Args:
            from_node_id: Source node.
            to_node_id: Destination node.
            label: Optional edge label.
            condition: Optional routing condition.
            priority: Higher values sort first.

        Raises:
            KeyError: If either node does not exist.
        """
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
        """Replace the outgoing edges for a node.

        Args:
            from_node_id: Node whose outgoing edges are replaced.
            to_node_ids: New ordered list of destination node IDs.

        Raises:
            KeyError: If *from_node_id* or any destination node does not exist.
        """
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
        """Remove one outgoing edge.

        Args:
            from_node_id: Source node.
            to_node_id: Destination node.

        Raises:
            KeyError: If *from_node_id* does not exist.
        """
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
        """Remove a node and detach all incoming edges.

        Also clears ``entry_node_id`` / ``exit_node_id`` if they pointed to
        the removed node.

        Args:
            node_id: The node to remove.

        Raises:
            KeyError: If the node does not exist.
        """
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
        """Project the execution graph into a pure agent graph.

        Tool nodes and intermediate routing nodes are elided; only
        :class:`AgentNode` instances are retained, with edges representing
        the transitive agent-to-agent routing.

        Returns:
            A new :class:`ExecutionGraph` with ``graph_kind == "agent"``.
        """
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
            """DFS through non-agent nodes to find the next reachable agents."""
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
        """Set the entry node for the graph.

        Args:
            node_id: The node that will be executed first.

        Raises:
            KeyError: If the node does not exist.
        """
        self._ensure_node_exists(node_id)
        self.entry_node_id = node_id

    def set_exit(self, node_id: int) -> None:
        """Set the exit node for the graph.

        Args:
            node_id: The node that marks the end of execution.

        Raises:
            KeyError: If the node does not exist.
        """
        self._ensure_node_exists(node_id)
        self.exit_node_id = node_id

    def _ensure_node_exists(self, node_id: int) -> None:
        """Defensive guard: raise if *node_id* is absent."""
        if node_id not in self.nodes:
            raise KeyError(f"Unknown node_id: {node_id}")

    def _allows_missing_binding(self, node: Node) -> bool:
        """Return whether a missing blueprint/tool binding is acceptable.

        Transient nodes are allowed to have dangling references because they
        may be generated dynamically and removed before execution.
        """
        metadata = node.metadata if isinstance(node.metadata, dict) else {}
        return _node_is_transient(metadata)

    def purge_transient_nodes(self) -> List[int]:
        """Remove transient nodes from the graph and return their ids.

        Returns:
            List of node IDs that were removed.
        """
        removed: List[int] = []
        for node_id, node in list(self.nodes.items()):
            metadata = node.metadata if isinstance(node.metadata, dict) else {}
            if _node_is_transient(metadata):
                self.remove_node(node_id)
                removed.append(node_id)
        return removed

    def validate(self, core: Optional["Core"] = None) -> GraphValidationResult:
        """Validate graph structure and runtime bindings.

        Checks performed:

        1. Structural checks — at least one node, entry node set, etc.
        2. Edge integrity — no dangling references or duplicates.
        3. Binding checks — every :class:`AgentNode` has a blueprint and every
           :class:`ToolNode` has a tool name.  When *core* is provided, the
           blueprint/tool is verified against the runtime registry.
        4. Transient-node downgrade — missing bindings on transient nodes
           become warnings instead of errors.

        Args:
            core: Optional runtime core for binding verification.

        Returns:
            A :class:`GraphValidationResult` with errors and warnings.
        """
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
        """Return whether the graph is ready for execution.

        Args:
            core: Optional runtime core for binding verification.

        Returns:
            ``True`` if validation produces no errors.
        """
        return self.validate(core).is_valid

    def is_complete(self, core: Optional["Core"] = None) -> bool:
        """Return whether the graph is complete enough for runtime use.

        Args:
            core: Optional runtime core for binding verification.

        Returns:
            ``True`` if validation produces no errors and no warnings.
        """
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
        """Execute the graph from its entry node.

        Args:
            core: The runtime :class:`Core`.
            initial_payload: Seed payload.
            rounds: Starting round counter.
            run_id: Optional run identifier.
            swarm_name: Name of the swarm package.
            event_sink: Optional live-event callback.

        Returns:
            The final :class:`ExecutionState`.
        """
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
        """Render the graph as a standalone Python module.

        Returns:
            Python source code that reconstructs the graph when executed.
        """
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
        """Create a shallow clone of the graph structure.

        Returns:
            A new :class:`ExecutionGraph` with copied nodes and edges.
        """
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
        """Emit Python source lines that reconstruct *node*."""
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
        """Return the outgoing edges for a node sorted by priority (descending).

        Args:
            node_id: The node whose outgoing edges are requested.

        Returns:
            Sorted list of :class:`Edge` objects.
        """
        return sorted(
            [edge for edge in self.edges if edge.from_node_id == node_id],
            key=lambda edge: edge.priority,
            reverse=True,
        )

    def _clone_node(self, node: Node) -> Node:
        """Create a shallow copy of *node* preserving its concrete type."""
        cloned = type(node)(
            node_id=node.node_id,
            node_name=node.node_name,
            metadata=dict(node.metadata),
            **self._node_specific_kwargs(node),
        )
        cloned.next_node_ids = list(node.next_node_ids)
        return cloned

    def _node_specific_kwargs(self, node: Node) -> Dict[str, Any]:
        """Return constructor kwargs specific to the concrete node type."""
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
        """Return whether an identical edge already exists."""
        return any(
            edge.from_node_id == from_node_id
            and edge.to_node_id == to_node_id
            and edge.label == label
            and edge.condition == condition
            for edge in self.edges
        )


def _node_is_transient(metadata: Dict[str, Any]) -> bool:
    """Determine whether a node's metadata marks it as transient.

    Transient nodes are expected to be short-lived and therefore missing
    runtime bindings are downgraded from errors to warnings.

    The check follows a precedence chain:

    1. ``metadata["runtime_transient"]`` — explicit boolean flag.
    2. ``metadata["node_lifecycle"]["persistence"]`` / ``["lifetime_policy"]``.
    3. ``metadata["persistence"]`` / ``metadata["lifetime_policy"]``.
    4. ``metadata["temporary"]`` — legacy boolean flag.

    Args:
        metadata: Node metadata dictionary.

    Returns:
        ``True`` if the node should be treated as transient.
    """
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
    """Check whether *core* knows about *blueprint_ref*.

    Prefers ``core.has_agent_blueprint`` if available (allows custom logic);
    falls back to a simple ``in`` check against ``core.agents``.

    Args:
        core: The runtime :class:`Core`.
        blueprint_ref: Agent blueprint identifier.

    Returns:
        ``True`` if the blueprint exists.
    """
    has_blueprint = getattr(core, "has_agent_blueprint", None)
    if callable(has_blueprint):
        try:
            return bool(has_blueprint(blueprint_ref))
        except Exception:
            return False
    agents = getattr(core, "agents", {})
    return blueprint_ref in agents
