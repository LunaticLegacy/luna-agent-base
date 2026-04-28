from __future__ import annotations

import unittest

from core.architecture_manager import ArchitectureManager
from core.config import AgentConfig
from core.core import Core
from core.policy import AgentNode, ExecutionGraph


class DummyAgent:
    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self.name = agent_id
        self.tool_execution_mode = "disabled"
        self.tools = []

    def reset_context(self):
        return None


def build_core(max_agents: int = 12) -> Core:
    core = Core(
        agent_name="demo",
        agent_config=AgentConfig(api_url="https://example.com", api_key="key", model="model"),
    )
    core.architecture_policy["max_agents"] = max_agents
    start = DummyAgent("start_agent")
    core.add_agent(start)
    core.register_agent_blueprint("start_agent", start)
    graph = ExecutionGraph("arch")
    graph.add_node(AgentNode(node_id=1, node_name="start", blueprint_ref="start_agent"))
    graph.set_entry(1)
    graph.set_exit(1)
    core.set_execution_graph(graph)
    return core


class ArchitecturePatchTest(unittest.IsolatedAsyncioTestCase):
    async def test_legal_add_agent_node_patch_can_apply_and_rollback(self) -> None:
        core = build_core()
        manager = ArchitectureManager(core)
        patch = {
            "patch_id": "p1",
            "reason": "add helper",
            "scope": "package",
            "operations": [
                {"op": "add_agent", "agent_id": "helper", "character_prompt": "Help.", "tool_execution_mode": "disabled"},
                {"op": "add_agent_node", "node_id": "auto", "node_name": "helper_node", "agent_id": "helper"},
                {"op": "insert_after", "target_node_id": 1, "new_node_ref": "helper_node", "preserve_downstream": True},
            ],
        }

        result = await manager.apply_patch(patch)

        self.assertTrue(result.ok, result.errors)
        self.assertEqual(len(core.get_execution_graph().nodes), 2)
        self.assertIn("helper", core.agents)

        rollback = await manager.rollback_patch("p1")

        self.assertTrue(rollback.ok, rollback.errors)
        self.assertEqual(len(core.get_execution_graph().nodes), 1)
        self.assertNotIn("helper", core.agents)

    async def test_patch_rejects_missing_node_reference(self) -> None:
        core = build_core()
        result = ArchitectureManager(core).validate_patch({
            "patch_id": "bad",
            "reason": "bad",
            "operations": [{"op": "insert_after", "target_node_id": 999, "new_node_ref": "x"}],
        })

        self.assertFalse(result.ok)
        self.assertTrue(any("missing target_node_id" in error for error in result.errors))

    async def test_patch_rejects_max_agents(self) -> None:
        core = build_core(max_agents=1)
        result = ArchitectureManager(core).validate_patch({
            "patch_id": "bad",
            "reason": "too many",
            "operations": [{"op": "add_agent", "agent_id": "extra", "character_prompt": "x"}],
        })

        self.assertFalse(result.ok)
        self.assertTrue(any("max_agents" in error for error in result.errors))

    async def test_patch_rejects_tool_permission_escalation(self) -> None:
        core = build_core()
        result = ArchitectureManager(core).validate_patch({
            "patch_id": "bad",
            "reason": "tool escalation",
            "operations": [{"op": "add_agent", "agent_id": "extra", "character_prompt": "x", "tools": ["command_runner"]}],
        })

        self.assertFalse(result.ok)
        self.assertTrue(any("cannot grant tools" in error for error in result.errors))


if __name__ == "__main__":
    unittest.main()
