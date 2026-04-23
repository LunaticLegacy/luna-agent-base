"""Cognitive graph model for Angelus — thinking as a graph.

Inspired by Thinking Graph (https://github.com/LunaticLegacy/thinking_graph),
this module provides a semantic graph layer where nodes represent thoughts
(evidence, hypotheses, claims, reasoning steps) and edges represent logical
relationships (supports, opposes, derives_from, etc.).

Every Agent owns a private CognitiveGraph.  During execution the swarm
maintains a shared CognitiveGraph that aggregates agent contributions.
"""

from __future__ import annotations

import json
import re
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


class CognitiveNodeType(str, Enum):
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
    """A schedulable view into the shared thought graph."""

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
    """A single thought / claim / evidence piece in the cognitive space."""

    content: str
    node_type: CognitiveNodeType = CognitiveNodeType.CLAIM
    node_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    summary: str = ""
    confidence: float = 1.0
    evidence: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    source: str = ""  # agent_id or tool_name that produced this node
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    version: int = 1

    def to_dict(self) -> Dict[str, Any]:
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
    """A directed logical relationship between two cognitive nodes."""

    source_id: str
    target_id: str
    relation: CognitiveRelationType = CognitiveRelationType.RELATES
    edge_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    strength: float = 1.0
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
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
        return cls(
            source_id=str(data["source_id"]),
            target_id=str(data["target_id"]),
            relation=CognitiveRelationType(str(data.get("relation", "relates"))),
            edge_id=str(data.get("edge_id", uuid.uuid4())),
            strength=float(data.get("strength", 1.0)),
            description=str(data.get("description", "")),
            metadata=dict(data.get("metadata", {}) or {}),
        )


