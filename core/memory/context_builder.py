"""Build prompt messages from episode nodes and memories.

``ContextBuilder`` assembles a ``MemoryContextPlan`` by partitioning
eligible memories (pinned, timeline, semantic) and selected episode nodes
(packed summaries vs. recent turns) into ordered system messages.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .types import EpisodeNode, KeyMemory, MemoryContextPlan
from .lifecycle import can_inject_memory


class ContextBuilder:
    """Builds prompt messages from episode nodes and memories, partitioned by type.

    Attributes:
        max_context_nodes: Maximum number of episode nodes to include.
    """

    def __init__(self, max_context_nodes: int = 6) -> None:
        self.max_context_nodes = max_context_nodes

    def build(
        self,
        *,
        episode_graph_nodes: Dict[str, EpisodeNode],
        selected_node_ids: List[str],
        memories: List[KeyMemory],
        current_turn_id: str,
        memory_queries: Optional[List[str]] = None,
        user_message: str = "",
    ) -> MemoryContextPlan:
        """Construct a MemoryContextPlan with partitioned prompt messages.

        Args:
            episode_graph_nodes: Full node pool from the episode graph.
            selected_node_ids: Node IDs chosen by the planner/context policy.
            memories: All committed memories from the memory store.
            current_turn_id: Identifier for the current turn (used to filter
                memories that are not yet eligible for injection).
            memory_queries: Raw query strings that produced the selection.
            user_message: The current turn's user message (reserved for future
                expansion; not yet injected directly).

        Returns:
            A MemoryContextPlan ready for the agent's system context.
        """
        memory_queries = memory_queries or []

        # Collect all nodes from selected ancestors
        all_nids: set[str] = set()
        for nid in selected_node_ids:
            if nid in episode_graph_nodes:
                # For simplicity, include the node itself; the runtime/planner
                # is expected to have already resolved ancestor chains.
                all_nids.add(nid)

        # Sort by a topological/creation heuristic: use node_id as proxy if needed,
        # but ideally we preserve ancestor chain order. Here we rely on the caller
        # to pass selected_node_ids in the desired order, or we sort active first.
        sorted_nids = sorted(all_nids, key=lambda x: episode_graph_nodes[x].created_at or x)

        # ---- Memory filtering ----
        eligible_memories = [m for m in memories if can_inject_memory(m, current_turn_id)]

        pinned = [m for m in eligible_memories if m.pinned]
        timeline = [m for m in eligible_memories if m.kind == "timeline_constraint" and not m.pinned]
        semantic = [m for m in eligible_memories if m.kind not in ("formula", "constraint", "api_contract", "timeline_constraint") and not m.pinned]
        # Also include pinned formula/constraint/api_contract in pinned section
        # (they are already in pinned because pinned=True)

        # Remove duplicates across categories
        timeline_ids = {m.memory_id for m in timeline}
        semantic_ids = {m.memory_id for m in semantic}
        semantic = [m for m in semantic if m.memory_id not in timeline_ids]

        selected_memory_ids = [m.memory_id for m in pinned + timeline + semantic]

        # ---- Build prompt messages ----
        prompt_messages: List[Dict[str, str]] = []

        # 1. Pinned Memory
        if pinned:
            lines = ["【Pinned Memory / 精确保留记忆】"]
            for i, m in enumerate(pinned):
                lines.append(f"- [M{m.memory_id}] {m.content}")
            prompt_messages.append({"role": "system", "content": "\n".join(lines)})

        # 2. Timeline Constraints
        if timeline:
            lines = ["【Timeline Constraints / 时间线约束】"]
            for i, m in enumerate(timeline):
                lines.append(f"- [M{m.memory_id}] {m.content}")
            prompt_messages.append({"role": "system", "content": "\n".join(lines)})

        # 3. Semantic Memory
        if semantic:
            lines = ["【Semantic Memory / 语义记忆】"]
            for i, m in enumerate(semantic):
                lines.append(f"- [M{m.memory_id}] {m.content}")
            prompt_messages.append({"role": "system", "content": "\n".join(lines)})

        # 4. Packed History (summary nodes among selected)
        summary_nodes = [episode_graph_nodes[nid] for nid in sorted_nids if episode_graph_nodes[nid].is_summary]
        if summary_nodes:
            lines = ["【Packed History / 压缩历史】"]
            for node in summary_nodes:
                lines.append(f"- [S{node.node_id}] {node.assistant_content}")
            prompt_messages.append({"role": "system", "content": "\n".join(lines)})

        # 5. Recent Turns (non-summary nodes)
        recent_nodes = [episode_graph_nodes[nid] for nid in sorted_nids if not episode_graph_nodes[nid].is_summary]
        if recent_nodes:
            lines = ["【Recent Turns / 最近对话】"]
            for node in recent_nodes:
                lines.append(f"User: {node.user_content}")
                lines.append(f"Assistant: {node.assistant_content}")
                lines.append("")
            prompt_messages.append({"role": "system", "content": "\n".join(lines)})

        token_estimate = sum(len(m["content"]) for m in prompt_messages) // 4

        return MemoryContextPlan(
            selected_node_ids=list(selected_node_ids),
            selected_memory_ids=selected_memory_ids,
            pack_triggers=[],
            compressed_node_ids=[],
            summary_node_ids=[n.node_id for n in summary_nodes],
            memory_queries=list(memory_queries),
            prompt_messages=prompt_messages,
            token_estimate=token_estimate,
            reasoning="Built from selected nodes and eligible committed memories.",
        )
