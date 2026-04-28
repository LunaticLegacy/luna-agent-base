"""Atomic graph mutation transactions.

Provides ``GraphTransaction``, which stages mutations against a working
clone of an ExecutionGraph, validates the result, and only then copies
the accepted state back to the live graph.  During commit, affected
agent blueprints are quarantined and drained so that in-flight rounds
do not observe a partially-mutated graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .policy import AgentNode, ExecutionGraph


@dataclass
class GraphMutationRecord:
    """One logical graph mutation staged inside a transaction.

    Attributes:
        action: Human-readable mutation name (e.g. ``"architecture_patch"``).
        detail: Arbitrary serialisable payload describing the change.
        author: Identity that proposed the mutation.
        reason: Free-form justification string.
    """

    action: str
    detail: Dict[str, Any] = field(default_factory=dict)
    author: str = ""
    reason: str = ""


@dataclass
class GraphTransactionResult:
    """Committed graph mutation result.

    Attributes:
        graph_name: Name of the mutated graph.
        revision: Optional revision counter after commit.
        runtime_path: Optional filesystem path to the persisted runtime graph.
        revision_path: Optional filesystem path to the revision backup.
        change: Serialisable summary of the mutation.
    """

    graph_name: str
    revision: Optional[int] = None
    runtime_path: Optional[str] = None
    revision_path: Optional[str] = None
    change: Dict[str, Any] = field(default_factory=dict)


class GraphTransaction:
    """Prepare, validate, and commit a graph mutation atomically.

    The transaction workflow is:
        1. ``prepare`` — apply the mutation to a *working* clone and validate.
        2. ``commit`` — quarantine affected agents, copy state to the live
           graph, persist, then restore agents.
        3. ``rollback`` — discard the working clone and reset state.

    Args:
        graph: The live ExecutionGraph to mutate.
        core: Optional Core reference for agent-pool and persistence hooks.
    """

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
        """Return the working clone (safe to inspect before commit)."""
        return self._working_graph

    def prepare(
        self,
        mutation: GraphMutationRecord,
        mutate: Callable[[ExecutionGraph], None],
    ) -> ExecutionGraph:
        """Stage *mutate* against the working graph and validate.

        Raises:
            ValueError: If validation of the working graph fails.
        """
        mutate(self._working_graph)
        validation = self._working_graph.validate(self.core)
        if not validation.is_valid:
            detail = "; ".join(validation.errors)
            raise ValueError(f"graph transaction '{mutation.action}' left graph invalid: {detail}")
        self._mutations.append(mutation)
        self._prepared = True
        return self._working_graph

    async def commit(self) -> GraphTransactionResult:
        """Commit the prepared mutation to the live graph.

        Steps:
            1. Quarantine and drain affected agent blueprints.
            2. Snapshot the current graph, copy working state over.
            3. Persist the change via the core hook.
            4. Restore quarantined agents.

        Raises:
            ValueError: If called before ``prepare()``.
            Exception: Re-raised from persistence; live graph is rolled back.
        """
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
            # Rollback on persistence failure so the live graph stays consistent.
            self._copy_graph_state(self.graph, previous)
            self._unquarantine(affected_blueprints)
            raise

        self._unquarantine(affected_blueprints)
        return persistence

    def rollback(self) -> None:
        """Discard the working clone and clear staged mutations."""
        self._working_graph = self.graph.clone()
        self._mutations.clear()
        self._prepared = False

    async def _quarantine_and_drain(self, blueprint_refs: List[str]) -> None:
        """Temporarily isolate affected blueprints so no active rounds race."""
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
        """Restore quarantined blueprints to the active pool."""
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
        """Compare previous vs working graph to find changed agent nodes."""
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
        """Delegate persistence to the core hook, if available."""
        if self.core is None:
            return GraphTransactionResult(graph_name=self.graph.graph_name, change=change)
        persist = getattr(self.core, "persist_execution_graph", None)
        if not callable(persist):
            return GraphTransactionResult(graph_name=self.graph.graph_name, change=change)
        try:
            result = persist(graph=self.graph, change=change)
        except TypeError:
            # Back-compat: some older hooks take no arguments.
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
        """Summarise the transaction for audit trails."""
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
        """Deep-copy all mutable state from *source* into *target*.

        This is used both for commit (working -> live) and rollback
        (snapshot -> live) so the target object identity stays stable.
        """
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
