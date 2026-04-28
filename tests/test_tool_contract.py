from __future__ import annotations

import unittest
from types import SimpleNamespace

from core.policy import AgentNode, ExecutionGraph, ToolNode
from core.tool_contract import ToolContractValidator


class DummyTool:
    tool_name = "command_runner"


class ToolContractValidatorTest(unittest.TestCase):
    def test_tool_node_unknown_tool_fails_before_run(self) -> None:
        graph = ExecutionGraph("contract")
        graph.add_node(ToolNode(node_id=1, node_name="missing", tool_name="missing_tool"))
        graph.set_entry(1)
        core = SimpleNamespace(tools={}, agents={}, agent_blueprints={})

        report = ToolContractValidator().validate(core, graph)

        self.assertFalse(report.ok)
        self.assertEqual(report.errors[0].issue_kind, "unknown_tool")

    def test_external_recall_context_without_registered_tool_is_scheduler_handled_warning(self) -> None:
        agent = SimpleNamespace(
            agent_id="a",
            tool_execution_mode="external",
            tools=[SimpleNamespace(tool_name="recall_context")],
        )
        graph = ExecutionGraph("contract")
        graph.add_node(AgentNode(node_id=1, node_name="agent", blueprint_ref="a"))
        graph.set_entry(1)
        core = _Core({"a": agent}, {})

        report = ToolContractValidator().validate(core, graph)

        self.assertTrue(report.ok)
        self.assertEqual(report.warnings[0].issue_kind, "external_builtin_tool_scheduler_handled")

    def test_alias_passes_when_target_tool_exists(self) -> None:
        graph = ExecutionGraph("contract")
        graph.add_node(ToolNode(node_id=1, node_name="bash", tool_name="bash"))
        graph.set_entry(1)
        core = SimpleNamespace(tools={"command_runner": DummyTool()}, agents={}, agent_blueprints={})

        report = ToolContractValidator().validate(core, graph)

        self.assertTrue(report.ok)

    def test_alias_fails_when_target_missing(self) -> None:
        graph = ExecutionGraph("contract")
        graph.add_node(ToolNode(node_id=1, node_name="bash", tool_name="bash"))
        graph.set_entry(1)
        core = SimpleNamespace(tools={}, agents={}, agent_blueprints={})

        report = ToolContractValidator().validate(core, graph)

        self.assertFalse(report.ok)
        self.assertIn("bash", report.errors[0].tool_name)


class _Core:
    def __init__(self, agents, tools) -> None:
        self.agents = agents
        self.agent_blueprints = agents
        self.tools = tools

    def has_agent_blueprint(self, blueprint_ref: str) -> bool:
        return blueprint_ref in self.agent_blueprints

    def get_agent_blueprint(self, blueprint_ref: str):
        return self.agent_blueprints[blueprint_ref]


if __name__ == "__main__":
    unittest.main()
