from __future__ import annotations

import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch

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

try:  # pragma: no cover - environment dependent
    from fastapi.testclient import TestClient
    from web.server import create_app
except ModuleNotFoundError:  # pragma: no cover - environment dependent
    TestClient = None
    create_app = None


class DummyCore:
    def __init__(self) -> None:
        self.execution_graph = {
            "graph_name": "demo",
            "nodes": {"1": {"type": "agent", "class": "AgentNode"}},
            "edges": [{"source": "1", "target": "1", "label": "loop"}],
        }
        self.thinking_graph = {
            "format": "thinking-graph/config",
            "schema_version": "1.0",
            "version": 3,
            "next_object_id": 5,
            "transaction_id": 2,
            "nodes": {
                "0": {
                    "id": 0,
                    "node_type": "goal",
                    "info": "demo goal",
                    "tags": [],
                    "created_by": "tester",
                    "confidence": 1.0,
                    "description": "",
                    "payload": {},
                }
            },
            "edges": {},
            "transaction_log": [],
            "node_count": 1,
            "edge_count": 0,
            "transaction_count": 0,
            "last_transaction_id": None,
        }
        self.swarms = {"demo": object()}

    def get_execution_graph_snapshot(self, name: str):
        if name not in self.swarms:
            raise KeyError(name)
        return self.execution_graph

    def get_thinking_graph_snapshot(self, name: str):
        if name not in self.swarms:
            raise KeyError(name)
        return self.thinking_graph


@unittest.skipIf(create_app is None, "fastapi is not installed in this environment")
class GraphRouteSplitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.core = DummyCore()
        self.app = create_app()
        self.client = TestClient(self.app)
        self._core_patch = patch("web.server._core", new=self.core)
        self._core_patch.start()
        self.addCleanup(self._core_patch.stop)

    def test_execution_graph_and_thinking_graph_routes_exist(self) -> None:
        execution = self.client.get("/swarms/demo/execution_graph")
        self.assertEqual(execution.status_code, 200)
        execution_payload = execution.json()
        self.assertEqual(execution_payload["name"], "demo")
        self.assertIn("nodes", execution_payload)

        thinking = self.client.get("/swarms/demo/thinking_graph")
        self.assertEqual(thinking.status_code, 200)
        thinking_payload = thinking.json()
        self.assertEqual(thinking_payload["name"], "demo")
        self.assertEqual(thinking_payload["thinking_graph"]["format"], "thinking-graph/config")

    def test_compatibility_aliases_remain_available(self) -> None:
        legacy_execution = self.client.get("/swarms/demo/graph")
        self.assertEqual(legacy_execution.status_code, 200)
        self.assertIn("edges", legacy_execution.json())

        legacy_thinking = self.client.get("/swarms/demo/thought-graph")
        self.assertEqual(legacy_thinking.status_code, 200)
        self.assertIn("thinking_graph", legacy_thinking.json())


if __name__ == "__main__":
    unittest.main()
