from __future__ import annotations

import unittest
from pathlib import Path

from core.errors import RequiredToolFailedError, ToolContractError, ToolPolicyDeniedError
from core.executor_parts.engine import GraphExecutor
from core.executor_parts.tool_scheduler import ToolScheduler
from core.failure_classifier import classify_failure
from core.fault_tolerance import ArchitectureRegulator, FailureEvent
from core.policy import AgentNode, ExecutionGraph
from core.results import AgentRoundResult, ToolRequest
from core.toodefl import ToolContext
from tools.command_runner_tool import CommandRunnerTool


class ScriptedExternalAgent:
    agent_id = "agent"
    tool_execution_mode = "external"

    def __init__(self, steps):
        self.steps = list(steps)
        self.calls = 0
        self.tools = [CommandRunnerTool()]

    async def round_call(self, *, rounds: int, user_message: str, additional_prompt=None):
        self.calls += 1
        if self.tool_execution_mode == "disabled":
            return AgentRoundResult(
                rounds=rounds,
                user_message=user_message,
                assistant_message="tool denied; continuing from assumptions",
            )
        step = self.steps.pop(0) if self.steps else {"message": "done"}
        requests = step.get("tool_requests")
        if requests is not None:
            return AgentRoundResult(
                rounds=rounds,
                user_message=user_message,
                assistant_message=step.get("message", "[tool request]"),
                tool_requests=requests,
            )
        return AgentRoundResult(
            rounds=rounds,
            user_message=user_message,
            assistant_message=step.get("message", "done"),
        )


class Core:
    workspace_mode = "workspace"
    workspace_root = Path.cwd()
    current_run_id = None

    def __init__(self, agent=None, *, tools=None) -> None:
        self.agent = agent
        self.agents = {"agent": agent} if agent is not None else {}
        self.agent_blueprints = dict(self.agents)
        self.tools = {"command_runner": CommandRunnerTool()} if tools is None else tools
        self.limiter = None

    def has_agent_blueprint(self, ref):
        return ref in self.agent_blueprints

    def get_agent_blueprint(self, ref):
        return self.agent_blueprints[ref]

    def acquire_agent_instance(self, ref, **kwargs):
        return self.agent_blueprints[ref]

    def release_agent_instance(self, ref):
        return None

    def get_tool(self, tool_name):
        try:
            return self.tools[tool_name]
        except KeyError as exc:
            raise KeyError(f"Unknown tool_name: {tool_name}") from exc

    def get_tool_scheduler(self):
        return ToolScheduler(self)

    def get_tool_capabilities(self, tool_name):
        if tool_name == "command_runner":
            return {"command_execute"}
        return set()

    def merge_agent_cognitive_delta(self, *args, **kwargs):
        return None

    def get_cognitive_graph_export(self, *args, **kwargs):
        return ""

    def record_runtime_change(self, **kwargs):
        return None

    def cleanup_transient_execution_nodes(self, *, graph=None):
        return []


def build_graph(metadata=None) -> ExecutionGraph:
    graph = ExecutionGraph("policy")
    graph.add_node(
        AgentNode(
            node_id=1,
            node_name="agent",
            blueprint_ref="agent",
            metadata={"tool_execution_mode": "external", **(metadata or {})},
        )
    )
    graph.set_entry(1)
    graph.set_exit(1)
    return graph


