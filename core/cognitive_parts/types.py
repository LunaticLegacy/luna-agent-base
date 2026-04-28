"""Primitive types for the cognitive graph.

Defines enums for node and edge semantics, plus dataclasses for nodes,
edges, and subgraph descriptors.  All IDs are UUID strings by default.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List


class CognitiveNodeType(str, Enum):
    """Taxonomy of cognitive node kinds."""

    FACT = "fact"
    GOAL = "goal"
    HYPOTHESIS = "hypothesis"
    GUESS = "guess"
    REASONING = "reasoning"
    EVIDENCE = "evidence"
    CLAIM = "claim"
    QUESTION = "question"
    ASSUMPTION = "assumption"
    DECISION = "decision"
    RISK = "risk"
    COUNTEREVIDENCE = "counterevidence"
    TOOL_RESULT = "tool_result"
    EXECUTION_TRACE = "execution_trace"


class CognitiveRelationType(str, Enum):
    """Taxonomy of directed relationships between cognitive nodes."""

    SUPPORTS = "supports"
    OPPOSES = "opposes"
    DERIVES_FROM = "derives_from"
    LEADS_TO = "leads_to"
    DEPENDS_ON = "depends_on"
    QUESTIONS = "questions"
    REFINES = "refines"
    VERIFIES = "verifies"
    DISPROVES = "disproves"
    SPECULATES = "speculates"
    RELATES = "relates"
    EVIDENCE_FOR = "evidence_for"


@dataclass
class CognitiveSubgraphDescriptor:
    """A schedulable view into the shared thought graph.

    Attributes:
        root_node_ids: Entry points for the subgraph.
        frontier_node_ids: Nodes that have neighbours outside the subgraph.
        purpose: Human-readable intent (e.g. ``"coder planning context"``).
        visibility: Access level (``"shared"``, ``"private"``, etc.).
        owner_agent: Agent that created or owns this view.
        expected_next_information: Hint about what the owner expects next.
        priority: Scheduling priority (higher = more urgent).
        subgraph_id: Auto-generated UUID.
        status: Lifecycle status (``"active"``, ``"archived"``, etc.).
        metadata: Free-form extension dict.
        created_at: ISO timestamp.
    """

    root_node_ids: List[str] = field(default_factory=list)
    frontier_node_ids: List[str] = field(default_factory=list)
    purpose: str = ""
    visibility: str = "shared"
    owner_agent: str = ""
    expected_next_information: str = ""
    priority: int = 0
    subgraph_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: str = "active"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict."""
        return {
            "subgraph_id": self.subgraph_id,
            "root_node_ids": list(self.root_node_ids),
            "frontier_node_ids": list(self.frontier_node_ids),
            "purpose": self.purpose,
            "visibility": self.visibility,
            "owner_agent": self.owner_agent,
            "expected_next_information": self.expected_next_information,
            "priority": self.priority,
            "status": self.status,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CognitiveSubgraphDescriptor":
        """Deserialise from a plain dict."""
        return cls(
            subgraph_id=str(data.get("subgraph_id", uuid.uuid4())),
            root_node_ids=[str(item) for item in data.get("root_node_ids", []) or []],
            frontier_node_ids=[str(item) for item in data.get("frontier_node_ids", []) or []],
            purpose=str(data.get("purpose", "")),
            visibility=str(data.get("visibility", "shared")),
            owner_agent=str(data.get("owner_agent", "")),
            expected_next_information=str(data.get("expected_next_information", "")),
            priority=int(data.get("priority", 0)),
            status=str(data.get("status", "active")),
            metadata=dict(data.get("metadata", {}) or {}),
            created_at=str(data.get("created_at", datetime.now(timezone.utc).isoformat())),
        )


@dataclass
class CognitiveNode:
    """A single thought / claim / evidence piece in the cognitive space.

    Attributes:
        content: Primary text payload.
        node_type: Semantic category.
        node_id: UUID string.
        summary: Shortened form for display.
        confidence: 0.0–1.0 credibility estimate.
        evidence: List of supporting evidence strings.
        tags: Arbitrary labels for indexing.
        source: Origin agent or system identifier.
        metadata: Free-form extension dict.
        created_at: ISO timestamp.
        version: Monotonically incremented on merge.
    """

    content: str
    node_type: CognitiveNodeType = CognitiveNodeType.CLAIM
    node_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    summary: str = ""
    confidence: float = 1.0
    evidence: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    source: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    version: int = 1

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict."""
        return {
            "node_id": self.node_id,
            "node_type": self.node_type.value,
            "content": self.content,
            "summary": self.summary,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "tags": list(self.tags),
            "source": self.source,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CognitiveNode":
        """Deserialise from a plain dict."""
        return cls(
            node_id=str(data.get("node_id", uuid.uuid4())),
            node_type=CognitiveNodeType(str(data.get("node_type", "claim"))),
            content=str(data.get("content", "")),
            summary=str(data.get("summary", "")),
            confidence=float(data.get("confidence", 1.0)),
            evidence=list(data.get("evidence", []) or []),
            tags=list(data.get("tags", []) or []),
            source=str(data.get("source", "")),
            metadata=dict(data.get("metadata", {}) or {}),
            created_at=str(data.get("created_at", datetime.now(timezone.utc).isoformat())),
            version=int(data.get("version", 1)),
        )


@dataclass
class CognitiveEdge:
    """A directed logical relationship between two cognitive nodes.

    Attributes:
        source_id: Origin node UUID.
        target_id: Destination node UUID.
        relation: Semantic relationship type.
        edge_id: UUID string.
        strength: 0.0–1.0 weight.
        description: Human-readable annotation.
        metadata: Free-form extension dict.
    """

    source_id: str
    target_id: str
    relation: CognitiveRelationType = CognitiveRelationType.RELATES
    edge_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    strength: float = 1.0
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict."""
        return {
            "edge_id": self.edge_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation": self.relation.value,
            "strength": self.strength,
            "description": self.description,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CognitiveEdge":
        """Deserialise from a plain dict."""
        return cls(
            source_id=str(data["source_id"]),
            target_id=str(data["target_id"]),
            relation=CognitiveRelationType(str(data.get("relation", "relates"))),
            edge_id=str(data.get("edge_id", uuid.uuid4())),
            strength=float(data.get("strength", 1.0)),
            description=str(data.get("description", "")),
            metadata=dict(data.get("metadata", {}) or {}),
        )
