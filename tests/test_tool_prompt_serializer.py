from __future__ import annotations

import unittest
from types import SimpleNamespace

from core.agent import Agent
from core.tool_prompt_serializer import serialize_tool_contracts
from core.toodefl import ToolContext, ToolDefinition


class RecordingLLM:
    def __init__(self) -> None:
        self.system_prompts = []

    async def fetch(self, *, msg, system_prompt=None, prev_messages=None, tools=None):
        self.system_prompts.append(system_prompt)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="done",
                        tool_calls=None,
                    )
                )
            ]
        )


class DemoTool(ToolDefinition):
    def __init__(self) -> None:
        super().__init__(
            tool_name="demo_tool",
            description="Demo tool.",
            schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        )

    async def execute(self, arguments, *, context: ToolContext | None = None):
        return {"ok": True}


class ToolPromptSerializerTest(unittest.IsolatedAsyncioTestCase):
    async def test_serializer_includes_tool_schema(self) -> None:
        text = serialize_tool_contracts([DemoTool()])

        self.assertIn("Runtime Tool Contracts", text)
        self.assertIn('"tool_name": "demo_tool"', text)
        self.assertIn('"required"', text)
        self.assertIn('"path"', text)
        self.assertIn('"content"', text)

    async def test_agent_injects_tool_contracts_into_system_prompt(self) -> None:
        llm = RecordingLLM()
        agent = Agent(
            agent_id="demo",
            llm_handler=llm,
            character_prompt="You are demo.",
            tools=[DemoTool()],
            tool_execution_mode="external",
        )

        await agent.round_call(rounds=1, user_message="hello")

        self.assertEqual(len(llm.system_prompts), 1)
        system_prompt = llm.system_prompts[0]
        self.assertIn("Runtime Tool Contracts", system_prompt)
        self.assertIn('"tool_name": "demo_tool"', system_prompt)
        self.assertIn('"required"', system_prompt)

    async def test_agent_can_disable_tool_contract_prompt(self) -> None:
        llm = RecordingLLM()
        agent = Agent(
            agent_id="demo",
            llm_handler=llm,
            character_prompt="You are demo.",
            tools=[DemoTool()],
            tool_execution_mode="external",
            tool_contract_prompt_mode="off",
        )

        await agent.round_call(rounds=1, user_message="hello")

        self.assertNotIn("Runtime Tool Contracts", llm.system_prompts[0])


if __name__ == "__main__":
    unittest.main()
