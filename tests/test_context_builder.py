from __future__ import annotations

import unittest

from core.memory.context_builder import ContextBuilder
from core.memory.episode_graph import EpisodeGraph
from core.memory.memory_store import MemoryStore


class TestContextBuilder(unittest.TestCase):
    def setUp(self) -> None:
        self.builder = ContextBuilder(max_context_nodes=6)
        self.graph = EpisodeGraph()
        self.store = MemoryStore()

    def test_prompt_partitions(self) -> None:
        n0 = self.graph.add_node("hello", "hi there")
        n1 = self.graph.add_node("what is pi", "pi is 3.14", parent_ids={n0})

        # Add various memory types
        m_pinned = self.store.add_memory(
            content="E=mc²", kind="formula", pinned=True, packable=False, status="committed", created_turn_id="turn_1"
        )
        m_timeline = self.store.add_memory(
            content="Deadline is Friday", kind="timeline_constraint", status="committed", created_turn_id="turn_1"
        )
        m_semantic = self.store.add_memory(
            content="User likes dark mode", kind="preference", status="committed", created_turn_id="turn_1"
        )
        # Candidate memory should not appear
        self.store.add_memory(
            content="Candidate fact", kind="fact", status="candidate", created_turn_id="turn_2"
        )

        plan = self.builder.build(
            episode_graph_nodes=self.graph.nodes,
            selected_node_ids=[n1],
            memories=self.store.get_all_memories(),
            current_turn_id="turn_2",
        )

        # Flatten all prompt content for inspection
        all_text = "\n".join(m["content"] for m in plan.prompt_messages)

        # Verify partitions exist
        self.assertIn("Pinned Memory", all_text)
        self.assertIn("Timeline Constraints", all_text)
        self.assertIn("Semantic Memory", all_text)
        self.assertIn("Recent Turns", all_text)

        # Verify specific memories appear
        self.assertIn("E=mc²", all_text)
        self.assertIn("Deadline is Friday", all_text)
        self.assertIn("User likes dark mode", all_text)

        # Candidate should NOT appear
        self.assertNotIn("Candidate fact", all_text)

        # Verify selected_memory_ids contains committed ones only
        self.assertIn(m_pinned, plan.selected_memory_ids)
        self.assertIn(m_timeline, plan.selected_memory_ids)
        self.assertIn(m_semantic, plan.selected_memory_ids)
        self.assertEqual(len(plan.selected_memory_ids), 3)


if __name__ == "__main__":
    unittest.main()
