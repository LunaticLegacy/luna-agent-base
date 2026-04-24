from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.context_graph import ContextEntry, ContextEntryType, ContextGraph, ContextReference, ContextRelation


class ContextGraphTest(unittest.TestCase):
    def test_context_graph_prunes_and_resolves_references(self) -> None:
        graph = ContextGraph(graph_id="context-demo")
        graph.add_entry(
            ContextEntry(
                id="system",
                summary="system instructions",
                content="System instructions for the swarm.",
                token_count=0,
                timestamp=1.0,
                entry_type=ContextEntryType.SYSTEM,
                is_retained=True,
            )
        )
        graph.add_entry(
            ContextEntry(
                id="claim",
                summary="claim summary",
                content="Claim uses a supporting fact.",
                token_count=0,
                timestamp=3.0,
                entry_type=ContextEntryType.CLAIM,
            )
        )
        graph.add_entry(
            ContextEntry(
                id="evidence",
                summary="evidence summary",
                content="Evidence " + ("x" * 280),
                token_count=0,
                timestamp=1.5,
                entry_type=ContextEntryType.EVIDENCE,
            )
        )
        graph.add_reference(
            "claim",
            ContextReference(
                target_id="evidence",
                relation=ContextRelation.REFERENCES,
                target_hash=graph.entries["evidence"].content_hash(),
                fallback_inline="evidence summary",
                weight=1.0,
            ),
        )

        prompt = graph.assemble_prompt(anchor_id="claim", token_budget=50)

        self.assertIn("[引用: evidence summary]", prompt)
        self.assertIn("Claim uses a supporting fact.", prompt)

    def test_context_graph_round_trips_through_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "context.json"
            graph = ContextGraph(graph_id="roundtrip")
            graph.add_entry(
                ContextEntry(
                    id="note",
                    summary="note summary",
                    content="A retained note.",
                    token_count=0,
                    timestamp=2.0,
                    entry_type=ContextEntryType.NOTE,
                )
            )
            graph.save(path)

            loaded = ContextGraph.load(path)

            self.assertEqual(loaded.graph_id, "roundtrip")
            self.assertEqual(loaded.entries["note"].summary, "note summary")
            self.assertEqual(loaded.entries["note"].content, "A retained note.")


if __name__ == "__main__":
    unittest.main()
