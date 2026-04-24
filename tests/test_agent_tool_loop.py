from __future__ import annotations

import unittest
from types import SimpleNamespace

from core.agent import Agent
from core.toodefl import ToolContext, ToolDefinition


class RecordingLLM:
    def __init__(self) -> None:
        self.prev_messages = []
        self.calls = 0

    async def fetch(self, *, msg, system_prompt=None, prev_messages=None, tools=None):
        self.prev_messages.append(list(prev_messages or []))
        self.calls += 1
        if self.calls == 1:
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=None,
                            tool_calls=[
                                {
                                    "function": {
                                        "name": "record_tool",
                                        "arguments": '{"input": "needle"}',
                                    }
                                }
                            ],
                        )
                    )
                ]
            )
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="final answer",
                        tool_calls=None,
                    )
                )
            ]
        )


class RecordingTool(ToolDefinition):
    def __init__(self) -> None:
        super().__init__(
            tool_name="record_tool",
            description="Record input.",
            schema={
                "type": "object",
                "properties": {"input": {"type": "string"}},
            },
        )

    async def execute(self, arguments, *, context: ToolContext | None = None):
        return {"tool_result": f"seen {arguments['input']}"}


class DummyCore:
    def __init__(self, tool: ToolDefinition) -> None:
        self.tool = tool

    def get_tool(self, tool_name: str) -> ToolDefinition:
        if tool_name != self.tool.tool_name:
            raise KeyError(tool_name)
        return self.tool


class AgentToolLoopTest(unittest.IsolatedAsyncioTestCase):
    async def test_tool_result_is_available_to_next_llm_call(self) -> None:
        llm = RecordingLLM()
        tool = RecordingTool()
        agent = Agent(
            agent_id="researcher",
            llm_handler=llm,
            character_prompt="Use tools.",
            tools=[tool],
            core=DummyCore(tool),
        )

        await agent.round_call(rounds=1, user_message="hello")

        second_prev_messages = llm.prev_messages[1]
        self.assertTrue(
            any("seen needle" in message.content for message in second_prev_messages),
            second_prev_messages,
        )


if __name__ == "__main__":
    unittest.main()
