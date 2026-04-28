"""Mutable semantic graph representing thoughts, evidence, and reasoning.

``CognitiveGraph`` is the primary data structure for the Angelus thought
layer.  Nodes are ``CognitiveNode`` instances (facts, claims, hypotheses,
etc.) and edges are ``CognitiveEdge`` instances describing logical
relationships.  The graph supports subgraph extraction, conflict
detection, unsupported-claim detection, and LLM-friendly export.
"""

from __future__ import annotations

import re
import uuid
from copy import deepcopy
from typing import Any, Dict, List, Optional, Set, Tuple

from .types import CognitiveEdge, CognitiveNode, CognitiveNodeType, CognitiveRelationType, CognitiveSubgraphDescriptor


class CognitiveGraph:
    """A mutable semantic graph representing thoughts, evidence, and reasoning.

    Attributes:
        graph_id: UUID string identifying this graph instance.
        nodes: Mapping from node_id to CognitiveNode.
        edges: List of CognitiveEdge instances.
    """

    def __init__(self, graph_id: str = "") -> None:
        self.graph_id = graph_id or str(uuid.uuid4())
        self.nodes: Dict[str, CognitiveNode] = {}
        self.edges: List[CognitiveEdge] = []

    def add_node(self, node: CognitiveNode) -> CognitiveNode:
        """Register *node* in the graph (overwrites any existing ID)."""
        self.nodes[node.node_id] = node
        return node

    def add_edge(self, edge: CognitiveEdge) -> CognitiveEdge:
        """Add *edge* to the graph, auto-creating placeholder nodes if missing.

        Auto-created placeholders use ``CognitiveNodeType.CLAIM`` so that
        the graph remains structurally valid even when an edge references
        a node that has not been explicitly added yet.
        """
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
        """Remove a node and all incident edges."""
        if node_id not in self.nodes:
            return False
        del self.nodes[node_id]
        self.edges = [e for e in self.edges if e.source_id != node_id and e.target_id != node_id]
        return True

    def remove_edge(self, edge_id: str) -> bool:
        """Remove the edge with the given *edge_id*."""
        original = len(self.edges)
        self.edges = [e for e in self.edges if e.edge_id != edge_id]
        return len(self.edges) < original

    def get_node(self, node_id: str) -> Optional[CognitiveNode]:
        """Return the node with *node_id*, or None."""
        return self.nodes.get(node_id)

    def outgoing_edges(self, node_id: str) -> List[CognitiveEdge]:
        """Return edges where *node_id* is the source."""
        return [e for e in self.edges if e.source_id == node_id]

    def incoming_edges(self, node_id: str) -> List[CognitiveEdge]:
        """Return edges where *node_id* is the target."""
        return [e for e in self.edges if e.target_id == node_id]

    def neighbors(self, node_id: str) -> List[str]:
        """Return all distinct node IDs adjacent to *node_id* (undirected)."""
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
        max_nodes: Optional[int] = None,
        allowed_relations: Optional[List[CognitiveRelationType]] = None,
    ) -> "CognitiveGraph":
        """Extract a hop-limited subgraph around *seed_ids*.

        Args:
            seed_ids: Entry points for the BFS expansion.
            max_hops: Maximum distance from any seed.
            max_nodes: Hard cap on node count; if exceeded, high-degree seed
                nodes are preferred over distant ones.
            allowed_relations: If provided, only traverse edges whose relation
                is in this list.

        Returns:
            A new CognitiveGraph containing the selected nodes and edges.
        """
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

        seeds = set(seed_ids)
        if max_nodes is not None and len(visited) > max_nodes:
            # Prefer seeds, then high-degree nodes, as a sensible pruning heuristic.
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
        max_nodes: Optional[int] = None,
        max_hops: int = 2,
    ) -> Tuple[CognitiveSubgraphDescriptor, "CognitiveGraph"]:
        """Build a subgraph plus its descriptor for scheduling or export.

        If *seed_ids* are given they are used directly; otherwise *query*
        is used to score and rank nodes; if both are absent, all nodes are
        considered.
        """
        roots = [sid for sid in (seed_ids or []) if sid in self.nodes]
        if not roots and query:
            scored = self._score_nodes_by_query(query)
            roots = scored[:max_nodes] if max_nodes is not None else scored
        if not roots:
            all_ids = list(self.nodes.keys())
            roots = all_ids[:max_nodes] if max_nodes is not None else all_ids

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
        """Detect pairs of nodes that are both supported and opposed.

        A conflict exists when two nodes have one SUPPORTS edge and one
        OPPOSES edge between them (order does not matter).

        Returns:
            List of (node_a, node_b, [edge1, edge2]) tuples.
        """
        conflicts: List[Tuple[CognitiveNode, CognitiveNode, List[CognitiveEdge]]] = []
        checked: Set[Tuple[str, str]] = set()

        for e1 in self.edges:
            if e1.relation not in (CognitiveRelationType.SUPPORTS, CognitiveRelationType.OPPOSES):
                continue
            for e2 in self.edges:
                if e2.relation not in (CognitiveRelationType.SUPPORTS, CognitiveRelationType.OPPOSES):
                    continue
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
        """Return nodes that lack supporting evidence edges.

        Only node types that are logically "assertive" (claim, fact,
        hypothesis, etc.) are considered.  A node is supported if any
        incoming edge has relation SUPPORTS, EVIDENCE_FOR, or VERIFIES.
        """
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

    def export_for_llm(
        self,
        query: Optional[str] = None,
        seed_ids: Optional[List[str]] = None,
        max_nodes: Optional[int] = None,
        max_hops: int = 2,
    ) -> str:
        """Produce a human-readable text representation for LLM prompting.

        If *seed_ids* or *query* are provided, a subgraph is extracted first;
        otherwise the full graph is exported (subject to *max_nodes*).
        """
        if seed_ids:
            graph = self.query_subgraph(seed_ids, max_hops=max_hops, max_nodes=max_nodes)
        elif query:
            scored = self._score_nodes_by_query(query)
            seed_ids = scored[:max_nodes] if max_nodes is not None else scored
            graph = self.query_subgraph(seed_ids, max_hops=max_hops, max_nodes=max_nodes)
        else:
            all_ids = list(self.nodes.keys())
            seed_ids = all_ids[:max_nodes] if max_nodes is not None else all_ids
            graph = self.query_subgraph(seed_ids, max_hops=max_hops, max_nodes=max_nodes)

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

    def export_subgraph_for_llm(self, descriptor: CognitiveSubgraphDescriptor, subgraph: "CognitiveGraph") -> str:
        """Export a descriptor plus its subgraph in a single formatted block."""
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
        """Serialise to a plain dict."""
        return {
            "graph_id": self.graph_id,
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CognitiveGraph":
        """Deserialise from a plain dict."""
        cg = cls(graph_id=str(data.get("graph_id", "")))
        for n in data.get("nodes", []) or []:
            cg.add_node(CognitiveNode.from_dict(n))
        for e in data.get("edges", []) or []:
            cg.add_edge(CognitiveEdge.from_dict(e))
        return cg

    def snapshot(self) -> Dict[str, Any]:
        """Alias for ``to_dict()``; used by the runtime for persistence."""
        return self.to_dict()

    def _score_nodes_by_query(self, query: str) -> List[str]:
        """Score every node by token overlap with *query* and return sorted IDs.

        Scoring weights:
            * +2 per matching token
            * +5 if the full query appears verbatim
            * +1 * confidence
        Only nodes with a positive score are returned.
        """
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
