from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class EpisodeNode:
    """DAG node representing one agent dialogue turn."""

    node_id: str
    user_content: str
    assistant_content: str
    parent_ids: Set[str] = field(default_factory=set)
    child_ids: Set[str] = field(default_factory=set)
    is_summary: bool = False
    summarizes: Set[str] = field(default_factory=set)
    summarized_by: Set[str] = field(default_factory=set)
    active: bool = True
    archived: bool = False
    created_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "user_content": self.user_content,
            "assistant_content": self.assistant_content,
            "parent_ids": sorted(self.parent_ids),
            "child_ids": sorted(self.child_ids),
            "is_summary": self.is_summary,
            "summarizes": sorted(self.summarizes),
            "summarized_by": sorted(self.summarized_by),
            "active": self.active,
            "archived": self.archived,
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EpisodeNode":
        return cls(
            node_id=str(data["node_id"]),
            user_content=str(data.get("user_content", "")),
            assistant_content=str(data.get("assistant_content", "")),
            parent_ids=set(data.get("parent_ids", [])),
            child_ids=set(data.get("child_ids", [])),
            is_summary=bool(data.get("is_summary", False)),
            summarizes=set(data.get("summarizes", [])),
            summarized_by=set(data.get("summarized_by", [])),
            active=bool(data.get("active", True)),
            archived=bool(data.get("archived", False)),
            created_at=str(data.get("created_at", "")),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class KeyMemory:
    """Extracted key memory independent of the episode graph."""

    memory_id: str
    content: str
    kind: str = "fact"
    tags: Set[str] = field(default_factory=set)
    source_node_ids: Set[str] = field(default_factory=set)
    pinned: bool = False
    packable: bool = True
    status: str = "candidate"
    created_turn_id: Optional[str] = None
    canonical_key: Optional[str] = None
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "content": self.content,
            "kind": self.kind,
            "tags": sorted(self.tags),
            "source_node_ids": sorted(self.source_node_ids),
            "pinned": self.pinned,
            "packable": self.packable,
            "status": self.status,
            "created_turn_id": self.created_turn_id,
            "canonical_key": self.canonical_key,
            "confidence": self.confidence,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KeyMemory":
        return cls(
            memory_id=str(data["memory_id"]),
            content=str(data.get("content", "")),
            kind=str(data.get("kind", "fact")),
            tags=set(data.get("tags", [])),
            source_node_ids=set(data.get("source_node_ids", [])),
            pinned=bool(data.get("pinned", False)),
            packable=bool(data.get("packable", True)),
            status=str(data.get("status", "candidate")),
            created_turn_id=data.get("created_turn_id"),
            canonical_key=data.get("canonical_key"),
            confidence=float(data.get("confidence", 1.0)),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class MemoryContextPlan:
    """Plan produced before a round describing what context to inject."""

    selected_node_ids: List[str] = field(default_factory=list)
    selected_memory_ids: List[str] = field(default_factory=list)
    pack_triggers: List[str] = field(default_factory=list)
    compressed_node_ids: List[str] = field(default_factory=list)
    summary_node_ids: List[str] = field(default_factory=list)
    memory_queries: List[str] = field(default_factory=list)
    prompt_messages: List[Dict[str, str]] = field(default_factory=list)
    token_estimate: Optional[int] = None
    reasoning: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "selected_node_ids": list(self.selected_node_ids),
            "selected_memory_ids": list(self.selected_memory_ids),
            "pack_triggers": list(self.pack_triggers),
            "compressed_node_ids": list(self.compressed_node_ids),
            "summary_node_ids": list(self.summary_node_ids),
            "memory_queries": list(self.memory_queries),
            "prompt_messages": [dict(m) for m in self.prompt_messages],
            "token_estimate": self.token_estimate,
            "reasoning": self.reasoning,
        }


@dataclass
class MemoryUsageTrace:
    """Trace of how injected memories were used in a round."""

    injected_memory_ids: List[str] = field(default_factory=list)
    declared_used_memory_ids: List[str] = field(default_factory=list)
    verified_used_memory_ids: List[str] = field(default_factory=list)
    invalid_memory_refs: List[str] = field(default_factory=list)
    unused_injected_memory_ids: List[str] = field(default_factory=list)
    verification_notes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "injected_memory_ids": list(self.injected_memory_ids),
            "declared_used_memory_ids": list(self.declared_used_memory_ids),
            "verified_used_memory_ids": list(self.verified_used_memory_ids),
            "invalid_memory_refs": list(self.invalid_memory_refs),
            "unused_injected_memory_ids": list(self.unused_injected_memory_ids),
            "verification_notes": dict(self.verification_notes),
        }


@dataclass
class MemoryUpdateResult:
    """Result produced after a round with memory updates."""

    new_node_id: Optional[str] = None
    committed_memory_ids: List[str] = field(default_factory=list)
    extracted_memory_ids: List[str] = field(default_factory=list)
    usage_trace: MemoryUsageTrace = field(default_factory=MemoryUsageTrace)
    applied_ops: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "new_node_id": self.new_node_id,
            "committed_memory_ids": list(self.committed_memory_ids),
            "extracted_memory_ids": list(self.extracted_memory_ids),
            "usage_trace": self.usage_trace.to_dict(),
            "applied_ops": dict(self.applied_ops),
        }
