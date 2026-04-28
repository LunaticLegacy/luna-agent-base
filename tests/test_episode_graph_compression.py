from __future__ import annotations

import unittest

from core.memory.episode_graph import EpisodeGraph, CyclicGraphError


class TestEpisodeGraphCompression(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.graph = EpisodeGraph()
        self.summaries: list[str] = []

    async def _fake_summarize(self, prompt: str, system_prompt: str | None = None) -> str:
        return "[摘要] " + prompt[:80]

    async def test_compression_creates_summary_node(self) -> None:
        n0 = self.graph.add_node("u0", "a0")
        n1 = self.graph.add_node("u1", "a1", parent_ids={n0})
        n2 = self.graph.add_node("u2", "a2", parent_ids={n1})
        n3 = self.graph.add_node("u3", "a3", parent_ids={n2})
        n4 = self.graph.add_node("u4", "a4", parent_ids={n3})

        summary_id = await self.graph.compress_ancestors(
            n4, self._fake_summarize, max_nodes=8, keep_recent=2
        )
        self.assertIsNotNone(summary_id)
        self.assertIn(summary_id, self.graph.nodes)
        summary_node = self.graph.nodes[summary_id]
        self.assertTrue(summary_node.is_summary)
        self.assertGreater(len(summary_node.summarizes), 0)

    async def test_compressed_nodes_are_archived(self) -> None:
        n0 = self.graph.add_node("u0", "a0")
        n1 = self.graph.add_node("u1", "a1", parent_ids={n0})
        n2 = self.graph.add_node("u2", "a2", parent_ids={n1})
        n3 = self.graph.add_node("u3", "a3", parent_ids={n2})
        n4 = self.graph.add_node("u4", "a4", parent_ids={n3})

        summary_id = await self.graph.compress_ancestors(
            n4, self._fake_summarize, max_nodes=8, keep_recent=2
        )
        self.assertIsNotNone(summary_id)
        compressed = self.graph.nodes[summary_id].summarizes
        self.assertGreater(len(compressed), 0)
        for cid in compressed:
            node = self.graph.nodes[cid]
            self.assertTrue(node.archived)
            self.assertFalse(node.active)
            self.assertIn(summary_id, node.summarized_by)

    async def test_active_path_correct(self) -> None:
        n0 = self.graph.add_node("u0", "a0")
        n1 = self.graph.add_node("u1", "a1", parent_ids={n0})
        n2 = self.graph.add_node("u2", "a2", parent_ids={n1})
        n3 = self.graph.add_node("u3", "a3", parent_ids={n2})
        n4 = self.graph.add_node("u4", "a4", parent_ids={n3})

        summary_id = await self.graph.compress_ancestors(
            n4, self._fake_summarize, max_nodes=8, keep_recent=2
        )
        self.assertIsNotNone(summary_id)
        # Active nodes should not include archived ones
        active = self.graph.get_active_nodes()
        for cid in self.graph.nodes[summary_id].summarizes:
            self.assertNotIn(cid, active)
        # Summary node should be active
        self.assertIn(summary_id, active)
        # Recent nodes should be active
        self.assertIn(n3, active)
        self.assertIn(n4, active)

    async def test_no_compression_when_chain_too_short(self) -> None:
        n0 = self.graph.add_node("u0", "a0")
        n1 = self.graph.add_node("u1", "a1", parent_ids={n0})
        result = await self.graph.compress_ancestors(
            n1, self._fake_summarize, max_nodes=8, keep_recent=2
        )
        self.assertIsNone(result)

    async def test_graph_persistence_roundtrip(self) -> None:
        n0 = self.graph.add_node("u0", "a0")
        n1 = self.graph.add_node("u1", "a1", parent_ids={n0})
        snapshot = self.graph.to_dict()
        restored = EpisodeGraph.from_dict(snapshot)
        self.assertEqual(set(restored.nodes.keys()), {n0, n1})
        self.assertEqual(restored.nodes[n1].parent_ids, {n0})
        self.assertEqual(restored.nodes[n0].child_ids, {n1})


if __name__ == "__main__":
    unittest.main()