class CognitiveGraph:
    """A mutable semantic graph representing thoughts, evidence, and reasoning."""

    def __init__(self, graph_id: str = "") -> None:
        self.graph_id = graph_id or str(uuid.uuid4())
        self.nodes: Dict[str, CognitiveNode] = {}
        self.edges: List[CognitiveEdge] = []

    # ------------------------------------------------------------------ #
    # Mutations
    # ------------------------------------------------------------------ #

    def add_node(self, node: CognitiveNode) -> CognitiveNode:
        self.nodes[node.node_id] = node
        return node

    def add_edge(self, edge: CognitiveEdge) -> CognitiveEdge:
        # Validate endpoints exist (soft validation: create stubs if missing)
        if edge.source_id not in self.nodes:
            self.add_node(
                CognitiveNode(
                    node_id=edge.source_id,
                    content="[auto]",
                    node_type=CognitiveNodeType.CLAIM,
                )
            )
        if edge.target_id not in self.nodes:
            self.add_node(
                CognitiveNode(
                    node_id=edge.target_id,
                    content="[auto]",
                    node_type=CognitiveNodeType.CLAIM,
                )
            )
        self.edges.append(edge)
        return edge

    def remove_node(self, node_id: str) -> bool:
        if node_id not in self.nodes:
            return False
        del self.nodes[node_id]
        self.edges = [e for e in self.edges if e.source_id != node_id and e.target_id != node_id]
        return True

    def remove_edge(self, edge_id: str) -> bool:
        original = len(self.edges)
        self.edges = [e for e in self.edges if e.edge_id != edge_id]
        return len(self.edges) < original

    # ------------------------------------------------------------------ #
    # Queries
    # ------------------------------------------------------------------ #

    def get_node(self, node_id: str) -> Optional[CognitiveNode]:
        return self.nodes.get(node_id)

    def outgoing_edges(self, node_id: str) -> List[CognitiveEdge]:
        return [e for e in self.edges if e.source_id == node_id]

    def incoming_edges(self, node_id: str) -> List[CognitiveEdge]:
        return [e for e in self.edges if e.target_id == node_id]

    def neighbors(self, node_id: str) -> List[str]:
        nbrs: Set[str] = set()
        for e in self.edges:
            if e.source_id == node_id:
                nbrs.add(e.target_id)
            if e.target_id == node_id:
                nbrs.add(e.source_id)
        return list(nbrs)

    def query_subgraph(
        self,
        seed_ids: List[str],
        max_hops: int = 2,
        max_nodes: int = 50,
        allowed_relations: Optional[List[CognitiveRelationType]] = None,
    ) -> "CognitiveGraph":
        """Extract a neighbourhood subgraph around seed nodes via BFS."""
        if not seed_ids:
            return CognitiveGraph(graph_id=f"{self.graph_id}_sub")

        allowed = set(allowed_relations) if allowed_relations else None
        visited: Set[str] = set(seed_ids)
        current_level: Set[str] = set(seed_ids)

        for _ in range(max_hops):
            next_level: Set[str] = set()
            for node_id in current_level:
                for e in self.edges:
                    if allowed and e.relation not in allowed:
                        continue
                    if e.source_id == node_id and e.target_id not in visited:
                        next_level.add(e.target_id)
                    if e.target_id == node_id and e.source_id not in visited:
                        next_level.add(e.source_id)
            visited.update(next_level)
            current_level = next_level
            if not current_level:
                break

        # Trim to max_nodes — seeds always kept
        seeds = set(seed_ids)
        if len(visited) > max_nodes:
            # Priority: seeds > nodes with higher total edge count
            node_degrees = {nid: len(self.outgoing_edges(nid)) + len(self.incoming_edges(nid)) for nid in visited}
            sorted_nodes = sorted(visited, key=lambda nid: (0 if nid in seeds else 1, -node_degrees.get(nid, 0), nid))
            visited = set(sorted_nodes[:max_nodes])

        sub = CognitiveGraph(graph_id=f"{self.graph_id}_sub")
        for nid in visited:
            if nid in self.nodes:
                sub.add_node(deepcopy(self.nodes[nid]))
        for e in self.edges:
            if e.source_id in visited and e.target_id in visited:
                if allowed is None or e.relation in allowed:
                    sub.add_edge(deepcopy(e))
        return sub

    def describe_subgraph(
        self,
        *,
        owner_agent: str = "",
        query: Optional[str] = None,
        seed_ids: Optional[List[str]] = None,
        purpose: str = "",
        visibility: str = "shared",
        expected_next_information: str = "",
        priority: int = 0,
        max_nodes: int = 20,
        max_hops: int = 2,
    ) -> Tuple[CognitiveSubgraphDescriptor, "CognitiveGraph"]:
        """Create a schedulable descriptor and matching graph slice."""
        roots = [sid for sid in (seed_ids or []) if sid in self.nodes]
        if not roots and query:
            roots = self._score_nodes_by_query(query)[:max_nodes]
        if not roots:
            roots = list(self.nodes.keys())[:max_nodes]

        subgraph = self.query_subgraph(roots, max_hops=max_hops, max_nodes=max_nodes)
        frontier = [
            node_id
            for node_id in subgraph.nodes
            if any(neighbor_id not in subgraph.nodes for neighbor_id in self.neighbors(node_id))
        ]
        descriptor = CognitiveSubgraphDescriptor(
            root_node_ids=list(roots),
            frontier_node_ids=frontier,
            purpose=purpose or (query or "General thought graph context"),
            visibility=visibility,
            owner_agent=owner_agent,
            expected_next_information=expected_next_information,
            priority=priority,
        )
        return descriptor, subgraph

    def find_conflicts(self) -> List[Tuple[CognitiveNode, CognitiveNode, List[CognitiveEdge]]]:
        """Detect pairs of nodes that both support and oppose each other."""
        conflicts: List[Tuple[CognitiveNode, CognitiveNode, List[CognitiveEdge]]] = []
        checked: Set[Tuple[str, str]] = set()

        for e1 in self.edges:
            if e1.relation not in (CognitiveRelationType.SUPPORTS, CognitiveRelationType.OPPOSES):
                continue
            for e2 in self.edges:
                if e2.relation not in (CognitiveRelationType.SUPPORTS, CognitiveRelationType.OPPOSES):
                    continue
                # Pair (A, B) where A supports B and A opposes B (or vice versa)
                pair = tuple(sorted([e1.source_id, e1.target_id, e2.source_id, e2.target_id]))
                if len(set(pair)) != 2:
                    continue
                key = (pair[0], pair[1])
                if key in checked:
                    continue
                if {e1.relation, e2.relation} == {CognitiveRelationType.SUPPORTS, CognitiveRelationType.OPPOSES}:
                    a_id, b_id = pair[0], pair[1]
                    a = self.nodes.get(a_id)
                    b = self.nodes.get(b_id)
                    if a and b:
                        conflicts.append((a, b, [e1, e2]))
                        checked.add(key)
        return conflicts

    def find_unsupported_claims(self) -> List[CognitiveNode]:
        """Return claim-like nodes with no incoming support or verification edges."""
        unsupported: List[CognitiveNode] = []
        for node in self.nodes.values():
            if node.node_type not in (
                CognitiveNodeType.CLAIM,
                CognitiveNodeType.HYPOTHESIS,
                CognitiveNodeType.GUESS,
                CognitiveNodeType.FACT,
                CognitiveNodeType.DECISION,
            ):
                continue
            has_support = any(
                e.target_id == node.node_id
                and e.relation in (
                    CognitiveRelationType.SUPPORTS,
                    CognitiveRelationType.EVIDENCE_FOR,
                    CognitiveRelationType.VERIFIES,
                )
                for e in self.edges
            )
            if not has_support:
                unsupported.append(node)
        return unsupported

    # ------------------------------------------------------------------ #
    # Serialization
    # ------------------------------------------------------------------ #

    def export_for_llm(
        self,
        query: Optional[str] = None,
        seed_ids: Optional[List[str]] = None,
        max_nodes: int = 20,
        max_hops: int = 2,
    ) -> str:
        """Serialize a relevant subgraph as plain text for LLM consumption."""
        if seed_ids:
            graph = self.query_subgraph(seed_ids, max_hops=max_hops, max_nodes=max_nodes)
        elif query:
            seed_ids = self._score_nodes_by_query(query)[:max_nodes]
            graph = self.query_subgraph(seed_ids, max_hops=max_hops, max_nodes=max_nodes)
        else:
            # No query / no seeds → return the whole graph (clamped)
            all_ids = list(self.nodes.keys())[:max_nodes]
            graph = self.query_subgraph(all_ids, max_hops=max_hops, max_nodes=max_nodes)

        lines: List[str] = [f"Cognitive Graph (id={graph.graph_id}, nodes={len(graph.nodes)}, edges={len(graph.edges)}):"]
        for node in graph.nodes.values():
            lines.append(
                f"- [{node.node_type.value}] {node.content[:120]}"
                f"  (confidence={node.confidence:.2f}, id={node.node_id}, source={node.source})"
            )
        if graph.edges:
            lines.append("Relations:")
            for edge in graph.edges:
                lines.append(
                    f"  {edge.source_id} --[{edge.relation.value}]--> {edge.target_id}"
                    f"  (strength={edge.strength:.2f})"
                )
        return "\n".join(lines)

    def export_subgraph_for_llm(
        self,
        descriptor: CognitiveSubgraphDescriptor,
        subgraph: "CognitiveGraph",
    ) -> str:
        """Serialize a schedulable subgraph with its scheduling metadata."""
        lines: List[str] = [
            "Schedulable Thought Subgraph:",
            f"- id: {descriptor.subgraph_id}",
            f"- owner_agent: {descriptor.owner_agent or 'unassigned'}",
            f"- purpose: {descriptor.purpose or 'unspecified'}",
            f"- visibility: {descriptor.visibility}",
            f"- expected_next_information: {descriptor.expected_next_information or 'unspecified'}",
            f"- root_nodes: {', '.join(descriptor.root_node_ids) or 'none'}",
            f"- frontier_nodes: {', '.join(descriptor.frontier_node_ids) or 'none'}",
            "",
            subgraph.export_for_llm(max_nodes=len(subgraph.nodes) or 1),
        ]
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CognitiveGraph":
        cg = cls(graph_id=str(data.get("graph_id", "")))
        for n in data.get("nodes", []) or []:
            cg.add_node(CognitiveNode.from_dict(n))
        for e in data.get("edges", []) or []:
            cg.add_edge(CognitiveEdge.from_dict(e))
        return cg

    def snapshot(self) -> Dict[str, Any]:
        return self.to_dict()

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _score_nodes_by_query(self, query: str) -> List[str]:
        """Simple lexical scoring for subgraph extraction."""
        tokens = re.findall(r"[a-z0-9\u4e00-\u9fff]+", query.lower())
        scores: Dict[str, float] = {}
        for nid, node in self.nodes.items():
            score = 0.0
            text = f"{node.content} {node.summary} {' '.join(node.tags)}".lower()
            for token in tokens:
                if token in text:
                    score += 2.0
            if query.lower() in text:
                score += 5.0
            score += node.confidence * 1.0
            scores[nid] = score
        sorted_ids = sorted(scores.keys(), key=lambda nid: (-scores[nid], nid))
        return [nid for nid in sorted_ids if scores[nid] > 0]


