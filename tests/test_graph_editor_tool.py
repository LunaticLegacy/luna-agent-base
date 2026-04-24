from __future__ import annotations

import asyncio
import unittest

from core.policy import ExecutionGraph, Node
from core.toodefl import ToolContext
from tools.graph_editor_tool import GraphEditorTool


class FailingPersistCore:
    agents = {}
    tools = {}

    def persist_execution_graph(self):
        raise RuntimeError("persist failed")


class NoopPersistCore:
    def __init__(self) -> None:
        self.agents = {"agent-3": object()}
        self.tools = {"tool-4": object()}

    def persist_execution_graph(self):
        return None

    def record_runtime_change(self, **kwargs):
        return None


class GraphEditorToolTest(unittest.TestCase):
    def test_graph_editor_requires_mutation_capability(self) -> None:
        graph = _build_graph()
        tool = GraphEditorTool()

        with self.assertRaises(PermissionError):
            asyncio.run(
                tool.execute(
                    {"action": "add_edge", "from_node_id": 1, "to_node_id": 2},
                    context=ToolContext(graph=graph),
                )
            )

    def test_graph_editor_rolls_back_when_persist_fails(self) -> None:
        graph = _build_graph()
        tool = GraphEditorTool()

        with self.assertRaises(RuntimeError):
            asyncio.run(
                tool.execute(
                    {"action": "add_edge", "from_node_id": 1, "to_node_id": 2},
                    context=ToolContext(
                        graph=graph,
                        core=FailingPersistCore(),
                        capabilities={"graph_mutation"},
                    ),
                )
            )

        self.assertEqual(graph.nodes[1].next_node_ids, [])
        self.assertEqual(graph.edges, [])

    def test_graph_editor_supports_persistent_and_transient_lifecycle(self) -> None:
        graph = _build_graph()
        tool = GraphEditorTool()

        asyncio.run(
            tool.execute(
                {
                    "action": "add_agent_node",
                    "node_id": 3,
                    "node_name": "persistent-agent",
                    "agent_id": "agent-3",
                    "next_node_ids": [],
                    "persistence": "persistent",
                    "lifetime_policy": "manual",
                },
                context=ToolContext(
                    graph=graph,
                    core=NoopPersistCore(),
                    capabilities={"graph_mutation"},
                ),
            )
        )

        self.assertFalse(graph.nodes[3].metadata["runtime_transient"])
        self.assertEqual(graph.nodes[3].metadata["persistence"], "persistent")
        self.assertEqual(graph.nodes[3].metadata["lifetime_policy"], "manual")
        self.assertEqual(graph.nodes[3].metadata["node_lifecycle"]["persistence"], "persistent")

        asyncio.run(
            tool.execute(
                {
                    "action": "add_tool_node",
                    "node_id": 4,
                    "node_name": "temporary-tool",
                    "tool_name": "tool-4",
                    "next_node_ids": [],
                    "runtime_transient": True,
                },
                context=ToolContext(
                    graph=graph,
                    core=NoopPersistCore(),
                    capabilities={"graph_mutation"},
                ),
            )
        )

        self.assertTrue(graph.nodes[4].metadata["runtime_transient"])
        self.assertEqual(graph.nodes[4].metadata["persistence"], "transient")
        self.assertEqual(graph.nodes[4].metadata["lifetime_policy"], "run")


def _build_graph() -> ExecutionGraph:
    graph = ExecutionGraph("test")
    graph.add_node(Node(node_id=1, node_name="one"))
    graph.add_node(Node(node_id=2, node_name="two"))
    graph.set_entry(1)
    graph.set_exit(2)
    return graph


if __name__ == "__main__":
    unittest.main()
