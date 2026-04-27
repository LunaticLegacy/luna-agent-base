from __future__ import annotations

import unittest
from types import SimpleNamespace

from core.cognitive import CognitiveGraph
from core.fault_tolerance import ArchitectureRegulator, FailureEvent
from core.executor_parts.engine import GraphExecutor
from core.policy import AgentNode, ExecutionGraph


class DummyAgent:
    async def round_call(self, *, rounds: int, user_message: str, additional_prompt=None):
        return SimpleNamespace(
            assistant_message=f"round-{rounds}:{user_message}",
            raw_response=None,
        )


class DummyCore:
    def __init__(self) -> None:
        self.agents = {
            "quarantined": DummyAgent(),
            "healthy": DummyAgent(),
        }
        self.tools = {}
        self.swarm_cognitive_graph = CognitiveGraph(graph_id="shared")
        self.current_run_id = None

    def get_agent(self, agent_id: str):
        return self.agents[agent_id]

    def merge_agent_cognitive_graph(self, agent_id: str) -> None:
        return None

    def get_cognitive_graph_export(self, query=None, max_nodes=20):
        return "cognitive export"

    def cleanup_transient_execution_nodes(self, *, graph=None):
        if graph is None:
            return []
        return graph.purge_transient_nodes()


class FaultToleranceTest(unittest.TestCase):
    def test_architecture_regulator_quarantines_node_with_fallback(self) -> None:
        graph = ExecutionGraph("demo")
        graph.add_node(
            AgentNode(node_id=1,
                node_name="flaky",
                agent_id="quarantined",
                metadata={"failure_policy": {"fallback_node_id": 2}})
        )
        graph.add_node(
            AgentNode(node_id=2,
                node_name="fallback",
                agent_id="healthy")
        )

        regulator = ArchitectureRegulator()
        regulation = regulator.regulate(
            FailureEvent(
                run_id="run-1",
                swarm_name="demo",
                graph_revision=1,
                failure_scope="node",
                failure_kind="tool_error",
                node_id=1,
                node_name="flaky",
                node_type="AgentNode",
                message="tool failed",
                state_snapshot={"payload": "x"},
            ),
            graph=graph,
        )

        self.assertEqual(regulation.action, "reroute_to_fallback")
        self.assertTrue(graph.nodes[1].metadata["fault_tolerance"]["quarantined"])
        self.assertEqual(graph.nodes[1].metadata["fault_tolerance"]["fallback_node_id"], 2)

    def test_executor_skips_quarantined_node_and_continues(self) -> None:
        graph = ExecutionGraph("demo")
        graph.add_node(
            AgentNode(node_id=1,
                node_name="quarantined",
                agent_id="quarantined",
                metadata={
                    "fault_tolerance": {"quarantined": True, "fallback_node_id": 2, "last_failure_message": "quarantined"},
                    "runtime_transient": True,
                    "persistence": "transient",
                    "lifetime_policy": "run",
                })
        )
        graph.add_node(
            AgentNode(node_id=2,
                node_name="healthy",
                agent_id="healthy")
        )
        graph.set_entry(1)
        graph.set_exit(2)

        core = DummyCore()
        executor = GraphExecutor()
        events = []

        async def _run():
            return await executor.execute(
                graph,
                core,
                {"task": "demo"},
                event_sink=events.append,
            )

        import asyncio

        state = asyncio.run(_run())

        event_types = [event.event_type for event in events]
        self.assertIn("node.skipped", event_types)
        self.assertIn("node.started", event_types)
        self.assertIn("node.completed", event_types)
        # Envelope mode: payload is not overwritten by agent output; outputs live in metadata
        self.assertEqual(state.payload, {"task": "demo"})
        outputs = state.metadata.get("outputs", {})
        self.assertIn(str(2), outputs)
        self.assertNotIn(1, graph.nodes)
        self.assertIn(2, graph.nodes)


if __name__ == "__main__":
    unittest.main()
