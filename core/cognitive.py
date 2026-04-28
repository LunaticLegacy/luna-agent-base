"""Cognitive module — convenience re-exports for the thought-graph subsystem.

All real implementations live in ``core.cognitive_parts``.  This module
exists so that downstream code can ``from core.cognitive import ...``
without knowing the internal package layout.
"""

from __future__ import annotations

from .cognitive_parts import (
    CognitiveEdge,
    CognitiveGraph,
    CognitiveNode,
    CognitiveNodeType,
    CognitiveRelationType,
    CognitiveSubgraphDescriptor,
    extract_cognitive_graph_from_text,
    merge_cognitive_graphs,
    strip_cognitive_graph_tags,
)

__all__ = [
    "CognitiveEdge",
    "CognitiveGraph",
    "CognitiveNode",
    "CognitiveNodeType",
    "CognitiveRelationType",
    "CognitiveSubgraphDescriptor",
    "extract_cognitive_graph_from_text",
    "merge_cognitive_graphs",
    "strip_cognitive_graph_tags",
]
