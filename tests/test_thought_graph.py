from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from core.agent import Agent
from core.cognitive import (
    CognitiveEdge,
    CognitiveGraph,
    CognitiveNode,
    CognitiveNodeType,
    CognitiveRelationType,
)


class ThoughtGraphTest(unittest.TestCase):
    def test_schedulable_subgraph_descriptor_exports_context(self) -> None:
        graph = CognitiveGraph(graph_id="shared")
        fact = graph.add_node(
            CognitiveNode(
                node_id="fact-1",
                node_type=CognitiveNodeType.FACT,
                content="The swarm has a shared thought graph.",
                confidence=0.95,
                source="tester",
            )
        )
        evidence = graph.add_node(
            CognitiveNode(
                node_id="evidence-1",
                node_type=CognitiveNodeType.EVIDENCE,
                content="core.cognitive exports graph snapshots.",
                confidence=0.9,
                source="tester",
            )
        )
        graph.add_edge(
            CognitiveEdge(
                source_id=evidence.node_id,
                target_id=fact.node_id,
                relation=CognitiveRelationType.VERIFIES,
            )
        )

        descriptor, subgraph = graph.describe_subgraph(
            owner_agent="reviewer",
            query="shared thought graph",
            purpose="Verify graph context",
            expected_next_information="Find missing evidence",
        )
        exported = graph.export_subgraph_for_llm(descriptor, subgraph)

        self.assertEqual(descriptor.owner_agent, "reviewer")
        self.assertEqual(descriptor.purpose, "Verify graph context")
        self.assertIn("fact-1", subgraph.nodes)
        self.assertIn("evidence-1", subgraph.nodes)
        self.assertIn("Schedulable Thought Subgraph", exported)
        self.assertIn("verifies", exported)

    def test_extended_node_and_relation_taxonomy_round_trips(self) -> None:
        node = CognitiveNode(
            node_type=CognitiveNodeType.COUNTEREVIDENCE,
            content="A counterexample exists.",
            confidence=0.4,
        )
        edge = CognitiveEdge(
            source_id="counter",
            target_id="claim",
            relation=CognitiveRelationType.DISPROVES,
        )

        self.assertEqual(CognitiveNode.from_dict(node.to_dict()).node_type, CognitiveNodeType.COUNTEREVIDENCE)
        self.assertEqual(CognitiveEdge.from_dict(edge.to_dict()).relation, CognitiveRelationType.DISPROVES)

    def test_private_workspace_snapshot_stays_agent_local(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir)
            shared = CognitiveGraph(graph_id="shared")
            private = CognitiveGraph(graph_id="agent_reviewer")
            private.add_node(
                CognitiveNode(
                    node_type=CognitiveNodeType.HYPOTHESIS,
                    content="Private draft hypothesis",
                    source="reviewer",
                )
            )
            agent = Agent(
                agent_id="reviewer",
                llm_handler=object(),
                character_prompt="review",
                cognitive_graph=private,
                workspace_root=workspace_root,
            )

            agent.persist_private_thought_snapshot()
            snapshot_path = workspace_root / ".angelus_private" / "manual" / "reviewer" / "cognitive_graph_snapshot.json"

            self.assertTrue(snapshot_path.exists())
            self.assertIn("Private draft hypothesis", snapshot_path.read_text(encoding="utf-8"))
            self.assertEqual(shared.nodes, {})

    def test_private_workspace_summary_is_run_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir)
            agent = Agent(
                agent_id="reviewer",
                llm_handler=object(),
                character_prompt="review",
                workspace_root=workspace_root,
            )
            agent.set_run_id("run-a")
            run_a_dir = agent.private_workspace_dir
            run_a_dir.mkdir(parents=True)
            (run_a_dir / "notes.txt").write_text("old task secret", encoding="utf-8")

            agent.set_run_id("run-b")

            self.assertNotIn("old task secret", agent.summarize_private_workspace())


if __name__ == "__main__":
    unittest.main()
