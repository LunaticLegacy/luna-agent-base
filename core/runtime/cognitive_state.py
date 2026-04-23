from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..cognitive import CognitiveGraph, CognitiveSubgraphDescriptor, merge_cognitive_graphs
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
        main_graph = self.swarm_cognitive_graph.export_for_llm(query=query, max_nodes=12)
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

    def get_cognitive_graph_snapshot(self) -> Dict[str, Any]:
        snapshot = self.swarm_cognitive_graph.snapshot()
        snapshot["active_subgraphs"] = [
            descriptor.to_dict()
            for descriptor in self.active_thought_subgraphs.values()
            if descriptor.status == "active"
        ]
        return snapshot

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

