"""Core data types for the Angelus memory subsystem.

Defines the primary dataclasses that represent episode nodes, extracted
key memories, context plans, and usage traces.  All types support
round-trip serialization via ``to_dict`` / ``from_dict`` so that the
memory layer can be persisted to JSON.

Exports:
    - :class:`EpisodeNode`
    - :class:`KeyMemory`
    - :class:`MemoryContextPlan`
    - :class:`MemoryUsageTrace`
    - :class:`MemoryUpdateResult`
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class EpisodeNode:
    """DAG node representing one agent dialogue turn.

    Attributes:
        node_id: Unique identifier for this node.
        user_content: The user's message in this turn.
        assistant_content: The assistant's response in this turn.
        parent_ids: Set of parent node IDs forming the DAG ancestry.
        child_ids: Set of child node IDs derived from this node.
        is_summary: Whether this node is a compressed summary of older turns.
        summarizes: Set of node IDs that this summary subsumes.
        summarized_by: Set of node IDs that subsume this node as a summary.
        active: Whether the node is currently active (not archived).
        archived: Whether the node has been archived after compression.
        created_at: ISO-8601 timestamp when the node was created.
        metadata: Free-form metadata for extensibility.
    """

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
        """Serialize the node to a plain dictionary."""
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
        """Reconstruct an :class:`EpisodeNode` from a plain dictionary.

        Args:
            data: Dictionary previously produced by :meth:`to_dict`.

        Returns:
            A fully populated ``EpisodeNode`` instance.
        """
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
    """Extracted key memory independent of the episode graph.

    A ``KeyMemory`` represents a durable fact, formula, or constraint that
    has been lifted out of the conversation and can be reinjected into
    future prompts.

    Attributes:
        memory_id: Unique identifier for this memory.
        content: The textual content of the memory.
        kind: Semantic category (e.g. ``"fact"``, ``"formula"``, ``"constraint"``).
        tags: Set of searchable tags for retrieval.
        source_node_ids: Episode nodes from which this memory was extracted.
        pinned: If ``True``, the memory is always injected and never packed away.
        packable: If ``True``, the memory may be compressed or summarized.
        status: Lifecycle status — ``"candidate"``, ``"committed"``, or ``"rejected"``.
        created_turn_id: The turn during which this memory was extracted.
        canonical_key: Optional deduplication key (e.g. normalized formula).
        confidence: Confidence score in the range ``[0.0, 1.0]``.
        metadata: Free-form metadata for extensibility.
    """

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
        """Serialize the memory to a plain dictionary."""
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
        """Reconstruct a :class:`KeyMemory` from a plain dictionary.

        Args:
            data: Dictionary previously produced by :meth:`to_dict`.

        Returns:
            A fully populated ``KeyMemory`` instance.
        """
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
    """Plan produced before a round describing what context to inject.

    The planner builds this object so that the runtime knows which episode
    nodes and committed memories should be included in the prompt, which
    nodes were compressed, and what the reasoning was.

    Attributes:
        selected_node_ids: Episode nodes to load into the prompt context.
        selected_memory_ids: Committed memories eligible for injection.
        pack_triggers: Nodes whose ancestor chains were compressed.
        compressed_node_ids: Nodes that were folded into summaries.
        summary_node_ids: New summary nodes created by compression.
        memory_queries: Keywords used to search the memory store.
        prompt_messages: Pre-built prompt messages (if any).
        token_estimate: Estimated token count for the planned context.
        reasoning: Human-readable explanation of the planning decision.
    """

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
        """Serialize the plan to a plain dictionary."""
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
    """Trace of how injected memories were used in a round.

    After a round completes, the runtime compares the memories that were
    declared as "used" by the agent against the ones that were actually
    injected, producing this audit record.

    Attributes:
        injected_memory_ids: Memories that were present in the prompt.
        declared_used_memory_ids: Memories the agent claimed to have used.
        verified_used_memory_ids: Memories whose usage was heuristically confirmed.
        invalid_memory_refs: Declarations that could not be verified.
        unused_injected_memory_ids: Injected memories not referenced by the agent.
        verification_notes: Per-memory diagnostic details.
    """

    injected_memory_ids: List[str] = field(default_factory=list)
    declared_used_memory_ids: List[str] = field(default_factory=list)
    verified_used_memory_ids: List[str] = field(default_factory=list)
    invalid_memory_refs: List[str] = field(default_factory=list)
    unused_injected_memory_ids: List[str] = field(default_factory=list)
    verification_notes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the trace to a plain dictionary."""
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
    """Result produced after a round with memory updates.

    Attributes:
        new_node_id: The episode node created for this turn.
        committed_memory_ids: Candidate memories promoted to committed.
        extracted_memory_ids: New memories extracted during this turn.
        usage_trace: Audit record of how injected memories were used.
        applied_ops: Internal log of all transformations performed.
    """

    new_node_id: Optional[str] = None
    committed_memory_ids: List[str] = field(default_factory=list)
    extracted_memory_ids: List[str] = field(default_factory=list)
    usage_trace: MemoryUsageTrace = field(default_factory=MemoryUsageTrace)
    applied_ops: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the result to a plain dictionary."""
        return {
            "new_node_id": self.new_node_id,
            "committed_memory_ids": list(self.committed_memory_ids),
            "extracted_memory_ids": list(self.extracted_memory_ids),
            "usage_trace": self.usage_trace.to_dict(),
            "applied_ops": dict(self.applied_ops),
        }
