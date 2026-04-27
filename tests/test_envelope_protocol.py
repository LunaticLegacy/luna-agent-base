from __future__ import annotations

import unittest
from pathlib import Path

from core.executor import GraphExecutor
from core.policy import AgentNode, ExecutionGraph, ToolNode
from core.results import AgentRoundResult, ExecutionState
from tools.file_writer_tool import FileWriterTool
from web.routes.swarms import extract_artifact_path, normalize_initial_payload, resolve_final_output


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
        return None


class NormalizeInitialPayloadTest(unittest.TestCase):
    def test_string_passed_through(self) -> None:
        result = normalize_initial_payload("hello world")
        self.assertEqual(result, "hello world")

    def test_dict_passed_through(self) -> None:
        raw = {"template": "summary", "text": "do something", "output_style": "markdown"}
        result = normalize_initial_payload(raw)
        self.assertIs(result, raw)

    def test_int_coerced_to_str(self) -> None:
        result = normalize_initial_payload(42)
        self.assertEqual(result, "42")


class ResolveFinalOutputTest(unittest.TestCase):
    def test_no_outputs_returns_payload(self) -> None:
        state = ExecutionState(payload="raw request")
        self.assertEqual(resolve_final_output(state), "raw request")

    def test_returns_last_output_content(self) -> None:
        state = ExecutionState(
            payload="raw request",
            metadata={"outputs": {"1": {"content": "hello"}}},
        )
        self.assertEqual(resolve_final_output(state), "hello")

    def test_returns_last_output_final_answer(self) -> None:
        state = ExecutionState(
            payload="raw request",
            metadata={"outputs": {"1": {"final_answer": "answer"}}},
        )
        self.assertEqual(resolve_final_output(state), "answer")

    def test_returns_last_output_dict_when_no_priority_key(self) -> None:
        state = ExecutionState(
            payload="raw request",
            metadata={"outputs": {"1": {"written": True, "path": "x.py"}}},
        )
        self.assertEqual(resolve_final_output(state), {"written": True, "path": "x.py"})


