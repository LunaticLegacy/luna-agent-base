from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..cognitive import CognitiveGraph, CognitiveSubgraphDescriptor, merge_cognitive_graphs
from ..context_graph import ContextEntry, ContextEntryType, ContextGraph, ContextReference, ContextRelation
from ..task_graph import TaskGraph


class CognitiveRuntimeMixin:
    """Shared cognitive-graph helpers for a runtime core."""

    def merge_agent_cognitive_graph(self, agent_id: str) -> None:
        agent = self.agents.get(agent_id)
        if agent is None:
            return
        agent_cg = getattr(agent, "cognitive_graph", None)
        if agent_cg is None or not isinstance(agent_cg, CognitiveGraph):
            return
        merge_cognitive_graphs(self.swarm_cognitive_graph, agent_cg)

    def get_cognitive_graph_export(self, query: Optional[str] = None, max_nodes: int = 20) -> str:
        return self.swarm_cognitive_graph.export_for_llm(query=query, max_nodes=max_nodes)

    def schedule_thought_subgraph(
        self,
        *,
        agent_id: str = "",
        query: Optional[str] = None,
        seed_ids: Optional[List[str]] = None,
        purpose: str = "",
        expected_next_information: str = "",
        max_nodes: int = 16,
    ) -> tuple[CognitiveSubgraphDescriptor, CognitiveGraph]:
        if agent_id:
            for existing in self.active_thought_subgraphs.values():
                if existing.owner_agent == agent_id and existing.status == "active":
                    existing.status = "retired"
        descriptor, subgraph = self.swarm_cognitive_graph.describe_subgraph(
            owner_agent=agent_id,
            query=query,
            seed_ids=seed_ids,
            purpose=purpose,
            expected_next_information=expected_next_information,
            max_nodes=max_nodes,
        )
        self.active_thought_subgraphs[descriptor.subgraph_id] = descriptor
        return descriptor, subgraph

    def retire_thought_subgraph(self, subgraph_id: str) -> bool:
        descriptor = self.active_thought_subgraphs.get(subgraph_id)
        if descriptor is None:
            return False
        descriptor.status = "retired"
        return True

    def get_private_workspace_summary(self, agent_id: str) -> str:
        agent = self.agents.get(agent_id)
        summarize = getattr(agent, "summarize_private_workspace", None)
        if callable(summarize):
            return str(summarize())
        return "No private workspace summary available."

    def set_current_run_id(self, run_id: Optional[str]) -> None:
        self.current_run_id = str(run_id).strip() if run_id else None
        for agent in self.agents.values():
            set_run_id = getattr(agent, "set_run_id", None)
            if callable(set_run_id):
                set_run_id(self.current_run_id)

    def build_thought_context_export(
        self,
        *,
        agent_id: str,
        query: Optional[str] = None,
        purpose: str = "",
        max_nodes: int = 16,
    ) -> str:
        main_graph = self.build_context_graph_export(
            agent_id=agent_id,
            query=query,
            purpose=purpose or "Continue the current agent task using relevant shared reasoning.",
            max_nodes=max_nodes,
        )
        descriptor, subgraph = self.schedule_thought_subgraph(
            agent_id=agent_id,
            query=query,
            purpose=purpose or "Continue the current agent task using relevant shared reasoning.",
            expected_next_information="Identify missing facts, uncertain claims, and useful next evidence.",
            max_nodes=max_nodes,
        )
        subgraph_export = self.swarm_cognitive_graph.export_subgraph_for_llm(descriptor, subgraph)
        private_summary = self.get_private_workspace_summary(agent_id)
        return (
            "## Swarm Thought Context\n\n"
            "Use the shared graph as public reasoning state. Use the active subgraph as the current "
            "schedulable slice. Treat private workspace notes as agent-local context; only promote "
            "private information by emitting explicit thought graph nodes and relations.\n\n"
            "### Main Shared Graph Summary\n"
            f"{main_graph}\n\n"
            "### Active Schedulable Subgraph\n"
            f"{subgraph_export}\n\n"
            "### Private Workspace Summary\n"
            f"{private_summary}\n\n"
            "### Thought Graph Output Contract\n"
            "When you discover reusable reasoning, include a <cognitive_graph> JSON block with nodes "
            "and edges. Prefer node types fact, evidence, hypothesis, guess, claim, question, "
            "assumption, decision, risk, counterevidence, and tool_result. Prefer relations supports, "
            "opposes, derives_from, leads_to, depends_on, questions, refines, verifies, disproves, "
            "and speculates."
        )

    def build_context_graph_export(
        self,
        *,
        agent_id: str,
        query: Optional[str] = None,
        purpose: str = "",
        max_nodes: int = 16,
    ) -> str:
        descriptor, subgraph = self.swarm_cognitive_graph.describe_subgraph(
            owner_agent=agent_id,
            query=query,
            purpose=purpose or "General thought graph context",
            expected_next_information="Identify missing facts, uncertain claims, and useful next evidence.",
            max_nodes=max_nodes,
        )
        context_graph, anchor_ids = ContextGraph.from_cognitive_graph(
            subgraph,
            query=query,
            seed_ids=descriptor.root_node_ids,
            purpose=purpose,
            max_nodes=max_nodes,
        )
        system_entry = ContextEntry(
            id=f"system:{agent_id}",
            summary="Swarm thought context instructions",
            content=(
                "Use the shared graph as public reasoning state. Use the active subgraph as the current "
                "schedulable slice. Treat private workspace notes as agent-local context; only promote "
                "private information by emitting explicit thought graph nodes and relations."
            ),
            token_count=0,
            timestamp=0.0,
            entry_type=ContextEntryType.SYSTEM,
            metadata={"agent_id": agent_id, "purpose": purpose},
            is_retained=True,
        )
        context_graph.add_entry(system_entry)
        private_summary = self.get_private_workspace_summary(agent_id)
        workspace_entry = ContextEntry(
            id=f"workspace:{agent_id}",
            summary="Private workspace summary",
            content=private_summary,
            token_count=0,
            timestamp=0.0,
            entry_type=ContextEntryType.WORKSPACE,
            metadata={"agent_id": agent_id, "swarm": self.agent_name},
            is_retained=True,
        )
        context_graph.add_entry(workspace_entry)

        anchor_id = anchor_ids[0] if anchor_ids else next(iter(context_graph.entries.keys()), "")
        if anchor_id and anchor_id in context_graph.entries:
            context_graph.add_reference(
                system_entry.id,
                ContextReference(
                    target_id=anchor_id,
                    relation=ContextRelation.REFERENCES,
                    target_hash=context_graph.entries[anchor_id].content_hash(),
                    fallback_inline=context_graph.entries[anchor_id].summary,
                    weight=1.2,
                ),
            )
        prompt = context_graph.assemble_prompt(
            anchor_id=anchor_id or None,
            token_budget=max(1200, max_nodes * 180),
            title="Swarm Context Graph",
        )
        return prompt

    def get_cognitive_graph_snapshot(self) -> Dict[str, Any]:
        snapshot = self.swarm_cognitive_graph.snapshot()
        snapshot["active_subgraphs"] = [
            descriptor.to_dict()
            for descriptor in self.active_thought_subgraphs.values()
            if descriptor.status == "active"
        ]
        if not snapshot.get("edges"):
            snapshot["edges"] = self._synthesize_thought_graph_edges(snapshot)
        return snapshot

    def _synthesize_thought_graph_edges(self, snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
        nodes = snapshot.get("nodes") or []
        if len(nodes) < 2:
            return []

        node_ids = {str(node.get("node_id")) for node in nodes if node.get("node_id")}
        node_by_id = {str(node.get("node_id")): node for node in nodes if node.get("node_id")}
        active_subgraphs = snapshot.get("active_subgraphs") or []
        edges: List[Dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()

        def add_edge(source_id: str, target_id: str, relation: str, description: str, strength: float) -> None:
            if not source_id or not target_id or source_id == target_id:
                return
            key = (source_id, target_id, relation)
            if key in seen:
                return
            seen.add(key)
            edges.append(
                {
                    "edge_id": f"synth_{source_id[:8]}_{target_id[:8]}_{relation}",
                    "source_id": source_id,
                    "target_id": target_id,
                    "relation": relation,
                    "strength": strength,
                    "description": description,
                    "metadata": {
                        "synthesized": True,
                        "source": "runtime-fallback",
                    },
                }
            )

        for subgraph in active_subgraphs:
            roots = [str(node_id) for node_id in (subgraph.get("root_node_ids") or []) if str(node_id) in node_ids]
            frontier = [str(node_id) for node_id in (subgraph.get("frontier_node_ids") or []) if str(node_id) in node_ids]
            if not roots or not frontier:
                continue
            purpose = str(subgraph.get("purpose") or subgraph.get("subgraph_id") or "active subgraph")
            for root_id in roots:
                for frontier_id in frontier:
                    add_edge(
                        root_id,
                        frontier_id,
                        "depends_on",
                        f"{purpose}: root to frontier",
                        0.65,
                    )

        if not edges:
            ordered_nodes = sorted(
                node_by_id.values(),
                key=lambda node: (
                    str(node.get("created_at") or ""),
                    str(node.get("source") or ""),
                    int(node.get("version") or 0),
                    str(node.get("node_id") or ""),
                ),
            )
            for current, nxt in zip(ordered_nodes, ordered_nodes[1:]):
                add_edge(
                    str(current.get("node_id") or ""),
                    str(nxt.get("node_id") or ""),
                    "leads_to",
                    "Chronological fallback relation",
                    0.45,
                )

        return edges

    def reset_runtime_state(self) -> None:
        for agent in self.agents.values():
            reset_runtime_state = getattr(agent, "reset_runtime_state", None)
            if callable(reset_runtime_state):
                reset_runtime_state()
                continue
            agent.reset_context()
        self.swarm_cognitive_graph = CognitiveGraph(graph_id=f"swarm_{self.agent_name}")
        self.active_thought_subgraphs.clear()
        self.current_run_id = None
