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

from core.swarm_spec import ApiConfig, SwarmAppConfig
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
        self.reset_calls = 0

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

    def reset_runtime_state(self):
        self.reset_calls += 1


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
        return sum(
            1
            for record in self._runs.values()
            if not record._done and (swarm_name is None or record.swarm_name == swarm_name)
        )

    def active_run_ids(self, swarm_name: str | None = None) -> list[str]:
        return []


class DummyRuntimeRegistry:
    def __init__(self, config_path: Path) -> None:
        self.swarms = {"demo": DummySwarm()}
        self.runs = DummyRunRegistry()
        self.load_error = None
        self.config_path = config_path
        self.root_config = SwarmAppConfig(swarm_root=Path("agents"))

    def get_swarm(self, swarm_name: str):
        if swarm_name not in self.swarms:
            raise KeyError(swarm_name)
        return self.swarms[swarm_name]


class RouteSmokeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        config_path = Path(self._tmpdir.name) / "config.toml"
        config_path.write_text('[app]\nswarm_root = "agents"\n', encoding="utf-8")
        self.runtime = DummyRuntimeRegistry(config_path)
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
        self.assertEqual(self.runtime.swarms["demo"].core.reset_calls, 1)

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
        self.assertEqual(self.runtime.swarms["demo"].core.reset_calls, 2)

    def test_settings_routes_round_trip_config_file(self) -> None:
        response = self.client.get("/api/settings")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["settings"]["api"]["base_url"], "/api")
        self.assertEqual(payload["settings"]["api"]["timeout_seconds"], 30)

        update_response = self.client.put(
            "/api/settings",
            json={
                "api": {
                    "base_url": "/gateway",
                    "timeout_seconds": 42,
                    "sse_reconnect_interval_seconds": 9,
                    "auto_reconnect": False,
                }
            },
        )
        self.assertEqual(update_response.status_code, 200)
        updated = update_response.get_json()
        self.assertTrue(updated["success"])
        self.assertEqual(updated["settings"]["api"]["base_url"], "/gateway")
        self.assertEqual(updated["settings"]["api"]["timeout_seconds"], 42)

        config_text = self.runtime.config_path.read_text(encoding="utf-8")
        self.assertIn('[api]', config_text)
        self.assertIn('base_url = "/gateway"', config_text)
        self.assertIn('timeout_seconds = 42', config_text)
        self.assertIn('sse_reconnect_interval_seconds = 9', config_text)
        self.assertIn('auto_reconnect = false', config_text)
        self.assertIn('require_auth = false', config_text)

    def test_mutating_routes_require_token_when_auth_enabled(self) -> None:
        self.runtime.root_config.api = ApiConfig(require_auth=True, api_token="secret-token")

        unauthorized = self.client.post("/api/swarms/demo/run", json={"input": "hello"})
        self.assertEqual(unauthorized.status_code, 401)
        self.assertFalse(unauthorized.get_json()["success"])
        self.assertEqual(self.runtime.swarms["demo"].core.reset_calls, 0)

        authorized = self.client.post(
            "/api/swarms/demo/run",
            json={"input": "hello"},
            headers={"Authorization": "Bearer secret-token"},
        )
        self.assertEqual(authorized.status_code, 200)
        self.assertTrue(authorized.get_json()["success"])
        self.assertEqual(self.runtime.swarms["demo"].core.reset_calls, 1)

    def test_cors_respects_allowlist(self) -> None:
        self.runtime.root_config.api = ApiConfig(cors_allowed_origins=["http://allowed.example"])

        allowed = self.client.get("/api", headers={"Origin": "http://allowed.example"})
        self.assertEqual(allowed.headers.get("Access-Control-Allow-Origin"), "http://allowed.example")

        denied = self.client.get("/api", headers={"Origin": "http://blocked.example"})
        self.assertNotIn("Access-Control-Allow-Origin", denied.headers)

    def test_rejects_concurrent_run_for_same_swarm(self) -> None:
        active = RunRecord(run_id="run-active", swarm_name="demo", status="running")
        self.runtime.runs._runs[active.run_id] = active

        response = self.client.post("/api/swarms/demo/runs", json={"input": {"hello": "world"}})

        self.assertEqual(response.status_code, 409)
        payload = response.get_json()
        self.assertFalse(payload["success"])
        self.assertIn("already has an active run", payload["error"])
        self.assertEqual(self.runtime.swarms["demo"].core.reset_calls, 0)


if __name__ == "__main__":
    unittest.main()
