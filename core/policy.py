from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .results import ExecutionState, GraphValidationResult

if TYPE_CHECKING:
    from .core import Core


@dataclass
class Node:
    """Base node definition for the execution graph."""

    node_id: int
    node_name: str
    next_node_ids: List[int] = field(default_factory=list)


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


class ExecutionGraph:
    """Execution graph engine for agents and tools."""

    def __init__(self, graph_name: str) -> None:
        self.graph_name = graph_name
        self.nodes: Dict[int, Node] = {}
        self.entry_node_id: Optional[int] = None
        self.exit_node_id: Optional[int] = None

    def add_node(self, node: Node) -> None:
        """Add a node to the graph."""
        if node.node_id in self.nodes:
            raise ValueError(f"Duplicate node_id: {node.node_id}")
        self.nodes[node.node_id] = node

    def add_edge(self, from_node_id: int, to_node_id: int) -> None:
        """Connect two nodes by id."""
        if from_node_id not in self.nodes:
            raise KeyError(f"Unknown from_node_id: {from_node_id}")
        if to_node_id not in self.nodes:
            raise KeyError(f"Unknown to_node_id: {to_node_id}")
        self.nodes[from_node_id].next_node_ids.append(to_node_id)

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

    def validate(self, core: Optional["Core"] = None) -> GraphValidationResult:
        """Validate graph structure and runtime bindings."""
        errors: List[str] = []
        warnings: List[str] = []

        if not self.nodes:
            errors.append("Graph has no nodes.")
        if self.entry_node_id is None:
            errors.append("Graph entry node is not set.")
        if self.exit_node_id is None:
            warnings.append("Graph exit node is not set.")

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
                    errors.append(
                        f"Agent node {node.node_id} references missing agent '{node.agent_id}'."
                    )

            if isinstance(node, ToolNode):
                if not node.tool_name:
                    errors.append(f"Tool node {node.node_id} has no tool_name.")
                elif core is not None and node.tool_name not in core.tools:
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
    ) -> ExecutionState:
        """Execute the graph from its entry node."""
        from .executor import GraphExecutor

        executor = GraphExecutor()
        return await executor.execute(self, core, initial_payload, rounds=rounds)
