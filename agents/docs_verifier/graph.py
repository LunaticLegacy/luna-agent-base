from __future__ import annotations

from pathlib import Path

from modules.llm_fetcher import AgentSwarm
from tools.echo_tool import create_echo_tools
from tools.file_writer_tool import create_file_writer_tools

PACKAGE_ROOT = Path(__file__).resolve().parent


def _read_prompt(name: str) -> str:
    prompt_path = PACKAGE_ROOT / "skills" / f"{name}.prompt.md"
    return prompt_path.read_text(encoding="utf-8")


def _register_tools(swarm: AgentSwarm) -> None:
    swarm.add_tools(
        [
            *create_file_writer_tools(),
            *create_echo_tools(),
        ]
    )


def build_graph(core):
    if not isinstance(core, AgentSwarm):
        raise TypeError("build_graph() expects an AgentSwarm instance")

    swarm = core
    _register_tools(swarm)

    swarm.add_input("input")
    swarm.add_output("output")

    swarm.add_agent("orchestrator", _read_prompt("orchestrator"))
    swarm.add_agent("backend_verifier", _read_prompt("backend_verifier"))
    swarm.add_agent("frontend_verifier", _read_prompt("frontend_verifier"))
    swarm.add_agent("structure_verifier", _read_prompt("structure_verifier"))
    swarm.add_agent("reviewer", _read_prompt("reviewer"))
    swarm.add_agent("publisher", _read_prompt("publisher"))

    swarm.connect("input", "orchestrator")
    swarm.connect("orchestrator", "backend_verifier")
    swarm.connect("orchestrator", "frontend_verifier")
    swarm.connect("orchestrator", "structure_verifier")
    swarm.connect("backend_verifier", "reviewer")
    swarm.connect("frontend_verifier", "reviewer")
    swarm.connect("structure_verifier", "reviewer")
    swarm.connect("reviewer", "publisher")
    swarm.connect("publisher", "output")

    return swarm.execution_graph
