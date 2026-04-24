from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .policy import AgentNode, ExecutionGraph


@dataclass
class GraphMutationRecord:
    """One logical graph mutation staged inside a transaction."""

    action: str
    detail: Dict[str, Any] = field(default_factory=dict)
    author: str = ""
    reason: str = ""


@dataclass
class GraphTransactionResult:
    """Committed graph mutation result."""

    graph_name: str
    revision: Optional[int] = None
    runtime_path: Optional[str] = None
    revision_path: Optional[str] = None
    change: Dict[str, Any] = field(default_factory=dict)


class GraphTransaction:
    """Prepare, validate, and commit a graph mutation atomically."""

    def __init__(
        self,
        graph: ExecutionGraph,
        *,
        core: Any = None,
    ) -> None:
        self.graph = graph
        self.core = core
        self._working_graph = graph.clone()
        self._mutations: List[GraphMutationRecord] = []
        self._prepared = False

    @property
    def working_graph(self) -> ExecutionGraph:
        return self._working_graph

    def prepare(
        self,
        mutation: GraphMutationRecord,
        mutate: Callable[[ExecutionGraph], None],
    ) -> ExecutionGraph:
        mutate(self._working_graph)
        validation = self._working_graph.validate(self.core)
        if not validation.is_valid:
            detail = "; ".join(validation.errors)
            raise ValueError(f"graph transaction '{mutation.action}' left graph invalid: {detail}")
        self._mutations.append(mutation)
        self._prepared = True
        return self._working_graph

    async def commit(self) -> GraphTransactionResult:
        if not self._prepared:
            raise ValueError("graph transaction commit called before prepare().")

        affected_blueprints = self._affected_agent_blueprints()
        await self._quarantine_and_drain(affected_blueprints)
        previous = self.graph.clone()
        self._copy_graph_state(self.graph, self._working_graph)

        change = self._build_change_payload(affected_blueprints)
        try:
            persistence = self._persist_change(change)
        except Exception:
            self._copy_graph_state(self.graph, previous)
            self._unquarantine(affected_blueprints)
            raise

        self._unquarantine(affected_blueprints)
        return persistence

    def rollback(self) -> None:
        self._working_graph = self.graph.clone()
        self._mutations.clear()
        self._prepared = False

    async def _quarantine_and_drain(self, blueprint_refs: List[str]) -> None:
        if self.core is None:
            return
        pool = getattr(self.core, "agent_instance_pool", None)
        if pool is None:
            return
        quarantine = getattr(pool, "quarantine", None)
        drain = getattr(pool, "drain", None)
        for blueprint_ref in blueprint_refs:
            if callable(quarantine):
                quarantine(blueprint_ref)
        for blueprint_ref in blueprint_refs:
            if callable(drain):
                await drain(blueprint_ref, timeout=2.0)

    def _unquarantine(self, blueprint_refs: List[str]) -> None:
        if self.core is None:
            return
        pool = getattr(self.core, "agent_instance_pool", None)
        if pool is None:
            return
        restore = getattr(pool, "restore", None)
        for blueprint_ref in blueprint_refs:
            if callable(restore):
                restore(blueprint_ref)

    def _affected_agent_blueprints(self) -> List[str]:
        affected: List[str] = []
        previous_agents = {
            node.node_id: node.blueprint_ref
            for node in self.graph.nodes.values()
            if isinstance(node, AgentNode)
        }
        current_agents = {
            node.node_id: node.blueprint_ref
            for node in self._working_graph.nodes.values()
            if isinstance(node, AgentNode)
        }
        for node_id, blueprint_ref in previous_agents.items():
            if node_id not in current_agents or current_agents.get(node_id) != blueprint_ref:
                affected.append(blueprint_ref)
        return list(dict.fromkeys([item for item in affected if item]))

    def _persist_change(self, change: Dict[str, Any]) -> GraphTransactionResult:
        if self.core is None:
            return GraphTransactionResult(graph_name=self.graph.graph_name, change=change)
        persist = getattr(self.core, "persist_execution_graph", None)
        if not callable(persist):
            return GraphTransactionResult(graph_name=self.graph.graph_name, change=change)
        try:
            result = persist(graph=self.graph, change=change)
        except TypeError:
            result = persist()
        if isinstance(result, dict):
            return GraphTransactionResult(
                graph_name=self.graph.graph_name,
                revision=result.get("revision"),
                runtime_path=result.get("runtime_path"),
                revision_path=result.get("revision_path"),
                change=change,
            )
        return GraphTransactionResult(graph_name=self.graph.graph_name, change=change)

    def _build_change_payload(self, affected_blueprints: List[str]) -> Dict[str, Any]:
        latest = self._mutations[-1]
        return {
            "action": latest.action,
            "author": latest.author,
            "reason": latest.reason,
            "detail": dict(latest.detail),
            "mutation_count": len(self._mutations),
            "affected_blueprints": list(affected_blueprints),
        }

    @staticmethod
    def _copy_graph_state(target: ExecutionGraph, source: ExecutionGraph) -> None:
        target.graph_name = source.graph_name
        target.graph_kind = source.graph_kind
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
