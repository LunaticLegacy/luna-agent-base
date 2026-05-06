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


class DummySwarm:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []
        self.execution_graph = SimpleNamespace(
            stop_state={"soft_requested": False, "hard_requested": False, "reason": None}
        )

    def request_soft_stop(self, reason: str | None = None):
        self.calls.append(("soft", reason))
        self.execution_graph.stop_state = {
            "soft_requested": True,
            "hard_requested": False,
            "reason": reason,
        }
        return self

    def request_hard_stop(self, reason: str | None = None):
        self.calls.append(("hard", reason))
        self.execution_graph.stop_state = {
            "soft_requested": True,
            "hard_requested": True,
            "reason": reason,
        }
        return self


class DummyCore:
    def __init__(self) -> None:
        self.swarms = {"demo": DummySwarm()}

    def get_swarm(self, name: str):
        if name not in self.swarms:
            raise KeyError(name)
        return self.swarms[name]


@unittest.skipIf(create_app is None, "fastapi is not installed in this environment")
class WebServerStopRouteTest(unittest.TestCase):
    def setUp(self) -> None:
        self.core = DummyCore()
        self.app = create_app()
        self.client = TestClient(self.app)
        self._core_patch = patch("web.server._core", new=self.core)
        self._core_patch.start()
        self.addCleanup(self._core_patch.stop)

    def test_stop_route_requests_soft_stop(self) -> None:
        response = self.client.post(
            "/swarms/demo/stop",
            json={"mode": "soft", "reason": "pause-for-review"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["requested"])
        self.assertEqual(payload["mode"], "soft")
        self.assertEqual(payload["reason"], "pause-for-review")
        self.assertEqual(self.core.swarms["demo"].calls, [("soft", "pause-for-review")])
        self.assertTrue(payload["stop_state"]["soft_requested"])
        self.assertFalse(payload["stop_state"]["hard_requested"])

    def test_stop_route_requests_hard_stop(self) -> None:
        response = self.client.post(
            "/swarms/demo/stop",
            json={"mode": "hard", "reason": "abort-now"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["requested"])
        self.assertEqual(payload["mode"], "hard")
        self.assertEqual(payload["reason"], "abort-now")
        self.assertEqual(self.core.swarms["demo"].calls, [("hard", "abort-now")])
        self.assertTrue(payload["stop_state"]["soft_requested"])
        self.assertTrue(payload["stop_state"]["hard_requested"])


if __name__ == "__main__":
    unittest.main()