# ---------------------------------------------------------------------- #
# Merge helpers
# ---------------------------------------------------------------------- #


def merge_cognitive_graphs(
    target: CognitiveGraph,
    source: CognitiveGraph,
    *,
    similarity_threshold: float = 0.85,
) -> CognitiveGraph:
    """Merge *source* graph into *target*, deduplicating by content similarity.

    If a source node has content very similar to an existing target node,
    the existing node is updated (confidence averaged, evidence unioned).
    Otherwise the source node is copied into target as-is.
    """
    node_id_map: Dict[str, str] = {}  # source_id -> target_id

    for src_node in source.nodes.values():
        existing = _find_similar_node(target, src_node, threshold=similarity_threshold)
        if existing:
            # Merge into existing
            existing.confidence = (existing.confidence + src_node.confidence) / 2.0
            existing.evidence = list(set(existing.evidence + src_node.evidence))
            existing.tags = list(set(existing.tags + src_node.tags))
            if src_node.source and src_node.source not in existing.source:
                existing.source += f",{src_node.source}"
            existing.version += 1
            node_id_map[src_node.node_id] = existing.node_id
        else:
            new_node = deepcopy(src_node)
            target.add_node(new_node)
            node_id_map[src_node.node_id] = new_node.node_id

    for src_edge in source.edges:
        mapped_source = node_id_map.get(src_edge.source_id, src_edge.source_id)
        mapped_target = node_id_map.get(src_edge.target_id, src_edge.target_id)
        # Avoid duplicate edges with same relation
        duplicate = any(
            e.source_id == mapped_source
            and e.target_id == mapped_target
            and e.relation == src_edge.relation
            for e in target.edges
        )
        if not duplicate:
            new_edge = deepcopy(src_edge)
            new_edge.source_id = mapped_source
            new_edge.target_id = mapped_target
            target.add_edge(new_edge)

    return target


