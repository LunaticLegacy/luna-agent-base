from __future__ import annotations

import asyncio
import unittest

from modules.llm_fetcher.thinking_graph import (
    ThinkingEdgeType,
    ThinkingGraph,
    ThinkingNodeType,
)


class ThinkingGraphSerializationTest(unittest.TestCase):
    def test_round_trip_preserves_nodes_edges_and_transactions(self) -> None:
        async def build_graph() -> ThinkingGraph:
            graph = ThinkingGraph()
            goal_id = await graph.add_node(
                node_type=ThinkingNodeType.GOAL,
                info="Ship the runtime graph split",
                tags=["runtime", "api"],
                created_by="tester",
                confidence=0.9,
                description="top-level goal",
                payload={"priority": "high"},
            )
            plan_id = await graph.add_node(
                node_type=ThinkingNodeType.PLAN,
                info="Split the graph endpoints",
                tags=["api"],
                created_by="tester",
                confidence=0.85,
            )
            step_id = await graph.add_node(
                node_type=ThinkingNodeType.STEP,
                info="Add execution and thinking graph endpoints",
                tags=["api"],
                created_by="tester",
                confidence=0.8,
            )
            action_id = await graph.add_node(
                node_type=ThinkingNodeType.ACTION,
                info="Update the REST surface",
                tags=["api"],
                created_by="tester",
                confidence=0.8,
            )
            await graph.add_edge(
                edge_type=ThinkingEdgeType.LEADS_TO,
                source_id=goal_id,
                target_id=plan_id,
                created_by="tester",
                description="goal drives planning",
                strength=0.9,
            )
            await graph.add_edge(
                edge_type=ThinkingEdgeType.PRODUCES,
                source_id=plan_id,
                target_id=step_id,
                created_by="tester",
                description="plan expands into steps",
                strength=0.85,
            )
            await graph.add_edge(
                edge_type=ThinkingEdgeType.LEADS_TO,
                source_id=step_id,
                target_id=action_id,
                created_by="tester",
                description="step drives execution",
                strength=0.75,
            )
            return graph

        graph = asyncio.run(build_graph())
        payload = graph.serialize()
        restored = ThinkingGraph.from_dict(payload)

        self.assertEqual(restored.version, graph.version)
        self.assertEqual(len(restored.node_dict), len(graph.node_dict))
        self.assertEqual(len(restored.edge_dict), len(graph.edge_dict))
        self.assertEqual(len(restored.transaction_log), len(graph.transaction_log))
        self.assertEqual(restored.node_dict[0].node_type, ThinkingNodeType.GOAL)
        self.assertEqual(restored.edge_dict[4].edge_type, ThinkingEdgeType.LEADS_TO)
        self.assertEqual(restored.node_dict[0].payload["priority"], "high")
        self.assertEqual(payload["format"], "thinking-graph/config")
        self.assertEqual(payload["schema_version"], "1.0")


if __name__ == "__main__":
    unittest.main()
