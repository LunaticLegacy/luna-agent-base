from __future__ import annotations

import unittest

from core.cognitive import CognitiveGraph
from core.executor import GraphExecutor
from core.policy import AgentNode, ExecutionGraph, ToolNode
from core.results import AgentRoundResult


class ScriptedAgent:
    def __init__(self, *responses: str) -> None:
        self.responses = list(responses)
        self.user_messages: list[str] = []

    async def round_call(self, *, rounds: int, user_message: str, additional_prompt=None):
        self.user_messages.append(user_message)
        response = self.responses.pop(0)
        return AgentRoundResult(
            rounds=rounds,
            user_message=user_message,
            assistant_message=response,
            additional_prompt=additional_prompt,
        )


class DummyCore:
    def __init__(self, agents: dict[str, ScriptedAgent], tools=None) -> None:
        self.agents = agents
        self.agent_blueprints = dict(agents)
        self.tools = tools or {}
        self.swarm_cognitive_graph = CognitiveGraph(graph_id="shared")
        self.current_run_id = None

    def get_agent(self, agent_id: str) -> ScriptedAgent:
        return self.agents[agent_id]

    def get_agent_blueprint(self, blueprint_ref: str) -> ScriptedAgent:
        return self.agent_blueprints[blueprint_ref]

    def has_agent_blueprint(self, blueprint_ref: str) -> bool:
        return blueprint_ref in self.agent_blueprints

    def acquire_agent_instance(
        self, blueprint_ref: str, *, instance_policy: str = "singleton", parallel_context: bool = False
    ):
        if instance_policy == "per_call" or parallel_context:
            prototype = self.agent_blueprints[blueprint_ref]
            clone = getattr(prototype, "clone_for_runtime", None)
            if callable(clone):
                return clone()
        return self.agent_blueprints[blueprint_ref]

    def get_tool(self, tool_name: str):
        return self.tools[tool_name]

    def merge_agent_cognitive_graph(self, agent_id: str) -> None:
        return None

    def merge_agent_cognitive_delta(self, agent_id: str, snapshot) -> None:
        if snapshot:
            self.swarm_cognitive_graph = CognitiveGraph.from_dict(snapshot)

    def get_cognitive_graph_export(self, query=None, max_nodes=None) -> str:
        return ""


def build_publish_graph() -> ExecutionGraph:
    graph = ExecutionGraph("publish")
    graph.add_node(AgentNode(node_id=18, node_name="writer", agent_id="writer"))
    graph.add_node(AgentNode(node_id=19, node_name="reviewer", agent_id="reviewer"))
    graph.add_node(AgentNode(node_id=20, node_name="publisher", agent_id="publisher"))
    graph.add_edge(18, 19, label="review", priority=10)
    graph.add_edge(19, 20, label="approve", condition="approve", priority=20)
    graph.add_edge(19, 18, label="revise", condition="revise", priority=10)
    graph.set_entry(18)
    graph.set_exit(20)
    return graph