class GraphExecutionTest(unittest.IsolatedAsyncioTestCase):
    async def test_payload_is_immutable(self) -> None:
        payload = "build me a thing"
        graph = ExecutionGraph("immutable")
        graph.add_node(
            AgentNode(node_id=1,
                node_name="orchestrator",
                agent_id="orchestrator")
        )
        graph.add_node(
            AgentNode(node_id=2,
                node_name="organizer",
                agent_id="organizer")
        )
        graph.add_edge(1, 2, label="next")
        graph.set_entry(1)
        graph.set_exit(2)

        core = DummyCore(
            {
                "orchestrator": ScriptedAgent('{"content": "brief"}'),
                "organizer": ScriptedAgent('{"next_node_ids": []}'),
            }
        )

        state = await GraphExecutor().execute(graph, core, payload)
        self.assertEqual(state.payload, "build me a thing")

    async def test_agent_outputs_saved_to_metadata_outputs(self) -> None:
        payload = "build me a thing"
        graph = ExecutionGraph("outputs")
        graph.add_node(
            AgentNode(node_id=1,
                node_name="orchestrator",
                agent_id="orchestrator")
        )
        graph.add_node(
            AgentNode(node_id=2,
                node_name="organizer",
                agent_id="organizer")
        )
        graph.add_edge(1, 2, label="next")
        graph.set_entry(1)
        graph.set_exit(2)

        core = DummyCore(
            {
                "orchestrator": ScriptedAgent('{"content": "brief"}'),
                "organizer": ScriptedAgent('{"plan": "do it"}'),
            }
        )

        state = await GraphExecutor().execute(graph, core, payload)
        self.assertIn("1", state.metadata["outputs"])
        self.assertIn("2", state.metadata["outputs"])
        self.assertEqual(state.metadata["outputs"]["1"]["content"], "brief")
        self.assertEqual(state.metadata["outputs"]["2"]["plan"], "do it")

    async def test_agent_control_patch_routes_via_metadata(self) -> None:
        payload = "build me a thing"
        graph = ExecutionGraph("routing")
        graph.add_node(
            AgentNode(node_id=1,
                node_name="orchestrator",
                agent_id="orchestrator")
        )
        graph.add_node(
            AgentNode(node_id=2,
                node_name="organizer",
                agent_id="organizer")
        )
        graph.add_node(
            AgentNode(node_id=22,
                node_name="code_writer",
                agent_id="code_writer")
        )
        graph.add_node(
            AgentNode(node_id=24,
                node_name="dev",
                agent_id="dev")
        )
        graph.add_edge(1, 2, label="next")
        graph.add_edge(2, 22, label="implement")
        graph.add_edge(2, 24, label="backend")
        graph.set_entry(1)
        graph.set_exit(22)

        core = DummyCore(
            {
                "orchestrator": ScriptedAgent('{"content": "brief"}'),
                "organizer": ScriptedAgent('{"next_node_ids": [22]}'),
                "code_writer": ScriptedAgent('{"content": "code"}'),
                "dev": ScriptedAgent('{"content": "dev"}'),
            }
        )

        state = await GraphExecutor().execute(graph, core, payload)
        # organizer's control patch should be in metadata
        self.assertEqual(state.metadata["control"]["2"]["next_node_ids"], [22])
        # code_writer should have run, dev should not
        self.assertIn("22", state.metadata["outputs"])
        self.assertNotIn("24", state.metadata.get("outputs", {}))
        self.assertEqual(state.metadata["outputs"]["22"]["content"], "code")

    async def test_tool_uses_upstream_output_not_payload(self) -> None:
        class CaptureTool:
            def __init__(self) -> None:
                self.arguments = None

            async def execute(self, arguments, *, context=None):
                self.arguments = arguments
                return {"written": True}

        payload = "build me a thing"
        graph = ExecutionGraph("tool-input")
        graph.add_node(
            AgentNode(node_id=22,
                node_name="code_writer",
                agent_id="code_writer")
        )
        graph.add_node(
            ToolNode(
                node_id=23,
                node_name="file_writer",
                tool_name="file_writer",
                next_node_ids=[],
                input_mapping={"path": "outputs/generated.py"},
            )
        )
        graph.add_edge(22, 23, label="write")
        graph.set_entry(22)
        graph.set_exit(23)

        capture = CaptureTool()
        core = DummyCore(
            {
                "code_writer": ScriptedAgent('{"content": "GENERATED_CODE"}'),
            },
            tools={"file_writer": capture},
        )

        state = await GraphExecutor().execute(graph, core, payload)
        self.assertIn("22", state.metadata["outputs"])
        self.assertIn("23", state.metadata["outputs"])
        # Tool should receive the upstream agent output, not the payload
        self.assertEqual(capture.arguments["input"], "GENERATED_CODE")
        self.assertEqual(capture.arguments["path"], "outputs/generated.py")
        self.assertEqual(capture.arguments["payload"], payload)

    async def test_agent_input_is_raw_payload(self) -> None:
        payload = {"template": "summary", "text": "build a loop framework", "output_style": "markdown"}
        graph = ExecutionGraph("agent-input")
        graph.add_node(
            AgentNode(node_id=1,
                node_name="orchestrator",
                agent_id="orchestrator")
        )
        graph.set_entry(1)
        graph.set_exit(1)

        core = DummyCore(
            {
                "orchestrator": ScriptedAgent('{"content": "ok"}'),
            }
        )

        await GraphExecutor().execute(graph, core, payload)
        user_msg = core.agents["orchestrator"].user_messages[0]
        # Agent should receive the JSON-serialized payload directly
        self.assertIn("build a loop framework", user_msg)


