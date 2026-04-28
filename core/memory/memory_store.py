from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Optional, Set

from .types import KeyMemory


def _normalize_formula(content: str) -> str:
    """Generate a canonical key for formula-like memories to deduplicate.

    Normalizes:
    - Removes LaTeX commands
    - Removes special symbols and spaces
    - Unifies Unicode superscripts
    - Keeps only lowercase letters, digits, and basic operators
    """
    normalized = content.lower()
    # Remove LaTeX commands
    normalized = re.sub(r"\\[a-zA-Z]+", "", normalized)
    # Remove special symbols and spaces
    normalized = re.sub(r"[\\{}()\[\]$\s|⟨⟩<>⟨⟩]", "", normalized)
    # Unify Unicode superscripts (simplified)
    normalized = normalized.replace("²", "2").replace("³", "3").replace("⁴", "4")
    # Unify caret superscripts so x^2 and x² match
    normalized = re.sub(r"\^(\d)", r"\1", normalized)
    # Keep only letters, digits, and basic operators
    normalized = re.sub(r"[^a-z0-9=+\-*/]", "", normalized)
    return normalized


class MemoryStore:
    """Storage for KeyMemory objects with tag indexing and canonical dedup."""

    def __init__(self) -> None:
        self.memories: Dict[str, KeyMemory] = {}
        self._tag_index: Dict[str, Set[str]] = {}
        self._canonical_index: Dict[str, str] = {}  # canonical_key -> memory_id

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memories": {mid: mem.to_dict() for mid, mem in self.memories.items()},
            "canonical_index": dict(self._canonical_index),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryStore":
        store = cls()
        for mid, mem_data in data.get("memories", {}).items():
            store.memories[mid] = KeyMemory.from_dict(mem_data)
        store._canonical_index = dict(data.get("canonical_index", {}))
        # Rebuild tag index
        for mem in store.memories.values():
            for tag in mem.tags:
                store._tag_index.setdefault(tag, set()).add(mem.memory_id)
        return store

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add_memory(
        self,
        content: str,
        kind: str = "fact",
        source_node_ids: Optional[Set[str]] = None,
        tags: Optional[Set[str]] = None,
        pinned: bool = False,
        packable: bool = True,
        canonical_key: Optional[str] = None,
        created_turn_id: Optional[str] = None,
        status: str = "candidate",
        confidence: float = 1.0,
        memory_id: Optional[str] = None,
    ) -> str:
        """Add a KeyMemory. If canonical_key already exists, merge source_node_ids and tags."""
        if canonical_key and canonical_key in self._canonical_index:
            existing_id = self._canonical_index[canonical_key]
            existing = self.memories[existing_id]
            if source_node_ids:
                existing.source_node_ids.update(source_node_ids)
            if tags:
                existing.tags.update(tags)
                for tag in tags:
                    self._tag_index.setdefault(tag, set()).add(existing_id)
            return existing_id

        mid = memory_id or uuid.uuid4().hex
        memory = KeyMemory(
            memory_id=mid,
            content=content,
            kind=kind,
            tags=set(tags) if tags else set(),
            source_node_ids=set(source_node_ids) if source_node_ids else set(),
            pinned=pinned,
            packable=packable,
            status=status,
            created_turn_id=created_turn_id,
            canonical_key=canonical_key,
            confidence=confidence,
        )
        self.memories[mid] = memory

        for tag in memory.tags:
            self._tag_index.setdefault(tag, set()).add(mid)

        if canonical_key:
            self._canonical_index[canonical_key] = mid

        return mid

    def get_memory(self, memory_id: str) -> Optional[KeyMemory]:
        return self.memories.get(memory_id)

    def get_pinned_memories(self) -> List[KeyMemory]:
        return [m for m in self.memories.values() if m.pinned]

    def get_committed_memories(self) -> List[KeyMemory]:
        return [m for m in self.memories.values() if m.status == "committed"]

    def commit_candidates(self, turn_id: str) -> List[str]:
        """Promote candidate memories from *turn_id* to committed."""
        committed_ids: List[str] = []
        for mem in self.memories.values():
            if mem.status == "candidate" and mem.created_turn_id == turn_id:
                mem.status = "committed"
                committed_ids.append(mem.memory_id)
        return committed_ids

    def reject_candidates(self, turn_id: str) -> List[str]:
        """Reject candidate memories from *turn_id*."""
        rejected_ids: List[str] = []
        for mem in self.memories.values():
            if mem.status == "candidate" and mem.created_turn_id == turn_id:
                mem.status = "rejected"
                rejected_ids.append(mem.memory_id)
        return rejected_ids

    def remove_memory(self, memory_id: str) -> bool:
        mem = self.memories.pop(memory_id, None)
        if mem is None:
            return False
        for tag in mem.tags:
            if tag in self._tag_index:
                self._tag_index[tag].discard(memory_id)
                if not self._tag_index[tag]:
                    del self._tag_index[tag]
        if mem.canonical_key and self._canonical_index.get(mem.canonical_key) == memory_id:
            del self._canonical_index[mem.canonical_key]
        return True

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search_by_tags(self, tags: Set[str]) -> List[KeyMemory]:
        if not tags:
            return []
        candidate_ids: Optional[Set[str]] = None
        for tag in tags:
            ids = self._tag_index.get(tag, set())
            if candidate_ids is None:
                candidate_ids = set(ids)
            else:
                candidate_ids &= ids
            if not candidate_ids:
                return []
        return [self.memories[mid] for mid in sorted(candidate_ids or [])]

    def search_by_text(self, query: str) -> List[KeyMemory]:
        query_lower = query.lower()
        results: List[KeyMemory] = []
        for mem in self.memories.values():
            if query_lower in mem.content.lower():
                results.append(mem)
                continue
            if any(query_lower in t.lower() for t in mem.tags):
                results.append(mem)
                continue
        return results

    def get_all_memories(self) -> List[KeyMemory]:
        return [self.memories[mid] for mid in sorted(self.memories.keys())]

    @staticmethod
    def normalize_formula(content: str) -> str:
        return _normalize_formula(content)
