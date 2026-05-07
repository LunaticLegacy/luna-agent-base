from __future__ import annotations

from pathlib import Path

from core import Core


def _write_package(root: Path) -> Path:
    package_root = root / "sample_agent"
    (package_root / "agents").mkdir(parents=True)
    (package_root / "workspace").mkdir(parents=True)

    (package_root / "graph.py").write_text(
        """
from core import AgentNode, ExecutionGraph


def build_graph(core):
    graph = ExecutionGraph("sample_agent")
    graph.add_node(
        AgentNode(
            node_id=1,
            node_name="planner",
            agent_id="planner",
        )
    )
    graph.set_entry(1)
    graph.set_exit(1)
    return graph
""".strip()
        + "\n",
        encoding="utf-8",
    )

    (package_root / "agents" / "planner.py").write_text(
        'AGENT = {"agent_id": "planner", "character_prompt": "Planner"}\n',
        encoding="utf-8",
    )

    (package_root / "swarm.toml").write_text(
        """
[swarm]
name = "sample_agent"
graph_file = "graph.py"
agent_files = ["agents/planner.py"]

[llm.default]
provider = "litellm"
api_url = "https://example.com"
api_key = "test-key"
model = "demo-model"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return package_root


def test_initialize_agent_packages_classifies_valid_packages(tmp_path: Path) -> None:
    package_root = _write_package(tmp_path)

    core = Core()
    inventory = core.initialize_agent_packages(tmp_path)

    assert len(inventory["valid"]) == 1
    assert len(inventory["invalid"]) == 0
    assert "sample_agent" in core.swarms

    record = core.valid_agent_packages["sample_agent"]
    assert record.package_root == package_root
    assert record.workspace_root == package_root / "workspace"
    assert record.valid is True
    assert record.swarm is not None
    assert record.swarm_name == "sample_agent"
    assert record.swarm.execution_graph is not None