class ExecutorPublishChainTest(unittest.IsolatedAsyncioTestCase):
    async def test_reviewer_approve_preserves_writer_payload_for_publisher(self) -> None:
        draft = "DRAFT REPORT"
        core = DummyCore(
            {
                "writer": ScriptedAgent(f'{{"content": "{draft}"}}'),
                "reviewer": ScriptedAgent(
                    '{"verdict": "approve", "branch": "approve", "content": "", "next_node_ids": [20]}'
                ),
                "publisher": ScriptedAgent('{"content": "published"}'),
            }
        )

        state = await GraphExecutor().execute(build_publish_graph(), core, "mission")

        # Without envelope mode, agent receives the raw payload directly
        publisher_input = core.agents["publisher"].user_messages[0]
        self.assertEqual(publisher_input, "mission")
        self.assertEqual(state.metadata["control"]["19"]["verdict"], "approve")
        self.assertEqual(state.metadata["approved_report"], draft)
        self.assertEqual(state.metadata["outputs"]["18"]["content"], draft)

    async def test_reviewer_revise_can_send_revision_payload_back_to_writer(self) -> None:
        core = DummyCore(
            {
                "writer": ScriptedAgent('{"content": "DRAFT"}', '{"content": "REVISED DRAFT"}'),
                "reviewer": ScriptedAgent(
                    '{"verdict": "revise", "branch": "revise", "content": "Please tighten evidence.", "next_node_ids": [18]}',
                    '{"verdict": "approve", "branch": "approve", "content": "", "next_node_ids": [20]}',
                ),
                "publisher": ScriptedAgent('{"content": "published"}'),
            }
        )

        state = await GraphExecutor().execute(build_publish_graph(), core, "mission")

        # Without envelope mode, agents receive the raw payload directly
        writer_input = core.agents["writer"].user_messages[1]
        self.assertEqual(writer_input, "mission")
        publisher_input = core.agents["publisher"].user_messages[0]
        self.assertEqual(publisher_input, "mission")
        self.assertEqual(state.metadata["approved_report"], "REVISED DRAFT")

    async def test_publisher_final_answer_becomes_file_writer_payload(self) -> None:
        class CaptureTool:
            def __init__(self) -> None:
                self.arguments = None

            async def execute(self, arguments, *, context=None):
                self.arguments = arguments
                return {"written": True}

        graph = ExecutionGraph("publish-final-answer")
        graph.add_node(AgentNode(node_id=1, node_name="publisher", agent_id="publisher"))
        graph.add_node(ToolNode(node_id=2, node_name="file_writer", tool_name="file_writer", next_node_ids=[]))
        graph.add_edge(1, 2)
        graph.set_entry(1)
        graph.set_exit(2)

        capture_tool = CaptureTool()
        core = DummyCore(
            {
                "publisher": ScriptedAgent(
                    '{"final_answer": "# Report\\n\\nFull body", "content": "report generated successfully"}'
                )
            },
            tools={"file_writer": capture_tool},
        )

        state = await GraphExecutor().execute(graph, core, "approved draft")

        self.assertEqual(capture_tool.arguments["input"], "# Report\n\nFull body")
        self.assertEqual(state.metadata["final_report"], "# Report\n\nFull body")

    async def test_agent_cannot_route_to_non_outgoing_node(self) -> None:
        graph = ExecutionGraph("route-policy")
        graph.add_node(AgentNode(node_id=1, node_name="router", agent_id="router"))
        graph.add_node(AgentNode(node_id=2, node_name="allowed", agent_id="allowed"))
        graph.add_node(AgentNode(node_id=3, node_name="blocked", agent_id="blocked"))
        graph.add_edge(1, 2)
        graph.set_entry(1)
        graph.set_exit(2)
        core = DummyCore(
            {
                "router": ScriptedAgent('{"content": "jump", "next_node_ids": [3]}'),
                "allowed": ScriptedAgent("allowed"),
                "blocked": ScriptedAgent("blocked"),
            }
        )

        with self.assertRaisesRegex(ValueError, "not an allowed outgoing edge"):
            await GraphExecutor().execute(graph, core, "mission")

    async def test_per_call_agent_node_uses_fresh_runtime_instance(self) -> None:
        class CloneableScriptedAgent(ScriptedAgent):
            def __init__(self, *responses: str) -> None:
                super().__init__(*responses)
                self.clone_count = 0

            def clone_for_runtime(self):
                self.clone_count += 1
                return CloneableScriptedAgent(*self.responses)

        graph = ExecutionGraph("per-call")
        graph.add_node(
            AgentNode(node_id=1,
                node_name="writer",
                blueprint_ref="writer",
                instance_policy="per_call")
        )
        graph.set_entry(1)
        graph.set_exit(1)
        prototype = CloneableScriptedAgent('{"content": "draft"}')
        core = DummyCore({"writer": prototype})

        state = await GraphExecutor().execute(graph, core, "mission")

        # Payload is immutable; agent output lives in metadata.outputs
        self.assertEqual(state.payload, "mission")
        self.assertEqual(state.metadata["outputs"]["1"]["content"], "draft")
        self.assertEqual(prototype.clone_count, 1)


if __name__ == "__main__":
    unittest.main()
