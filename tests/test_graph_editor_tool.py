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


def _build_graph() -> ExecutionGraph:
    graph = ExecutionGraph("test")
    graph.add_node(Node(node_id=1, node_name="one"))
    graph.add_node(Node(node_id=2, node_name="two"))
    graph.set_entry(1)
    graph.set_exit(2)
    return graph


if __name__ == "__main__":
    unittest.main()
