from __future__ import annotations

import asyncio
import builtins
import unittest
from unittest.mock import patch

from core.config import AgentConfig
from core.core import Core
from core.policy import AgentNode, ExecutionGraph, Node


def _build_graph() -> ExecutionGraph:
    graph = ExecutionGraph("boundary-test")
    graph.add_node(Node(node_id=1, node_name="start"))
    graph.add_node(Node(node_id=2, node_name="end"))
    graph.add_edge(1, 2)
    graph.set_entry(1)
    graph.set_exit(2)
    return graph


def _build_agent_graph() -> ExecutionGraph:
    graph = ExecutionGraph("agent-boundary-test")
    graph.add_node(AgentNode(node_id=1, node_name="writer", blueprint_ref="writer", next_node_ids=[2]))
    graph.add_node(AgentNode(node_id=2, node_name="publisher", blueprint_ref="publisher"))
    graph.add_edge(1, 2)
    graph.set_entry(1)
    graph.set_exit(2)
    return graph


class RuntimeArchitectureBoundaryTest(unittest.TestCase):
    def test_core_init_can_check_execution_graph_completeness(self) -> None:
        core = Core(
            agent_name="demo",
            agent_config=AgentConfig(api_url="https://example.com", api_key="key", model="model"),
        )
        core.set_execution_graph(_build_graph())

        asyncio.run(core.init())

    def test_agent_graph_snapshot_does_not_import_web_layer(self) -> None:
        core = Core(
            agent_name="demo",
            agent_config=AgentConfig(api_url="https://example.com", api_key="key", model="model"),
        )
        core.set_execution_graph(_build_agent_graph())
        original_import = builtins.__import__

        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "web" or name.startswith("web."):
                raise AssertionError(f"core imported web layer while building graph snapshot: {name}")
            return original_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=guarded_import):
            snapshot = core.get_agent_graph_snapshot()

        self.assertEqual(snapshot["graph_name"], "agent-boundary-test")
        self.assertEqual(snapshot["graph_kind"], "agent")
        self.assertEqual(snapshot["node_count"], 2)


if __name__ == "__main__":
    unittest.main()
