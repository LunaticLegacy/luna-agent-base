from __future__ import annotations

from modules.llm_fetcher import AgentSwarm
from tools.file_writer_tool import create_file_writer_tools


def build_graph(core):
    if not isinstance(core, AgentSwarm):
        raise TypeError("build_graph() expects an AgentSwarm instance")

    swarm = core
    swarm.add_tools(create_file_writer_tools())

    swarm.add_input("input")
    swarm.add_output("output")
    swarm.add_agent(
        "hello_writer",
        "You are a hello writer. Write 'Hello world!' to hello.txt.",
    )

    swarm.connect("input", "hello_writer")
    swarm.connect("hello_writer", "output")

    return swarm.execution_graph