def _find_similar_node(
    graph: CognitiveGraph,
    candidate: CognitiveNode,
    threshold: float = 0.85,
) -> Optional[CognitiveNode]:
    """Naïve content-similarity check using simple token overlap."""
    cand_tokens = set(_tokenize(candidate.content))
    if not cand_tokens:
        return None
    best: Optional[CognitiveNode] = None
    best_score = 0.0
    for node in graph.nodes.values():
        node_tokens = set(_tokenize(node.content))
        if not node_tokens:
            continue
        inter = len(cand_tokens & node_tokens)
        union = len(cand_tokens | node_tokens)
        if union == 0:
            continue
        score = inter / union
        if score >= threshold and score > best_score:
            best_score = score
            best = node
    return best


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9\u4e00-\u9fff]+", text.lower())


# ---------------------------------------------------------------------- #
# Extraction helpers — parse LLM output for embedded cognitive graph
# ---------------------------------------------------------------------- #


def extract_cognitive_graph_from_text(text: str, source_agent_id: str = "") -> Optional[CognitiveGraph]:
    """Attempt to extract a ``<cognitive_graph>`` JSON block from LLM text output.

    Returns *None* if no block is found or parsing fails.
    """
    if not isinstance(text, str):
        return None

    # Look for <cognitive_graph>...</cognitive_graph> tags
    match = re.search(r"<cognitive_graph>(.*?)</cognitive_graph>", text, re.DOTALL | re.IGNORECASE)
    if not match:
        # Fallback: look for a ```json block containing "thinking_graph" or "cognitive_graph"
        fence_match = re.search(r"```(?:json)?\s*(\{.*?\"(?:thinking_graph|cognitive_graph)\".*?\})\s*```", text, re.DOTALL)
        if fence_match:
            raw = fence_match.group(1)
        else:
            return None
    else:
        raw = match.group(1)

    try:
        data = json.loads(raw.strip())
    except json.JSONDecodeError:
        return None

    # Support both keys for compatibility
    graph_data = data.get("cognitive_graph") or data.get("thinking_graph")
    if not isinstance(graph_data, dict):
        return None

    cg = CognitiveGraph()
    nodes_raw = graph_data.get("nodes") or []
    edges_raw = graph_data.get("edges") or []

    for n in nodes_raw:
        node = CognitiveNode.from_dict(n)
        if source_agent_id and not node.source:
            node.source = source_agent_id
        cg.add_node(node)

    for e in edges_raw:
        edge = CognitiveEdge.from_dict(e)
        cg.add_edge(edge)

    return cg


def strip_cognitive_graph_tags(text: str) -> str:
    """Remove ``<cognitive_graph>...</cognitive_graph>`` blocks from text."""
    if not isinstance(text, str):
        return text
    cleaned = re.sub(r"<cognitive_graph>.*?</cognitive_graph>", "", text, flags=re.DOTALL | re.IGNORECASE)
    return cleaned.strip()
