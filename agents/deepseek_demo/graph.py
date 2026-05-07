from __future__ import annotations

from pathlib import Path

from modules.llm_fetcher import Agent, AgentSwarm
from tools.command_runner_tool import create_command_runner_tools
from tools.file_editor_tool import create_file_editor_tools
from tools.file_reader_tool import create_file_reader_tools
from tools.file_writer_tool import create_file_writer_tools
from tools.search_tool import create_search_tools

PACKAGE_ROOT = Path(__file__).resolve().parent


def _read_prompt(name: str) -> str:
    prompt_path = PACKAGE_ROOT / "skills" / f"{name}.prompt.md"
    return prompt_path.read_text(encoding="utf-8")


def _register_tools(swarm: AgentSwarm) -> None:
    swarm.add_tools(
        [
            *create_file_reader_tools(),
            *create_file_editor_tools(),
            *create_file_writer_tools(),
            *create_command_runner_tools(),
            *create_search_tools(),
        ]
    )


def build_graph(core):
    if not isinstance(core, AgentSwarm):
        raise TypeError("build_graph() expects an AgentSwarm instance")

    swarm = core
    _register_tools(swarm)

    swarm.add_input("input")
    swarm.add_output("output")

    swarm.add_agent("requirement_analyst", _read_prompt("requirement_analyst"))
    swarm.add_agent("coder", _read_prompt("coder"))
    swarm.add_agent("summarizer", _read_prompt("summarizer"))

    reviewer_agent = Agent(
        llm_handler=swarm._llm_fetcher,
        system_prompt=_read_prompt("reviewer"),
        tools=list(swarm.tool_registry._tools.values()),
    )
    swarm._agents["reviewer"] = reviewer_agent
    swarm.add_router(
        "reviewer",
        routes={
            "revise": "coder",
            "approve": "summarizer",
        },
        agent=reviewer_agent,
        default_route="approve",
    )

    swarm.connect("input", "requirement_analyst")
    swarm.connect("requirement_analyst", "coder")
    swarm.connect("coder", "reviewer")
    swarm.connect("reviewer", "coder", label="revise")
    swarm.connect("reviewer", "summarizer", label="approve")
    swarm.connect("summarizer", "output")

    return swarm.execution_graph
