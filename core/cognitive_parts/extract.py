"""Extract embedded cognitive graphs from LLM output text.

Provides regex-based parsers for the two recognised serialization forms:
    1. ``<cognitive_graph>...</cognitive_graph>`` XML tags.
    2. Markdown fenced JSON blocks containing a ``thinking_graph`` or
       ``cognitive_graph`` key.

Also exposes ``strip_cognitive_graph_tags`` to remove the markup so that
 downstream consumers only see the natural-language content.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from .graph import CognitiveGraph
from .types import CognitiveEdge, CognitiveNode


def extract_cognitive_graph_from_text(text: str, source_agent_id: str = "") -> Optional[CognitiveGraph]:
    """Parse a CognitiveGraph embedded in *text*.

    Supports both XML-style tags and fenced JSON blocks.  If *source_agent_id*
    is given, unattributed nodes are tagged with it.

    Args:
        text: Raw LLM response text.
        source_agent_id: Agent ID to stamp on orphan nodes.

    Returns:
        A populated CognitiveGraph, or None if no graph markup is found
        or parsing fails.
    """
    if not isinstance(text, str):
        return None

    match = re.search(r"<cognitive_graph>(.*?)</cognitive_graph>", text, re.DOTALL | re.IGNORECASE)
    if not match:
        # Fallback: look for a markdown-fenced JSON object that contains the graph key.
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
    """Remove ``<cognitive_graph>...</cognitive_graph>`` markup from *text*.

    Args:
        text: Raw LLM response text.

    Returns:
        The input text with tags removed and surrounding whitespace stripped.
    """
    if not isinstance(text, str):
        return text
    cleaned = re.sub(r"<cognitive_graph>.*?</cognitive_graph>", "", text, flags=re.DOTALL | re.IGNORECASE)
    return cleaned.strip()