class ToolPolicyDeniedTest(unittest.IsolatedAsyncioTestCase):
    async def test_command_runner_policy_denial_has_failure_kind(self) -> None:
        scheduler = ToolScheduler(Core())
        result = await scheduler.execute_batch(
            [
                ToolRequest(
                    id="bad",
                    tool="command_runner",
                    args={"command": "uname -m; cat /proc/cpuinfo"},
                    required=True,
                )
            ],
            context=ToolContext(
                agent_id="agent",
                workspace_root=Path.cwd(),
                capabilities={"command_execute"},
            ),
        )

        self.assertTrue(result.summary["failed_required"])
        self.assertEqual(result.results[0].error["failure_kind"], "tool_policy_denied")
        self.assertEqual(classify_failure(ToolPolicyDeniedError(
            tool_name="command_runner",
            command="pwd; ls",
            reason="compound_shell_command",
            blocked_tokens=[";"],
            suggested_safe_calls=[],
        )).failure_kind, "tool_policy_denied")

    async def test_tool_policy_denied_does_not_quarantine_node(self) -> None:
        graph = build_graph({"failure_policy": {"allow_tool_policy_repair": True}})
        regulation = ArchitectureRegulator().regulate(
            FailureEvent(
                failure_scope="node",
                failure_kind="tool_policy_denied",
                node_id=1,
                node_name="agent",
                node_type="AgentNode",
                message="denied",
            ),
            graph=graph,
        )

        self.assertEqual(regulation.action, "request_tool_rewrite")
        self.assertEqual(regulation.quarantined_nodes, [])
        self.assertFalse(graph.nodes[1].metadata["fault_tolerance"]["quarantined"])

    async def test_executor_allows_one_tool_policy_repair_round(self) -> None:
        agent = ScriptedExternalAgent([
            {
                "tool_requests": [
                    ToolRequest(id="bad", tool="command_runner", args={"command": "pwd; ls"}, required=True)
                ]
            },
            {
                "tool_requests": [
                    ToolRequest(id="good", tool="command_runner", args={"command": "pwd"}, required=True)
                ]
            },
            {"message": "planned after safe probe"},
        ])
        graph = build_graph({"failure_policy": {"allow_tool_policy_repair": True, "max_tool_repair_rounds": 1}})
        events = []

        state = await GraphExecutor().execute(graph, Core(agent), "input", event_sink=events.append)

        self.assertEqual(agent.calls, 3)
        self.assertFalse(any(event.event_type == "node.failed" for event in events))
        self.assertIn("planned after safe probe", state.metadata["outputs"]["1"])

    async def test_executor_allows_one_tool_argument_repair_round(self) -> None:
        from tools.file_writer_tool import FileWriterTool

        agent = ScriptedExternalAgent([
            {
                "tool_requests": [
                    ToolRequest(id="bad", tool="file_writer", args={"content": "hello"}, required=True)
                ]
            },
            {
                "tool_requests": [
                    ToolRequest(
                        id="good",
                        tool="file_writer",
                        args={"path": "tmp/tool_arg_repair.txt", "content": "hello"},
                        required=True,
                    )
                ]
            },
            {"message": "wrote file"},
        ])
        agent.tools = [FileWriterTool()]
        graph = build_graph({"failure_policy": {"allow_tool_call_repair": True, "max_tool_repair_rounds": 1}})
        core = Core(agent, tools={"file_writer": FileWriterTool()})

        def caps(tool_name):
            return {"file_write"} if tool_name == "file_writer" else set()

        core.get_tool_capabilities = caps
        events = []

        state = await GraphExecutor().execute(graph, core, "input", event_sink=events.append)

        self.assertEqual(agent.calls, 3)
        self.assertFalse(any(event.event_type == "node.failed" for event in events))
        self.assertIn("wrote file", state.metadata["outputs"]["1"])

    async def test_executor_toolless_fallback_degrades_node(self) -> None:
        agent = ScriptedExternalAgent([
            {
                "tool_requests": [
                    ToolRequest(id="bad", tool="command_runner", args={"command": "pwd; ls"}, required=True)
                ]
            }
        ])
        graph = build_graph({"failure_policy": {"allow_toolless_fallback": True}})
        events = []

        await GraphExecutor().execute(graph, Core(agent), "input", event_sink=events.append)

        self.assertTrue(any(event.event_type == "node.degraded" for event in events))
        self.assertTrue(any(event.event_type == "node.completed" and event.status == "degraded_ok" for event in events))

    async def test_unknown_tool_still_fails_fast(self) -> None:
        agent = ScriptedExternalAgent([])
        agent.tools = []
        graph = build_graph()
        graph.nodes[1].metadata["tool_execution_mode"] = "external"
        core = Core(agent, tools={})
        agent.tools = [type("UnknownTool", (), {"tool_name": "missing_tool"})()]

        with self.assertRaises(ToolContractError):
            await GraphExecutor().execute(graph, core, "input")

    async def test_required_runtime_failure_still_required_tool_failed(self) -> None:
        agent = ScriptedExternalAgent([
            {
                "tool_requests": [
                    ToolRequest(id="bad", tool="command_runner", args={"command": "exit 7"}, required=True)
                ]
            }
        ])
        graph = build_graph()
        events = []

        with self.assertRaises(RequiredToolFailedError):
            await GraphExecutor().execute(graph, Core(agent), "input", event_sink=events.append)

        failed = [event for event in events if event.event_type == "node.failed"]
        self.assertEqual(failed[0].data["failure"]["failure_kind"], "required_tool_failed")


if __name__ == "__main__":
    unittest.main()
