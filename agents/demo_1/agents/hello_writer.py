from core.agent import Agent
from core.results import AgentRoundResult, ToolRequest


class HelloWriterAgent(Agent):
    """A minimal agent that writes hello.txt without calling an LLM."""

    async def round_call(self, rounds, user_message, additional_prompt=None):
        if not getattr(self, "_has_written", False):
            self._has_written = True
            return AgentRoundResult(
                rounds=rounds,
                user_message=user_message,
                assistant_message="Writing hello.txt to workspace...",
                tool_requests=[
                    ToolRequest(
                        id="write_hello",
                        tool="file_writer",
                        args={"path": "hello.txt", "content": "Hello world!"},
                    )
                ],
            )
        return AgentRoundResult(
            rounds=rounds,
            user_message=user_message,
            assistant_message="Done! hello.txt has been written with 'Hello world!'.",
        )


AGENT = {
    "agent_id": "hello_writer",
    "name": "Hello Writer",
    "prompt_text": "You are a hello writer. Write 'Hello world!' to hello.txt.",
    "tools": ["file_writer"],
    "tool_execution_mode": "external",
}

AGENT_CLASS = HelloWriterAgent
