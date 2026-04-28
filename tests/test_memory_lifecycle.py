from __future__ import annotations

import unittest

from core.memory.memory_store import MemoryStore
from core.memory.lifecycle import can_inject_memory
from core.memory.types import KeyMemory


class TestMemoryLifecycle(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MemoryStore()

    def test_candidate_memory_cannot_inject_current_turn(self) -> None:
        mem = KeyMemory(
            memory_id="m1",
            content="test",
            status="candidate",
            created_turn_id="run_turn_1",
        )
        self.assertFalse(can_inject_memory(mem, "run_turn_1"))

    def test_committed_memory_can_inject_subsequent_turn(self) -> None:
        mem = KeyMemory(
            memory_id="m1",
            content="test",
            status="committed",
            created_turn_id="run_turn_1",
        )
        self.assertTrue(can_inject_memory(mem, "run_turn_2"))

    def test_committed_memory_same_turn_cannot_inject(self) -> None:
        mem = KeyMemory(
            memory_id="m1",
            content="test",
            status="committed",
            created_turn_id="run_turn_1",
        )
        self.assertFalse(can_inject_memory(mem, "run_turn_1"))

    def test_commit_candidates_promotes_only_matching_turn(self) -> None:
        self.store.add_memory(
            content="turn1",
            created_turn_id="turn_1",
            status="candidate",
            memory_id="m1",
        )
        self.store.add_memory(
            content="turn2",
            created_turn_id="turn_2",
            status="candidate",
            memory_id="m2",
        )
        committed = self.store.commit_candidates("turn_1")
        self.assertEqual(committed, ["m1"])
        self.assertEqual(self.store.get_memory("m1").status, "committed")
        self.assertEqual(self.store.get_memory("m2").status, "candidate")

    def test_current_turn_memory_usage_is_invalid(self) -> None:
        # Simulating: a candidate extracted in current turn is referenced
        mem = KeyMemory(
            memory_id="m1",
            content="test",
            status="candidate",
            created_turn_id="run_turn_1",
        )
        self.assertFalse(can_inject_memory(mem, "run_turn_1"))
        # Even if somehow status is committed but created_turn_id matches,
        # lifecycle blocks it
        mem.status = "committed"
        self.assertFalse(can_inject_memory(mem, "run_turn_1"))


if __name__ == "__main__":
    unittest.main()
