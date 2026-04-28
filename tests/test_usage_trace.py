from __future__ import annotations

import unittest

from core.memory.usage_trace import UsageTraceTracker
from core.memory.types import KeyMemory


class TestUsageTrace(unittest.TestCase):
    def setUp(self) -> None:
        self.memories = {
            "m0": KeyMemory(memory_id="m0", content="词源定义：御宅", tags={"词源"}, status="committed", created_turn_id="turn_1"),
            "m1": KeyMemory(memory_id="m1", content="互联网改变文化生态", tags={"互联网"}, status="committed", created_turn_id="turn_1"),
            "m2": KeyMemory(memory_id="m2", content="Candidate from this turn", status="candidate", created_turn_id="turn_2"),
        }

    def test_injected_memory_recorded(self) -> None:
        tracker = UsageTraceTracker(
            injected_memory_ids=["m0", "m1"],
            memory_lookup=self.memories,
            current_turn_id="turn_2",
        )
        trace = tracker.verify_all("answer using 词源")
        self.assertEqual(trace.injected_memory_ids, ["m0", "m1"])

    def test_declared_unused_memory_invalid(self) -> None:
        # Agent claims to use m3 which was never injected
        tracker = UsageTraceTracker(
            injected_memory_ids=["m0"],
            memory_lookup=self.memories,
            current_turn_id="turn_2",
        )
        tracker.record_declaration("m3", "用于解释词源")
        trace = tracker.verify_all("answer")
        self.assertIn("m3", trace.invalid_memory_refs)
        self.assertNotIn("m3", trace.verified_used_memory_ids)

    def test_candidate_memory_usage_invalid(self) -> None:
        tracker = UsageTraceTracker(
            injected_memory_ids=["m0", "m2"],
            memory_lookup=self.memories,
            current_turn_id="turn_2",
        )
        tracker.record_declaration("m2", "用于说明当前轮内容")
        trace = tracker.verify_all("answer using Candidate from this turn")
        self.assertIn("m2", trace.invalid_memory_refs)

    def test_verified_used_when_content_match(self) -> None:
        tracker = UsageTraceTracker(
            injected_memory_ids=["m0"],
            memory_lookup=self.memories,
            current_turn_id="turn_2",
        )
        tracker.record_declaration("m0", "用于解释词源")
        trace = tracker.verify_all("这个词语的词源非常重要")
        self.assertIn("m0", trace.verified_used_memory_ids)
        self.assertNotIn("m0", trace.invalid_memory_refs)

    def test_parse_declarations(self) -> None:
        text = """[Injected Memories]
  M0 pinned formula
  M3 pinned culture_ecology

[Declared Memory Usage]
  M0 -> 用于解释词源
  M3 -> 用于说明互联网和轻小说改变文化生态
"""
        decls = UsageTraceTracker.parse_declarations(text)
        self.assertIn("0", decls)
        self.assertIn("3", decls)
        self.assertIn("词源", decls["0"])


if __name__ == "__main__":
    unittest.main()
