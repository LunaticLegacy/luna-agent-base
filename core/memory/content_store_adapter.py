"""Bridge between the memory subsystem and the web ContentStore.

``ContentStoreMemoryAdapter`` pushes committed KeyMemory items into the
web-layer ContentStore so that the frontend can display them alongside
other content.  This is a lightweight alpha-phase bridge; canonical
persistence still happens via the JSON file backing MemoryRuntime.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from web.content_store import ContentStore

from .memory_store import MemoryStore


class ContentStoreMemoryAdapter:
    """Adapter to sync committed KeyMemory items into web.ContentStore.

    This is a lightweight bridge for the alpha phase; it does not
    replace the JSON file persistence in MemoryRuntime.

    Attributes:
        memory_store: Source of committed memories.
        content_store: Optional web-layer sink.  If None, sync is a no-op.
    """

    def __init__(self, memory_store: MemoryStore, content_store: Optional["ContentStore"] = None) -> None:
        self.memory_store = memory_store
        self.content_store = content_store

    def sync_committed(self) -> List[Dict[str, Any]]:
        """Push all committed memories into ContentStore.memory list.

        Returns:
            The list of synced items (empty if no ContentStore is attached).
        """
        if self.content_store is None:
            return []
        committed = self.memory_store.get_committed_memories()
        synced: List[Dict[str, Any]] = []
        for mem in committed:
            item = {
                "id": mem.memory_id,
                "type": "memory",
                "kind": mem.kind,
                "content": mem.content,
                "tags": sorted(mem.tags),
                "pinned": mem.pinned,
                "status": mem.status,
                "created_turn_id": mem.created_turn_id,
                "canonical_key": mem.canonical_key,
            }
            try:
                self.content_store.create_memory(item)
            except Exception:
                # If already exists or store rejects, skip rather than abort.
                pass
            synced.append(item)
        return synced
