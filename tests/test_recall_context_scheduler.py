from __future__ import annotations

import unittest
from types import SimpleNamespace

from core.executor_parts.tool_scheduler import ToolScheduler
from core.results import ToolRequest
from core.toodefl import ToolContext


class RecallContextSchedulerTest(unittest.IsolatedAsyncioTestCase):
    async def test_external_scheduler_handles_builtin_recall_context(self) -> None:
        agent = SimpleNamespace(
            recall_context=lambda query: [{"role": "user", "content": f"remembered {query}"}],
        )
        core = SimpleNamespace(
            get_agent_blueprint=lambda agent_id: agent,
        )
        scheduler = ToolScheduler(core)

        result = await scheduler.execute_batch(
            [ToolRequest(id="r1", tool="recall_context", args={"query": "needle"}, required=True)],
            agent_id="agent",
            context=ToolContext(agent_id="agent"),
        )

        self.assertFalse(result.summary["failed_required"])
        self.assertEqual(result.results[0].status, "success")
        self.assertEqual(result.results[0].output["found"], 1)
        self.assertIn("needle", result.results[0].output["messages"][0]["content"])


if __name__ == "__main__":
    unittest.main()
