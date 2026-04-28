from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from .types import EpisodeNode, KeyMemory, MemoryContextPlan, MemoryUpdateResult, MemoryUsageTrace
from .episode_graph import EpisodeGraph
from .memory_store import MemoryStore
from .lifecycle import MemoryLifecycle, can_inject_memory
from .context_builder import ContextBuilder
from .planner import MemoryPlanner
from .usage_trace import UsageTraceTracker

logger = logging.getLogger(__name__)


@dataclass
class MemoryRuntimeConfig:
    enabled: bool = True
    max_context_nodes: int = 6
    pack_keep_recent: int = 2
    enable_usage_trace: bool = True
    enable_candidate_memory: bool = True
    summary_system_prompt: Optional[str] = None
    memory_dir: Optional[Path] = None


class AgentMemoryRuntime:
    """Memory runtime hook for agent rounds.

    Integrates episode graph, memory store, context planning, and usage tracing
    into the Angelus agent lifecycle.
    """

    def __init__(
        self,
        config: MemoryRuntimeConfig,
        llm_fetch_callback: Optional[Callable] = None,
    ) -> None:
        self.config = config
        self.llm_fetch_callback = llm_fetch_callback
        self.graph = EpisodeGraph()
        self.memory_store = MemoryStore()
        self.planner = MemoryPlanner(
            max_context_nodes=config.max_context_nodes,
            pack_keep_recent=config.pack_keep_recent,
        )
        self.context_builder = ContextBuilder(max_context_nodes=config.max_context_nodes)
        self.lifecycle = MemoryLifecycle()
        self._turn_counter: Dict[str, int] = {}  # run_id -> turn count

    # ------------------------------------------------------------------
    # Persistence helpers (JSON file based)
    # ------------------------------------------------------------------

    def _memory_dir_for(self, swarm_name: str) -> Path:
        base = self.config.memory_dir or Path("agents") / swarm_name / "runtime_info" / "memory"
        base.mkdir(parents=True, exist_ok=True)
        return base

    def persist(self, swarm_name: str) -> None:
        if not swarm_name:
            return
        mem_dir = self._memory_dir_for(swarm_name)
        (mem_dir / "episode_graph.json").write_text(
            json.dumps(self.graph.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (mem_dir / "memories.json").write_text(
            json.dumps(self.memory_store.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def load(self, swarm_name: str) -> None:
        if not swarm_name:
            return
        mem_dir = self._memory_dir_for(swarm_name)
        eg_path = mem_dir / "episode_graph.json"
        if eg_path.exists():
            try:
                self.graph = EpisodeGraph.from_dict(json.loads(eg_path.read_text(encoding="utf-8")))
            except Exception:
                logger.exception("Failed to load episode_graph.json")
        ms_path = mem_dir / "memories.json"
        if ms_path.exists():
            try:
                self.memory_store = MemoryStore.from_dict(json.loads(ms_path.read_text(encoding="utf-8")))
            except Exception:
                logger.exception("Failed to load memories.json")

    # ------------------------------------------------------------------
    # before_round
    # ------------------------------------------------------------------

    async def before_round(
        self,
        *,
        agent_id: str,
        swarm_name: str,
        run_id: Optional[str],
        user_message: str,
        parent_node_ids: Optional[Set[str]] = None,
    ) -> MemoryContextPlan:
        """Prepare memory context before an agent round.

        1. Retrieve committed memories.
        2. Optionally ask the planner to select nodes / extract memories.
        3. Compress old context if needed.
        4. Build prompt context.
        """
        turn_id = self._next_turn_id(run_id)
        applied_ops: Dict[str, Any] = {
            "selected_nodes": [],
            "pack_triggers": [],
            "compressed_nodes": [],
            "summary_nodes": [],
            "extracted_memories": [],
            "memory_queries": [],
        }

        # --- Planning ---
        if self.llm_fetch_callback and self.graph.nodes:
            decision = await self.planner.plan(
                user_message=user_message,
                episode_nodes=list(self.graph.nodes.values()),
                memories=self.memory_store.get_all_memories(),
                llm_fetch_callback=self.llm_fetch_callback,
                parent_node_ids=parent_node_ids,
            )
            logger.info("[Agent Memory Decision] %s", decision.reasoning)
            applied_ops["selected_nodes"] = list(decision.selected_node_ids)
            applied_ops["memory_queries"] = list(decision.memory_queries)

            # --- Compression ---
            for pack_nid in list(decision.nodes_to_pack):
                if pack_nid not in self.graph.nodes:
                    continue
                chain = self.graph.get_ancestor_chain(pack_nid, max_nodes=99, strategy="longest")
                if len(chain) <= self.config.pack_keep_recent + 1:
                    # Try fallback to max selected node
                    alt_candidates = [nid for nid in decision.selected_node_ids if nid in self.graph.nodes]
                    if alt_candidates:
                        alt_nid = max(alt_candidates, key=lambda x: self.graph.nodes[x].created_at or x)
                        alt_chain = self.graph.get_ancestor_chain(alt_nid, max_nodes=99, strategy="longest")
                        if len(alt_chain) > self.config.pack_keep_recent + 1:
                            pack_nid = alt_nid
                            chain = alt_chain
                        else:
                            continue
                    else:
                        continue

                if self.llm_fetch_callback:
                    summary_id = await self.graph.compress_ancestors(
                        node_id=pack_nid,
                        llm_summarize_callback=self.llm_fetch_callback,
                        max_nodes=self.config.max_context_nodes + 4,
                        keep_recent=self.config.pack_keep_recent,
                        summary_system_prompt=self.config.summary_system_prompt,
                    )
                    if summary_id is not None:
                        applied_ops["pack_triggers"].append(pack_nid)
                        applied_ops["summary_nodes"].append(summary_id)
                        compressed = list(self.graph.nodes[summary_id].summarizes)
                        applied_ops["compressed_nodes"].extend(compressed)

            # --- Candidate memory extraction (before answering) ---
            if self.config.enable_candidate_memory:
                existing_contents = {m.content.strip() for m in self.memory_store.get_all_memories()}
                for mem_data in decision.memories_to_extract:
                    content = mem_data.get("content", "").strip()
                    kind = mem_data.get("kind", "fact")
                    tags = set(mem_data.get("tags", []))
                    pinned = bool(mem_data.get("pinned", False))
                    packable = bool(mem_data.get("packable", True))
                    if not content:
                        continue
                    if content in existing_contents:
                        logger.info("[记忆提取] 已存在相同记忆，跳过: %s...", content[:40])
                        continue
                    existing_contents.add(content)

                    canonical_key = None
                    if pinned or kind in ("formula", "constraint", "api_contract"):
                        canonical_key = MemoryStore.normalize_formula(content)
                        existing = self.memory_store._canonical_index.get(canonical_key)
                        if existing is not None:
                            logger.info(
                                "[记忆提取] 已存在相同公式（canonical），跳过: %s...",
                                content[:40],
                            )
                            continue

                    # Apply lifecycle defaults
                    defaults = MemoryLifecycle.default_pinned_and_packable(kind)
                    pinned = pinned or defaults[0]
                    packable = packable and defaults[1]

                    mem_id = self.memory_store.add_memory(
                        content=content,
                        kind=kind,
                        source_node_ids=set(decision.selected_node_ids),
                        tags=tags,
                        pinned=pinned,
                        packable=packable,
                        canonical_key=canonical_key,
                        created_turn_id=turn_id,
                        status="candidate",
                    )
                    applied_ops["extracted_memories"].append(mem_id)
                    flag = "[Pinned]" if pinned else ""
                    logger.info(
                        "[记忆提取] Memory %s %s (candidate, turn %s): %s...",
                        mem_id,
                        flag,
                        turn_id,
                        content[:60],
                    )

            selected_node_ids = decision.selected_node_ids
            memory_queries = decision.memory_queries
        else:
            # No planner: use parent nodes or all active nodes
            selected_node_ids = list(parent_node_ids) if parent_node_ids else []
            memory_queries = []

        # --- Build context ---
        plan = self.context_builder.build(
            episode_graph_nodes=self.graph.nodes,
            selected_node_ids=selected_node_ids,
            memories=self.memory_store.get_all_memories(),
            current_turn_id=turn_id,
            memory_queries=memory_queries,
        )
        plan.pack_triggers = list(applied_ops["pack_triggers"])
        plan.compressed_node_ids = list(applied_ops["compressed_nodes"])
        plan.summary_node_ids = list(applied_ops["summary_nodes"])
        plan.reasoning = (
            (decision.reasoning if "decision" in dir() else "Fallback mode")
            + f" | Applied ops: {applied_ops}"
        )

        # Store applied ops in plan metadata for after_round
        plan.metadata = {"applied_ops": applied_ops, "turn_id": turn_id}
        return plan

    # ------------------------------------------------------------------
    # after_round
    # ------------------------------------------------------------------

    async def after_round(
        self,
        *,
        agent_id: str,
        swarm_name: str,
        run_id: Optional[str],
        user_message: str,
        assistant_message: str,
        context_plan: MemoryContextPlan,
    ) -> MemoryUpdateResult:
        """Finalize memory state after an agent round.

        1. Write episode node.
        2. Commit candidate memories.
        3. Verify usage trace.
        4. Persist.
        """
        turn_id = context_plan.metadata.get("turn_id", "unknown")
        applied_ops = dict(context_plan.metadata.get("applied_ops", {}))

        # 1. Write episode node
        parent_ids = set(context_plan.selected_node_ids) if context_plan.selected_node_ids else set()
        # Filter to nodes that actually exist
        parent_ids = {pid for pid in parent_ids if pid in self.graph.nodes}
        new_node_id = self.graph.add_node(
            user_content=user_message,
            assistant_content=assistant_message,
            parent_ids=parent_ids or None,
        )
        applied_ops["new_node_id"] = new_node_id

        # 2. Commit candidates from this turn
        committed_ids: List[str] = []
        if self.config.enable_candidate_memory:
            committed_ids = self.memory_store.commit_candidates(turn_id)
            if committed_ids:
                logger.info(
                    "[Post-answer Commit] candidate 记忆已提交为 committed: %s",
                    committed_ids,
                )

        # 3. Usage trace
        usage_trace = MemoryUsageTrace()
        if self.config.enable_usage_trace:
            # Build memory lookup for injected memories
            injected_ids = list(context_plan.selected_memory_ids)
            memory_lookup = {
                mid: self.memory_store.get_memory(mid)
                for mid in injected_ids
                if self.memory_store.get_memory(mid) is not None
            }
            tracker = UsageTraceTracker(
                injected_memory_ids=injected_ids,
                memory_lookup=memory_lookup,  # type: ignore[arg-type]
                current_turn_id=turn_id,
            )
            # Parse declarations from assistant message
            declarations = UsageTraceTracker.parse_declarations(assistant_message)
            for mem_id_short, stmt in declarations.items():
                # Map short id like "0" to full id if needed; but our ids are hex strings.
                # Try exact match first.
                full_id = mem_id_short if mem_id_short in memory_lookup else None
                if full_id is None:
                    # Heuristic: if the short id looks like a numeric index, skip exact mapping
                    # and just record it as a potential invalid ref.
                    full_id = mem_id_short
                tracker.record_declaration(full_id, stmt)
            usage_trace = tracker.verify_all(assistant_message)

        # 4. Print final state summary
        self._print_state_summary()

        # 5. Persist
        self.persist(swarm_name)

        return MemoryUpdateResult(
            new_node_id=new_node_id,
            committed_memory_ids=committed_ids,
            extracted_memory_ids=list(applied_ops.get("extracted_memories", [])),
            usage_trace=usage_trace,
            applied_ops=applied_ops,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _next_turn_id(self, run_id: Optional[str]) -> str:
        key = run_id or "manual"
        self._turn_counter[key] = self._turn_counter.get(key, 0) + 1
        return f"{key}_turn_{self._turn_counter[key]}"

    def _print_state_summary(self) -> None:
        print("\n" + "=" * 50)
        print("Runtime Applied Ops")
        print("=" * 50)

        # Active Graph
        print("\n【Active Graph 活跃图】")
        active = {nid: n for nid, n in self.graph.nodes.items() if not n.archived}
        for nid, node in sorted(active.items()):
            marker = ""
            if node.is_summary:
                marker += " [摘要节点]"
            print(
                f"  Node {nid}: parents={sorted(node.parent_ids)}, children={sorted(node.child_ids)}{marker}"
            )

        # Archived Graph
        archived = {nid: n for nid, n in self.graph.nodes.items() if n.archived}
        if archived:
            print("\n【Archived Graph 已归档节点】")
            for nid in sorted(archived):
                node = archived[nid]
                print(
                    f"  Node {nid}: summarized_by={sorted(node.summarized_by)}, children={sorted(node.child_ids)}"
                )

        # Pinned Memory
        print("\n【Pinned Memory 永久记忆】")
        pinned = self.memory_store.get_pinned_memories()
        if not pinned:
            print("  （暂无）")
        else:
            for mem in pinned:
                print(f"  Memory {mem.memory_id} [tags={sorted(mem.tags)}]: {mem.content}")

        # All Memory
        print("\n【All Memory 全部记忆】")
        all_mem = self.memory_store.get_all_memories()
        if not all_mem:
            print("  （暂无）")
        else:
            for mem in all_mem:
                flags = []
                if mem.pinned:
                    flags.append("pinned")
                if not mem.packable:
                    flags.append("!packable")
                flag_str = f" [{', '.join(flags)}]" if flags else ""
                print(
                    f"  Memory {mem.memory_id}{flag_str} [{mem.status}] [tags={sorted(mem.tags)}]: {mem.content[:80]}..."
                )
