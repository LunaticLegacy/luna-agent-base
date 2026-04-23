from __future__ import annotations

import asyncio
import inspect
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sys
import types

from flask import Flask

sys.modules.setdefault("asyncpg", types.ModuleType("asyncpg"))
redis_module = types.ModuleType("redis")
redis_asyncio_module = types.ModuleType("redis.asyncio")
redis_module.asyncio = redis_asyncio_module
sys.modules.setdefault("redis", redis_module)
sys.modules.setdefault("redis.asyncio", redis_asyncio_module)

litellm_module = types.ModuleType("litellm")
litellm_module.completion = lambda **kwargs: None
sys.modules.setdefault("litellm", litellm_module)

openai_module = types.ModuleType("openai")
openai_types_module = types.ModuleType("openai.types")
openai_chat_module = types.ModuleType("openai.types.chat")


class DummyOpenAI:
    pass


openai_module.OpenAI = DummyOpenAI
openai_chat_module.ChatCompletion = object
openai_types_module.chat = openai_chat_module
openai_module.types = openai_types_module
sys.modules.setdefault("openai", openai_module)
sys.modules.setdefault("openai.types", openai_types_module)
sys.modules.setdefault("openai.types.chat", openai_chat_module)

from web.app_factory import create_app
from web.runs import RunRecord


class DummyValidation:
    is_valid = True
    errors: list[str] = []
    warnings: list[str] = []


class DummyGraphNode:
    def __init__(self, node_id: int, node_name: str, node_type: str, next_node_ids: list[int] | None = None) -> None:
        self.node_id = node_id
        self.node_name = node_name
        self.node_type = node_type
        self.next_node_ids = next_node_ids or []
        self.metadata = {"node": node_name}


class DummyGraph:
    graph_name = "demo-graph"
    entry_node_id = 1
    exit_node_id = 2

    def __init__(self) -> None:
        self.nodes = {
            1: DummyGraphNode(1, "start", "AgentNode", [2]),
            2: DummyGraphNode(2, "end", "ToolNode", []),
        }
        self.edges = [SimpleNamespace(from_node_id=1, to_node_id=2, label="next", condition=None, priority=0)]

    async def run(self, core, initial_payload, rounds=0, **kwargs):
        return SimpleNamespace(
            rounds=rounds or 1,
            payload={"initial_payload": initial_payload, "core": core.name},
            trace=[{"event": "done"}],
            metadata={"meta_mode": kwargs.get("meta_mode", False)},
        )


class DummyAgent:
    async def round_call(self, *, rounds: int, user_message: str, additional_prompt=None):
        return {"rounds": rounds, "message": user_message, "additional_prompt": additional_prompt}

    def get_context_snapshot(self):
        return {"context": "ok"}


class DummyCore:
    def __init__(self) -> None:
        self.name = "demo-core"
        self._graph = DummyGraph()
        self.tools = {"tool-a": object()}

    def list_agents(self):
        return [DummyAgent()]

    def list_skills(self):
        return ["skill-a"]

    def get_execution_graph(self):
        return self._graph

    def check_execution_graph_available(self):
        return DummyValidation()

    def get_agent(self, agent_id: str):
        return DummyAgent()


class DummySwarm:
    def __init__(self) -> None:
        self.manifest = SimpleNamespace(
            swarm_name="demo",
            agent_files=["agents/demo.py"],
            graph_file="graph.toml",
        )
        self.manifest_path = Path("/tmp/demo/manifest.toml")
        self.package_path = Path("/tmp/demo")
        self.core = DummyCore()


class DummyRunRegistry:
    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}

    def launch_run(self, **kwargs):
        record = RunRecord(run_id="run-1", swarm_name=kwargs["swarm_name"], status="completed")
        record._done = True
        self._runs[record.run_id] = record
        return record

    def get_run(self, run_id: str):
        return self._runs.get(run_id)

    def active_run_count(self, swarm_name: str | None = None) -> int:
        return 0

    def active_run_ids(self, swarm_name: str | None = None) -> list[str]:
        return []


class DummyRuntimeRegistry:
    def __init__(self) -> None:
        self.swarms = {"demo": DummySwarm()}
        self.runs = DummyRunRegistry()
        self.load_error = None

    def get_swarm(self, swarm_name: str):
        if swarm_name not in self.swarms:
            raise KeyError(swarm_name)
        return self.swarms[swarm_name]


class RouteSmokeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = DummyRuntimeRegistry()
        self._tmpdir = tempfile.TemporaryDirectory()
        config_path = Path(self._tmpdir.name) / "config.toml"
        original_ensure_sync = Flask.ensure_sync

        def ensure_sync(self, func):
            if inspect.iscoroutinefunction(func):
                def wrapper(*args, **kwargs):
                    return asyncio.run(func(*args, **kwargs))

                return wrapper
            return original_ensure_sync(self, func)

        self.addCleanup(self._tmpdir.cleanup)
        self._runtime_patch = patch("web.app_factory.RuntimeRegistry.from_config_path", return_value=self.runtime)
        self._content_patch = patch("web.app_factory.ContentStore.from_runtime_registry", return_value=SimpleNamespace())
        self._ensure_patch = patch.object(Flask, "ensure_sync", new=ensure_sync)
        for patcher in (self._runtime_patch, self._content_patch, self._ensure_patch):
            patcher.start()
            self.addCleanup(patcher.stop)

        self.app = create_app(config_path)
        self.client = self.app.test_client()

    def test_public_swarm_routes_resolve(self) -> None:
        detail_response = self.client.get("/api/swarms/demo")
        self.assertEqual(detail_response.status_code, 200)
        detail = detail_response.get_json()
        self.assertTrue(detail["success"])
        self.assertEqual(detail["swarm"]["swarm_name"], "demo")

        graph_response = self.client.get("/api/swarms/demo/graph")
        self.assertEqual(graph_response.status_code, 200)
        graph = graph_response.get_json()
        self.assertTrue(graph["success"])
        self.assertEqual(graph["graph"]["graph_name"], "demo-graph")

        run_response = self.client.post("/api/swarms/demo/run", json={"input": {"hello": "world"}, "rounds": 2})
        self.assertEqual(run_response.status_code, 200)
        run_payload = run_response.get_json()
        self.assertTrue(run_payload["success"])
        self.assertEqual(run_payload["rounds"], 2)

        background_response = self.client.post("/api/swarms/demo/runs", json={"input": {"hello": "world"}})
        self.assertEqual(background_response.status_code, 202)
        background_payload = background_response.get_json()
        self.assertTrue(background_payload["success"])
        run_snapshot = background_payload["run"]
        self.assertEqual(run_snapshot["events_url"], f"/api/swarms/runs/{run_snapshot['run_id']}/events")
        self.assertEqual(run_snapshot["status_url"], f"/api/swarms/runs/{run_snapshot['run_id']}")

        stream_response = self.client.get(f"/api/swarms/runs/{run_snapshot['run_id']}/events")
        self.assertEqual(stream_response.status_code, 200)
        stream_text = stream_response.get_data(as_text=True)
        self.assertIn("event: run.snapshot", stream_text)
        self.assertIn(f"\"status_url\": \"/api/swarms/runs/{run_snapshot['run_id']}\"", stream_text)


if __name__ == "__main__":
    unittest.main()
