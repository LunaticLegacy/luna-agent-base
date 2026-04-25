from __future__ import annotations

import asyncio
import shutil
import unittest
from pathlib import Path

from core.config import AgentConfig
from core.core import Core
from core.policy import ExecutionGraph, Node
from core.toodefl import ToolContext
from tools.graph_editor_tool import GraphEditorTool


TEST_TMP_ROOT = Path(__file__).resolve().parent / ".artifacts"
TEST_TMP_ROOT.mkdir(exist_ok=True)


def make_test_dir(name: str) -> Path:
    path = (TEST_TMP_ROOT / name).resolve()
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


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

    def test_runtime_graph_persistence_writes_json_revision_not_graph_source(self) -> None:
        workspace_root = make_test_dir("runtime_graph_persistence")
        runtime_dir = workspace_root / "runtime_info"
        source_path = workspace_root / "graph.py"
        source_path.write_text("# blueprint graph\n", encoding="utf-8")

        core = Core(
            agent_name="demo",
            agent_config=AgentConfig(
                api_url="https://example.com",
                api_key="key",
                model="model",
            ),
            workspace_root=workspace_root,
        )
        core.set_runtime_info_dir(runtime_dir)
        core.set_execution_graph_artifacts(source_path=source_path, backup_path=workspace_root / "graph_init.py")
        graph = _build_graph()
        graph.add_edge(1, 2)
        core.set_execution_graph(graph)

        result = core.persist_execution_graph(
            change={"action": "add_edge", "detail": {"from_node_id": 1, "to_node_id": 2}},
        )

        self.assertEqual(source_path.read_text(encoding="utf-8"), "# blueprint graph\n")
        self.assertIsNotNone(result)
        current_path = runtime_dir / "graph_state" / "current.json"
        self.assertTrue(current_path.exists())
        payload = current_path.read_text(encoding="utf-8")
        self.assertIn('"graph_name": "test"', payload)
        self.assertIn('"action": "add_edge"', payload)
        shutil.rmtree(workspace_root)

    def test_core_loads_runtime_graph_state_over_blueprint_graph(self) -> None:
        workspace_root = make_test_dir("runtime_graph_reload")
        runtime_dir = workspace_root / "runtime_info"
        source_path = workspace_root / "graph.py"
        source_path.write_text("# blueprint graph\n", encoding="utf-8")

        first_core = Core(
            agent_name="demo",
            agent_config=AgentConfig(
                api_url="https://example.com",
                api_key="key",
                model="model",
            ),
            workspace_root=workspace_root,
        )
        first_core.set_runtime_info_dir(runtime_dir)
        first_core.set_execution_graph_artifacts(source_path=source_path, backup_path=workspace_root / "graph_init.py")
        graph = _build_graph()
        graph.add_edge(1, 2)
        first_core.set_execution_graph(graph)
        first_core.persist_execution_graph(change={"action": "add_edge"})

        second_core = Core(
            agent_name="demo",
            agent_config=AgentConfig(
                api_url="https://example.com",
                api_key="key",
                model="model",
            ),
            workspace_root=workspace_root,
        )
        second_core.set_runtime_info_dir(runtime_dir)
        second_core.set_execution_graph_artifacts(source_path=source_path, backup_path=workspace_root / "graph_init.py")
        second_core.set_execution_graph(_build_graph())

        loaded_graph = second_core.get_execution_graph()
        self.assertIsNotNone(loaded_graph)
        self.assertEqual(len(loaded_graph.edges), 1)
        self.assertEqual(loaded_graph.nodes[1].next_node_ids, [2])
        shutil.rmtree(workspace_root)


def _build_graph() -> ExecutionGraph:
    graph = ExecutionGraph("test")
    graph.add_node(Node(node_id=1, node_name="one"))
    graph.add_node(Node(node_id=2, node_name="two"))
    graph.set_entry(1)
    graph.set_exit(2)
    return graph


if __name__ == "__main__":
    unittest.main()
