"""DAG-based episode history graph.

``EpisodeGraph`` records every user-assistant turn as a node in a directed
acyclic graph.  Parent links preserve conversation branching.  The graph
supports compression (summarisation) of ancestor chains so that long
histories can be condensed into summary nodes without losing structural
information.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from .types import EpisodeNode


class CyclicGraphError(ValueError):
    """Raised when an operation would create a cycle in the DAG."""


class EpisodeGraph:
    """DAG-based episode history graph.

    Each node represents one user-assistant turn. Supports compression
    (summarization) of ancestor chains while preserving original nodes
    in an archived state.

    Attributes:
        nodes: Mapping from node ID to EpisodeNode.
        root_ids: Node IDs that have no parents (entry points).
    """

    def __init__(self) -> None:
        self.nodes: Dict[str, EpisodeNode] = {}
        self.root_ids: Set[str] = set()

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Serialise the entire graph to a plain dict."""
        return {
            "nodes": {nid: node.to_dict() for nid, node in self.nodes.items()},
            "root_ids": sorted(self.root_ids),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EpisodeGraph":
        """Deserialise a plain dict back into an EpisodeGraph."""
        graph = cls()
        for nid, node_data in data.get("nodes", {}).items():
            graph.nodes[nid] = EpisodeNode.from_dict(node_data)
        graph.root_ids = set(data.get("root_ids", []))
        return graph

    # ------------------------------------------------------------------
    # Core graph operations
    # ------------------------------------------------------------------

    def add_node(
        self,
        user_content: str,
        assistant_content: str,
        parent_ids: Optional[Set[str]] = None,
        node_id: Optional[str] = None,
    ) -> str:
        """Add a new episode node to the graph.

        Args:
            user_content: The user's message text.
            assistant_content: The assistant's response text.
            parent_ids: Set of parent node IDs.  Empty set → root node.
            node_id: Optional explicit ID; auto-generated if omitted.

        Returns:
            The new node id.

        Raises:
            KeyError: If any parent_id does not exist.
        """
        nid = node_id or uuid.uuid4().hex
        parent_ids = set(parent_ids) if parent_ids else set()

        for pid in parent_ids:
            if pid not in self.nodes:
                raise KeyError(f"parent_id {pid} does not exist")

        node = EpisodeNode(
            node_id=nid,
            user_content=user_content,
            assistant_content=assistant_content,
            parent_ids=parent_ids,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.nodes[nid] = node

        if not parent_ids:
            self.root_ids.add(nid)
        else:
            for pid in parent_ids:
                self.nodes[pid].child_ids.add(nid)
            self.root_ids.discard(nid)

        return nid

    def _has_path(self, from_id: str, to_id: str, visited: Optional[Set[str]] = None) -> bool:
        """Depth-first search for a path from *from_id* to *to_id*."""
        if from_id == to_id:
            return True
        if visited is None:
            visited = set()
        visited.add(from_id)
        for child_id in self.nodes[from_id].child_ids:
            if child_id not in visited and self._has_path(child_id, to_id, visited):
                return True
        return False

    def add_edge(self, child_id: str, parent_id: str) -> None:
        """Add a parent relationship to an existing node.

        Args:
            child_id: The node that gains a new parent.
            parent_id: The new parent.

        Raises:
            KeyError: If either node does not exist.
            CyclicGraphError: If the edge would create a cycle.
        """
        if child_id not in self.nodes:
            raise KeyError(f"child_id {child_id} does not exist")
        if parent_id not in self.nodes:
            raise KeyError(f"parent_id {parent_id} does not exist")
        if parent_id in self.nodes[child_id].parent_ids:
            return
        if self._has_path(child_id, parent_id):
            raise CyclicGraphError(
                f"Adding edge {parent_id} -> {child_id} would create a cycle"
            )
        self.nodes[child_id].parent_ids.add(parent_id)
        self.nodes[parent_id].child_ids.add(child_id)
        self.root_ids.discard(child_id)

    def get_ancestor_chain(
        self,
        node_id: str,
        max_nodes: int = 8,
        strategy: str = "longest",
    ) -> List[str]:
        """Return one ancestor path from a root to the target node.

        Args:
            node_id: The target node.
            max_nodes: Maximum length of the returned chain.
            strategy: ``"longest"``, ``"shortest"``, or ``"first"``.

        Returns:
            Ordered list of node IDs from root to target (inclusive),
            truncated to *max_nodes* if necessary.

        Raises:
            KeyError: If *node_id* does not exist.
            ValueError: If *strategy* is unknown.
        """
        if node_id not in self.nodes:
            raise KeyError(f"node_id {node_id} does not exist")
        if strategy not in {"longest", "shortest", "first"}:
            raise ValueError(f"Unknown strategy: {strategy}")

        def dfs(nid: str, path_visited: Set[str]) -> List[str]:
            if nid in path_visited:
                return []
            parents = self.nodes[nid].parent_ids
            if not parents:
                return [nid]
            new_visited = path_visited | {nid}
            candidates: List[List[str]] = []
            for pid in parents:
                sub_path = dfs(pid, new_visited)
                if sub_path:
                    candidates.append(sub_path + [nid])
            if not candidates:
                return [nid]
            if strategy == "longest":
                return max(candidates, key=len)
            elif strategy == "shortest":
                return min(candidates, key=len)
            return candidates[0]

        chain = dfs(node_id, set())
        if len(chain) > max_nodes:
            chain = chain[-max_nodes:]
        return chain

    def get_all_ancestors(self, node_id: str) -> Set[str]:
        """Return all ancestor node ids via BFS.

        Raises:
            KeyError: If *node_id* does not exist.
        """
        if node_id not in self.nodes:
            raise KeyError(f"node_id {node_id} does not exist")
        ancestors: Set[str] = set()
        queue = list(self.nodes[node_id].parent_ids)
        while queue:
            pid = queue.pop(0)
            if pid not in ancestors:
                ancestors.add(pid)
                queue.extend(self.nodes[pid].parent_ids)
        return ancestors

    def get_active_nodes(self) -> Dict[str, EpisodeNode]:
        """Return nodes that are neither archived nor explicitly inactive."""
        return {nid: node for nid, node in self.nodes.items() if node.active and not node.archived}

    def get_archived_nodes(self) -> Dict[str, EpisodeNode]:
        """Return nodes that have been archived (e.g. after compression)."""
        return {nid: node for nid, node in self.nodes.items() if node.archived}

    # ------------------------------------------------------------------
    # Compression
    # ------------------------------------------------------------------

    async def compress_ancestors(
        self,
        node_id: str,
        llm_summarize_callback,
        max_nodes: int = 8,
        keep_recent: int = 2,
        summary_system_prompt: Optional[str] = None,
    ) -> Optional[str]:
        """Compress older ancestors of *node_id* into a summary node.

        *llm_summarize_callback* is an async callable accepting
        (prompt: str, system_prompt: Optional[str]) -> str
        that returns the summary text.

        Args:
            node_id: The node whose ancestor chain should be compressed.
            llm_summarize_callback: Async function producing a summary string.
            max_nodes: Upper bound on ancestor chain length to consider.
            keep_recent: How many recent ancestors to preserve verbatim.
            summary_system_prompt: Optional system prompt for the summariser.

        Returns:
            The new summary node id, or None if no compression happened.

        Raises:
            KeyError: If *node_id* does not exist.
        """
        if node_id not in self.nodes:
            raise KeyError(f"node_id {node_id} does not exist")

        chain = self.get_ancestor_chain(node_id, max_nodes=max_nodes, strategy="longest")
        if len(chain) <= keep_recent + 1:
            return None

        old_ids = chain[:-keep_recent] if keep_recent > 0 else chain[:]
        recent_ids = chain[-keep_recent:] if keep_recent > 0 else []

        if not old_ids:
            return None

        lines: List[str] = []
        for nid in old_ids:
            node = self.nodes[nid]
            lines.append(f"User: {node.user_content}")
            lines.append(f"Assistant: {node.assistant_content}")
            lines.append("")

        prompt = (
            "请对以下多轮对话进行高度浓缩的摘要，保留关键事实、结论和上下文信息。\n"
            "摘要需要足够详细，使得只读摘要就能继续后续对话，"
            "不要遗漏重要的用户要求或模型回答。\n\n"
            + "\n".join(lines)
        )

        summary_text = await llm_summarize_callback(
            prompt,
            system_prompt=summary_system_prompt
            or "你是一个对话摘要专家。请生成简洁但信息完整的摘要。",
        )

        first_old = self.nodes[old_ids[0]]
        summary_nid = uuid.uuid4().hex

        summary_node = EpisodeNode(
            node_id=summary_nid,
            user_content="[历史对话摘要]",
            assistant_content=summary_text,
            parent_ids=set(first_old.parent_ids),
            is_summary=True,
            summarizes=set(old_ids),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.nodes[summary_nid] = summary_node

        if not summary_node.parent_ids:
            self.root_ids.add(summary_nid)
        else:
            for pid in summary_node.parent_ids:
                self.nodes[pid].child_ids.add(summary_nid)

        # Rewire: first recent node's parent relation
        if recent_ids:
            first_recent_id = recent_ids[0]
            last_old_id = old_ids[-1]
            if last_old_id in self.nodes[first_recent_id].parent_ids:
                self.nodes[first_recent_id].parent_ids.discard(last_old_id)
                self.nodes[first_recent_id].parent_ids.add(summary_nid)
                self.nodes[last_old_id].child_ids.discard(first_recent_id)
                self.nodes[summary_nid].child_ids.add(first_recent_id)

        # Archive old nodes
        for old_id in old_ids:
            self.nodes[old_id].active = False
            self.nodes[old_id].archived = True
            self.nodes[old_id].summarized_by.add(summary_nid)

        return summary_nid