class ExtractArtifactPathTest(unittest.TestCase):
    def test_chinese_将该文件命名为(self) -> None:
        self.assertEqual(extract_artifact_path("将该文件命名为 frame.py"), "frame.py")

    def test_chinese_命名为(self) -> None:
        self.assertEqual(extract_artifact_path("命名为 frame.py"), "frame.py")

    def test_chinese_保存为(self) -> None:
        self.assertEqual(extract_artifact_path("保存为 frame.py"), "frame.py")

    def test_chinese_文件名为(self) -> None:
        self.assertEqual(extract_artifact_path("文件名为 frame.py"), "frame.py")

    def test_english_name_it(self) -> None:
        self.assertEqual(extract_artifact_path("name it frame.py"), "frame.py")

    def test_english_save_as(self) -> None:
        self.assertEqual(extract_artifact_path("save as frame.py"), "frame.py")

    def test_no_match_returns_none(self) -> None:
        self.assertIsNone(extract_artifact_path("do something interesting"))

    def test_path_with_subdirs(self) -> None:
        self.assertEqual(extract_artifact_path("save as src/main.py"), "src/main.py")


class FileWriterPathResolutionTest(unittest.TestCase):
    def test_explicit_path_wins(self) -> None:
        tool = FileWriterTool()
        path = tool._resolve_path({"path": "a.py", "fallback_path": "b.py", "payload": {"hint": "c.py"}})
        self.assertEqual(path, "a.py")

    def test_payload_hint_second(self) -> None:
        tool = FileWriterTool()
        path = tool._resolve_path({"fallback_path": "b.py", "payload": {"path": "c.py"}})
        self.assertEqual(path, "c.py")

    def test_fallback_path_last(self) -> None:
        tool = FileWriterTool()
        path = tool._resolve_path({"fallback_path": "b.py"})
        self.assertEqual(path, "b.py")

    def test_no_path_raises(self) -> None:
        tool = FileWriterTool()
        with self.assertRaisesRegex(ValueError, "requires a non-empty"):
            tool._resolve_path({})


class RawSourceCodeTest(unittest.IsolatedAsyncioTestCase):
    async def test_file_writer_receives_source_code_not_result_object(self) -> None:
        """Simulate code_writer outputting raw Python source (not JSON)."""
        class CaptureTool:
            def __init__(self) -> None:
                self.arguments = None

            async def execute(self, arguments, *, context=None):
                self.arguments = arguments
                return {"written": True, "path": arguments.get("path", arguments.get("fallback_path"))}

        payload = "为我做一个agent循环框架。将该文件命名为 frame.py。"
        graph = ExecutionGraph("raw-source")
        graph.add_node(
            AgentNode(node_id=22,
                node_name="code_writer",
                agent_id="code_writer")
        )
        graph.add_node(
            ToolNode(
                node_id=23,
                node_name="file_writer",
                tool_name="file_writer",
                next_node_ids=[],
                input_mapping={"fallback_path": "outputs/generated.py"},
            )
        )
        graph.add_edge(22, 23, label="write")
        graph.set_entry(22)
        graph.set_exit(23)

        source_code = "class AgentLoop:\n    pass\n"
        capture = CaptureTool()
        core = DummyCore(
            {
                "code_writer": ScriptedAgent(source_code),
            },
            tools={"file_writer": capture},
        )

        state = await GraphExecutor().execute(graph, core, payload)

        # The tool should receive the actual source code string, not AgentRoundResult repr
        self.assertEqual(capture.arguments["input"], source_code)
        # Verify the output stored in metadata is also the string, not an object
        self.assertEqual(state.metadata["outputs"]["22"], source_code)


class PromptSanityTest(unittest.TestCase):
    def test_coder_prompt_has_no_transformer(self) -> None:
        prompt_path = Path(__file__).resolve().parent.parent / "agents" / "deepseek_demo" / "skills" / "coder.prompt.md"
        text = prompt_path.read_text(encoding="utf-8")
        self.assertNotIn("transformer", text.lower())


if __name__ == "__main__":
    unittest.main()
