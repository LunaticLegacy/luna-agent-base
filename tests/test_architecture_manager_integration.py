from __future__ import annotations

import unittest
from types import SimpleNamespace

from core.config import AgentConfig
from core.core import Core
from core.executor_parts.engine import GraphExecutor
from core.policy import AgentNode, ExecutionGraph


class MalformedAgent:
    agent_id = "bad"
    name = "bad"
    tool_execution_mode = "disabled"
    tools = []

    async def round_call(self, *, rounds: int, user_message: str, additional_prompt=None):
        return SimpleNamespace(assistant_message='{"broken": ')

    def reset_context(self):
        return None


class ArchitectureManagerIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_output_parse_error_can_propose_and_apply_output_repairer_patch(self) -> None:
        core = Core(
            agent_name="demo",
            agent_config=AgentConfig(api_url="https://example.com", api_key="key", model="model"),
        )
        agent = MalformedAgent()
        core.add_agent(agent)
        core.register_agent_blueprint("bad", agent)
        graph = ExecutionGraph("integration")
        graph.add_node(
            AgentNode(
                node_id=1,
                node_name="bad",
                blueprint_ref="bad",
                metadata={"output_mode": "json_required", "auto_repair": True},
            )
        )
        graph.set_entry(1)
        graph.set_exit(1)
        core.set_execution_graph(graph)

        with self.assertRaises(Exception):
            await GraphExecutor().execute(graph, core, "input")

        self.assertIn("patch-output-repairer-1", core.architecture_manager.rollback_records)
        self.assertIn("output_repairer", core.agents)


if __name__ == "__main__":
    unittest.main()
