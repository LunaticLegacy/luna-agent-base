from __future__ import annotations

import asyncio
import unittest

from modules.llm_fetcher.swarm.execution_graph import (
    ExecutionGraph,
    ExecutionNode,
    GraphContext,
)
from modules.llm_fetcher.swarm.runtime_slot import RuntimeSlotManager, SlotStatus


class _BlockingExecutionNode(ExecutionNode):
    def __init__(
        self,
        node_id: str,
        started: asyncio.Event,
        release: asyncio.Event,
        result: str,
    ) -> None:
        super().__init__(node_id, "block")
        self._started = started
        self._release = release
        self._result = result

    async def run(self, ctx: GraphContext, inputs: list[object]) -> str:
        self._started.set()
        await self._release.wait()
        return self._result


class _BlockingTool:
    def __init__(self, started: asyncio.Event, release: asyncio.Event) -> None:
        self.name = "blocking_tool"
        self._started = started
        self._release = release

    async def execute(self, **kwargs):
        self._started.set()
        await self._release.wait()
        return kwargs.get("result", "tool-result")


class ExecutionAndSlotStopTest(unittest.TestCase):
    def test_execution_graph_soft_stop_finishes_current_node_without_downstream(self) -> None:
        async def _run() -> tuple[GraphContext, ExecutionGraph]:
            started = asyncio.Event()
            release = asyncio.Event()
            graph = ExecutionGraph()
            graph.add_input_node("input")
            graph.add_node(_BlockingExecutionNode("mid", started, release, "mid-result"))
            graph.add_output_node(node_id="output")
            graph.connect("input", "mid")
            graph.connect("mid", "output")

            run_task = asyncio.create_task(graph.run(initial_input="seed", entry_node_id="input"))
            await asyncio.wait_for(started.wait(), timeout=1.0)
            graph.request_soft_stop("pause-after-current-node")
            release.set()
            ctx = await asyncio.wait_for(run_task, timeout=1.0)
            return ctx, graph

        ctx, graph = asyncio.run(_run())
        self.assertEqual(ctx.executed, {"input", "mid"})
        self.assertEqual(ctx.node_outputs["mid"], "mid-result")
        self.assertNotIn("output", ctx.executed)
        self.assertEqual(
            graph.stop_state,
            {"soft_requested": False, "hard_requested": False, "reason": None},
        )

    def test_execution_graph_hard_stop_cancels_running_graph(self) -> None:
        async def _run() -> ExecutionGraph:
            started = asyncio.Event()
            release = asyncio.Event()
            graph = ExecutionGraph()
            graph.add_input_node("input")
            graph.add_node(_BlockingExecutionNode("mid", started, release, "mid-result"))
            graph.add_output_node(node_id="output")
            graph.connect("input", "mid")
            graph.connect("mid", "output")

            run_task = asyncio.create_task(graph.run(initial_input="seed", entry_node_id="input"))
            await asyncio.wait_for(started.wait(), timeout=1.0)
            graph.request_hard_stop("abort-now")

            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(run_task, timeout=1.0)
            return graph

        graph = asyncio.run(_run())
        self.assertEqual(
            graph.stop_state,
            {"soft_requested": False, "hard_requested": False, "reason": None},
        )

    def test_runtime_slot_soft_stop_marks_slot_cancelled(self) -> None:
        async def _run() -> tuple[str, RuntimeSlotManager]:
            started = asyncio.Event()
            release = asyncio.Event()
            manager = RuntimeSlotManager(default_timeout=5.0)
            slot_id = await manager.submit(_BlockingTool(started, release), {"result": "ok"})
            await asyncio.wait_for(started.wait(), timeout=1.0)

            requested = await manager.request_soft_stop(slot_id)
            self.assertTrue(requested)
            slot = await manager.poll(slot_id)
            self.assertEqual(slot.status, SlotStatus.CANCELLED)
            self.assertEqual(slot.stop_requested, "soft")
            self.assertEqual(slot.error, "Soft stop requested")
            return slot_id, manager

        slot_id, manager = asyncio.run(_run())
        slot = asyncio.run(manager.poll(slot_id))
        self.assertEqual(slot.status, SlotStatus.CANCELLED)

    def test_runtime_slot_hard_stop_marks_slot_cancelled(self) -> None:
        async def _run() -> tuple[str, RuntimeSlotManager]:
            started = asyncio.Event()
            release = asyncio.Event()
            manager = RuntimeSlotManager(default_timeout=5.0)
            slot_id = await manager.submit(_BlockingTool(started, release), {"result": "ok"})
            await asyncio.wait_for(started.wait(), timeout=1.0)

            requested = await manager.request_hard_stop(slot_id)
            self.assertTrue(requested)
            for _ in range(50):
                slot = await manager.poll(slot_id)
                if slot.status == SlotStatus.CANCELLED:
                    break
                await asyncio.sleep(0.01)
            else:
                self.fail("hard stop did not cancel the slot")
            self.assertEqual(slot.stop_requested, "hard")
            self.assertEqual(slot.error, "Hard stop requested")
            return slot_id, manager

        slot_id, manager = asyncio.run(_run())
        slot = asyncio.run(manager.poll(slot_id))
        self.assertEqual(slot.status, SlotStatus.CANCELLED)


if __name__ == "__main__":
    unittest.main()
