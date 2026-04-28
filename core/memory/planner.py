"""LLM-based planner for context selection, compression, and memory extraction.

The :class:`MemoryPlanner` asks the agent's LLM to decide:

1. Which episode nodes should be loaded into the current prompt.
2. Which node chains should be compressed (packed) into summaries.
3. Which new facts/formulas should be extracted as candidate memories.
4. What keywords should be used to query the existing memory store.

The planner is stateless and purely orchestrational; all durable state
lives in :class:`MemoryStore` and :class:`EpisodeGraph`.

Exports:
    - :class:`PlannerDecision`
    - :class:`MemoryPlanner`
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from .types import EpisodeNode, KeyMemory


@dataclass
class PlannerDecision:
    """Structured output of the memory planning LLM call.

    Attributes:
        reasoning: Human-readable explanation of the planning decision.
        selected_node_ids: Episode nodes to include in the prompt context.
        nodes_to_pack: Nodes whose ancestor chains should be compressed.
        memories_to_extract: Raw dicts describing new candidate memories.
        memory_queries: Keywords for searching the existing memory store.
    """

    reasoning: str = ""
    selected_node_ids: List[str] = field(default_factory=list)
    nodes_to_pack: List[str] = field(default_factory=list)
    memories_to_extract: List[Dict[str, Any]] = field(default_factory=list)
    memory_queries: List[str] = field(default_factory=list)


class MemoryPlanner:
    """LLM-based planner for context selection, compression, and memory extraction.

    Uses the agent's own LLM handler (or a provided one) to make decisions.

    Attributes:
        max_context_nodes: Upper bound on how many episode nodes may be selected.
        pack_keep_recent: How many recent turns to preserve when compressing a chain.
    """

    def __init__(
        self,
        max_context_nodes: int = 6,
        pack_keep_recent: int = 2,
    ) -> None:
        """Initialise the planner with its policy parameters.

        Args:
            max_context_nodes: Maximum number of episode nodes to load per round.
            pack_keep_recent: Number of recent turns to keep uncompressed during packing.
        """
        self.max_context_nodes = max_context_nodes
        self.pack_keep_recent = pack_keep_recent

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_nodes_for_decision(nodes: List[EpisodeNode]) -> str:
        """Render episode nodes as a compact text block for the planner prompt.

        Args:
            nodes: Episode nodes available for selection.

        Returns:
            Multi-line string summarising each node.
        """
        lines: List[str] = []
        for node in nodes:
            u = node.user_content.replace("\n", " ")[:80]
            a = node.assistant_content.replace("\n", " ")[:80]
            marker = ""
            if node.is_summary:
                marker = " [摘要]"
            if node.archived:
                marker = " [已归档]"
            lines.append(
                f"Node {node.node_id}{marker}: parents={sorted(node.parent_ids)} children={sorted(node.child_ids)}"
            )
            lines.append(f'  User: "{u}..."')
            lines.append(f'  Assistant: "{a}..."')
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _format_memories_for_decision(memories: List[KeyMemory]) -> str:
        """Render committed memories as a compact text block for the planner prompt.

        Args:
            memories: Committed memories already in the store.

        Returns:
            Multi-line string summarising each memory, or a placeholder if empty.
        """
        if not memories:
            return "（暂无已提取的关键记忆）"
        lines: List[str] = []
        for mem in memories:
            content = mem.content.replace("\n", " ")[:100]
            flag = ""
            if mem.pinned:
                flag = " [pinned]"
            lines.append(f"Memory {mem.memory_id}{flag} [tags={sorted(mem.tags)}]: {content}...")
        return "\n".join(lines)

    @staticmethod
    def _extract_json(raw: str) -> Dict[str, Any]:
        """Strip markdown fences and parse the inner JSON.

        Args:
            raw: Raw LLM output which may be wrapped in `` ```json ... ``` ``.

        Returns:
            Parsed JSON dictionary.

        Raises:
            json.JSONDecodeError: If the cleaned text is not valid JSON.
        """
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        return json.loads(raw)

    # ------------------------------------------------------------------
    # Core planning
    # ------------------------------------------------------------------

    async def plan(
        self,
        user_message: str,
        episode_nodes: List[EpisodeNode],
        memories: List[KeyMemory],
        llm_fetch_callback,
        parent_node_ids: Optional[Set[str]] = None,
    ) -> PlannerDecision:
        """Ask the LLM to decide context selection, packing, and memory extraction.

        *llm_fetch_callback* is an async callable::

            async def fetch(
                msg: str,
                system_prompt: Optional[str],
                temperature: float,
                max_tokens: int,
            ) -> str:
                return raw_text_response

        The prompt sent to the LLM is fully self-documenting and includes
        explicit rules for each field of the expected JSON response.

        Args:
            user_message: The incoming user message for this round.
            episode_nodes: All episode nodes in the graph.
            memories: All committed memories in the store.
            llm_fetch_callback: Async callable that forwards a prompt to the LLM.
            parent_node_ids: Optional set of parent nodes to use as fallback.

        Returns:
            A :class:`PlannerDecision` parsed from the LLM's JSON output.

        Raises:
            Exception: Only if both JSON parsing attempts fail; in that case a
                fallback decision is returned instead of propagating the error.
        """
        node_text = self._format_nodes_for_decision(episode_nodes)
        memory_text = self._format_memories_for_decision(memories)

        planning_prompt = f"""你是一位上下文与记忆管理专家。请基于以下信息，输出精确的 JSON 决策。

