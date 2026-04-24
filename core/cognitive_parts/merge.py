from __future__ import annotations

import re
from copy import deepcopy
from typing import List, Optional

from .graph import CognitiveGraph
from .types import CognitiveEdge, CognitiveNode


def merge_cognitive_graphs(
    target: CognitiveGraph,
    source: CognitiveGraph,
    *,
    similarity_threshold: float = 0.85,
) -> CognitiveGraph:
    node_id_map = {}

    for src_node in source.nodes.values():
        existing = _find_similar_node(target, src_node, threshold=similarity_threshold)
        if existing:
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
