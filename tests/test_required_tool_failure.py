from __future__ import annotations

import unittest
from types import SimpleNamespace

from core.executor_parts.engine import GraphExecutor
from core.policy import AgentNode, ExecutionGraph
from core.results import AgentRoundResult, ToolBatchResult, ToolRequest, ToolResult


class ScriptedExternalAgent:
    agent_id = "agent"
    tool_execution_mode = "external"

    def __init__(self) -> None:
        self.tools = [SimpleNamespace(tool_name="danger")]

    async def round_call(self, *, rounds: int, user_message: str, additional_prompt=None):
        return AgentRoundResult(
            rounds=rounds,
            user_message=user_message,
            assistant_message="[tool request]",
            tool_requests=[ToolRequest(id="t1", tool="danger", args={}, required=True)],
        )


class FailingScheduler:
    async def execute_batch(self, tool_requests, *, node_id=None, agent_id=None, tool_round=0, context=None):
        return ToolBatchResult(
            node_id=node_id,
            agent_id=agent_id,
            tool_round=tool_round,
            results=[
                ToolResult(
                    request_id="t1",
                    tool="danger",
                    status="failed",
                    error={"type": "RuntimeError", "message": "boom"},
                )
            ],
            summary={"status": "failed", "failed_required": True, "skipped": []},
        )


class Core:
    def __init__(self) -> None:
        self.agents = {"agent": ScriptedExternalAgent()}
        self.agent_blueprints = self.agents
        self.tools = {"danger": object()}
        self.workspace_mode = "workspace"
        self.workspace_root = None
        self.current_run_id = None

    def has_agent_blueprint(self, ref):
        return ref in self.agent_blueprints

    def get_agent_blueprint(self, ref):
        return self.agent_blueprints[ref]

    def acquire_agent_instance(self, ref, **kwargs):
        return self.agent_blueprints[ref]

    def release_agent_instance(self, ref):
        return None

    def get_tool_scheduler(self):
        return FailingScheduler()

    def get_tool_capabilities(self, tool_name):
        return set()

    def merge_agent_cognitive_delta(self, *args, **kwargs):
        return None

    def get_cognitive_graph_export(self, *args, **kwargs):
        return ""

    def record_runtime_change(self, **kwargs):
        return None

    def cleanup_transient_execution_nodes(self, *, graph=None):
        return []


class RequiredToolFailureTest(unittest.IsolatedAsyncioTestCase):
    async def test_failed_required_tool_fails_node_and_run(self) -> None:
        graph = ExecutionGraph("required")
        graph.add_node(AgentNode(node_id=1, node_name="agent", blueprint_ref="agent"))
        graph.set_entry(1)
        events = []

        with self.assertRaises(Exception):
            await GraphExecutor().execute(graph, Core(), "input", event_sink=events.append)

        failed = [event for event in events if event.event_type == "node.failed"]
        self.assertEqual(failed[0].data["failure"]["failure_kind"], "required_tool_failed")
        self.assertFalse(any(event.event_type == "node.completed" and event.status == "ok" for event in events))

    async def test_allow_toolless_fallback_marks_node_degraded(self) -> None:
        graph = ExecutionGraph("required")
        graph.add_node(
            AgentNode(
                node_id=1,
                node_name="agent",
                blueprint_ref="agent",
                metadata={"failure_policy": {"allow_toolless_fallback": True}},
            )
        )
        graph.set_entry(1)
        events = []

        await GraphExecutor().execute(graph, Core(), "input", event_sink=events.append)

        self.assertTrue(any(event.event_type == "node.degraded" for event in events))
        self.assertTrue(any(event.event_type == "node.completed" and event.status == "degraded_ok" for event in events))


if __name__ == "__main__":
    unittest.main()