## 可用历史节点
{node_text}

## 已有关键记忆（不会被压缩，可直接引用）
{memory_text}

## 用户新问题
{user_message}

## 你的任务（严格按以下规则）

1. **selected_node_ids**: 选择需要加载到当前上下文的节点 id（最多 {self.max_context_nodes} 个）。
   - 优先选择与新问题直接相关的节点
   - 必须包含构成完整推理链的节点

2. **nodes_to_pack**: 指定要压缩其祖先链的节点 id。
   - **关键规则**: 系统会从你指定的节点**向前回溯**，保留最近 {self.pack_keep_recent} 轮，把更早的对话压缩成摘要。
   - **因此你应该填写当前对话链的最新节点**（如 selected_node_ids 中 id 最大的那个），而不是根节点。
   - 不要填写没有祖先的根节点，那样不会产生任何效果。
   - 如果历史很短（≤{self.pack_keep_recent + 1} 轮），请留空 []。

3. **memories_to_extract**: 从对话中提取应永久保存的关键信息。
   - **公式/定义/代码** 等精确信息：必须设置 `"pinned": true, "packable": false`。
   - **一般结论/事实**：可以设置 `"pinned": false, "packable": true`。
   - 每条记忆必须有 `"content"`（内容）和 `"tags"`（标签列表），可选 `"kind"`（fact/formula/constraint/preference/api_contract/project_goal/timeline_constraint/decision/warning）。

4. **memory_queries**: 列出用于检索已有记忆的关键词或标签。

## 输出格式示例（严格 JSON，不要 markdown 代码块，不要额外文字）

{{"reasoning": "用户询问测量行为，与Node 1的叠加态公式直接相关，因此选择Node 0和Node 1。历史较长，用Node 1触发压缩以节省token。公式是精确信息，需要pinned。","selected_node_ids": ["0", "1"],"nodes_to_pack": ["1"],"memories_to_extract": [{{"content": "叠加态公式: |ψ⟩ = α|0⟩ + β|1⟩, |α|²+|β|²=1", "tags": ["公式", "量子计算"], "kind": "formula", "pinned": true, "packable": false}}],"memory_queries": ["叠加态", "测量"]}}
"""

        for attempt in range(2):
            try:
                raw = await llm_fetch_callback(
                    msg=planning_prompt,
                    system_prompt="你只输出合法 JSON，不要添加任何 markdown 标记、解释文字或换行符包裹。",
                    temperature=0.1,
                    max_tokens=2048,
                )
                data = self._extract_json(raw)

                return PlannerDecision(
                    reasoning=data.get("reasoning", ""),
                    selected_node_ids=[str(x) for x in data.get("selected_node_ids", [])],
                    nodes_to_pack=[str(x) for x in data.get("nodes_to_pack", [])],
                    memories_to_extract=data.get("memories_to_extract", []),
                    memory_queries=[str(x) for x in data.get("memory_queries", [])],
                )
            except Exception as exc:
                if attempt == 0:
                    # Append a corrective hint for the second attempt
                    planning_prompt += (
                        "\n\n注意：你上一次的输出不是合法 JSON，"
                        "请确保本次输出是严格的 JSON 对象，不要有任何额外文字。"
                    )
                    continue
                # Fallback: use parent nodes or an empty decision so the round can continue
                fallback_nodes = list(parent_node_ids or set())
                return PlannerDecision(
                    reasoning=f"决策解析失败（{exc}），回退到默认最长链",
                    selected_node_ids=fallback_nodes,
                    nodes_to_pack=[],
                    memories_to_extract=[],
                    memory_queries=[],
                )
