from __future__ import annotations

import unittest

from core.memory.memory_store import MemoryStore
from core.memory.lifecycle import MemoryLifecycle


class TestPinnedMemory(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MemoryStore()

    def test_formula_defaults_pinned_not_packable(self) -> None:
        pinned, packable = MemoryLifecycle.default_pinned_and_packable("formula")
        self.assertTrue(pinned)
        self.assertFalse(packable)

    def test_constraint_defaults_pinned_not_packable(self) -> None:
        pinned, packable = MemoryLifecycle.default_pinned_and_packable("constraint")
        self.assertTrue(pinned)
        self.assertFalse(packable)

    def test_api_contract_defaults_pinned_not_packable(self) -> None:
        pinned, packable = MemoryLifecycle.default_pinned_and_packable("api_contract")
        self.assertTrue(pinned)
        self.assertFalse(packable)

    def test_fact_defaults_not_pinned_packable(self) -> None:
        pinned, packable = MemoryLifecycle.default_pinned_and_packable("fact")
        self.assertFalse(pinned)
        self.assertTrue(packable)

    def test_pinned_memory_not_compressed(self) -> None:
        # Pinned memories are independent of compression, but packable=False
        # means the associated context should not be compressed.
        # Here we verify the store records packable=False correctly.
        mid = self.store.add_memory(
            content="E=mc²",
            kind="formula",
            pinned=True,
            packable=False,
        )
        mem = self.store.get_memory(mid)
        self.assertIsNotNone(mem)
        self.assertTrue(mem.pinned)
        self.assertFalse(mem.packable)
        pinned_list = self.store.get_pinned_memories()
        self.assertIn(mem, pinned_list)

    def test_canonical_duplicate_not_created(self) -> None:
        content1 = "|α|² + |β|² = 1"
        canonical1 = MemoryStore.normalize_formula(content1)
        mid1 = self.store.add_memory(
            content=content1,
            kind="formula",
            canonical_key=canonical1,
            pinned=True,
            packable=False,
        )

        content2 = "|\\alpha|^2 + |\\beta|^2 = 1"
        canonical2 = MemoryStore.normalize_formula(content2)
        # After normalization they should match
        self.assertEqual(canonical1, canonical2)

        mid2 = self.store.add_memory(
            content=content2,
            kind="formula",
            canonical_key=canonical2,
            pinned=True,
            packable=False,
        )
        # Should return existing id
        self.assertEqual(mid1, mid2)
        # Should have merged source_node_ids if any

    def test_canonical_merge_source_nodes_and_tags(self) -> None:
        canonical = MemoryStore.normalize_formula("1/√2")
        mid1 = self.store.add_memory(
            content="1/√2",
            kind="formula",
            canonical_key=canonical,
            source_node_ids={"n0"},
            tags={"math"},
        )
        mid2 = self.store.add_memory(
            content="\\frac{1}{\\sqrt{2}}",
            kind="formula",
            canonical_key=canonical,
            source_node_ids={"n1"},
            tags={"physics"},
        )
        self.assertEqual(mid1, mid2)
        mem = self.store.get_memory(mid1)
        self.assertIn("n0", mem.source_node_ids)
        self.assertIn("n1", mem.source_node_ids)
        self.assertIn("math", mem.tags)
        self.assertIn("physics", mem.tags)


if __name__ == "__main__":
    unittest.main()
