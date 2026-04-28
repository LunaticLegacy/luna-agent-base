"""Cognitive graph sub-package — semantic thought graph primitives.

Provides the CognitiveGraph data structure, node/edge types, and helpers
for extraction, merging, and tag stripping.

Main exports:
    CognitiveGraph, CognitiveNode, CognitiveEdge,
    CognitiveNodeType, CognitiveRelationType,
    extract_cognitive_graph_from_text, merge_cognitive_graphs,
    strip_cognitive_graph_tags
"""

from .extract import extract_cognitive_graph_from_text, strip_cognitive_graph_tags
from .graph import CognitiveGraph
from .merge import merge_cognitive_graphs
from .types import (
    CognitiveEdge,
    CognitiveNode,
    CognitiveNodeType,
    CognitiveRelationType,
    CognitiveSubgraphDescriptor,
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
