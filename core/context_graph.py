from __future__ import annotations

import copy
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .cognitive import CognitiveGraph
from .cognitive_parts.types import CognitiveEdge, CognitiveNode, CognitiveNodeType, CognitiveRelationType


class ContextEntryType(str, Enum):
    SYSTEM = "system"
    FACT = "fact"
    EVIDENCE = "evidence"
    CLAIM = "claim"
    QUESTION = "question"
    GOAL = "goal"
    TASK = "task"
    SUMMARY = "summary"
    MEMORY = "memory"
    WORKSPACE = "workspace"
    NOTE = "note"


class ContextRelation(str, Enum):
    REFERENCES = "references"
    SUMMARY_OF = "summary_of"
    ELABORATION_OF = "elaboration_of"
    CONTRADICTS = "contradicts"
    CAUSED_BY = "caused_by"
    VERSION_OF = "version_of"
    MERGED_FROM = "merged_from"


@dataclass
class ContextReference:
    target_id: str
    relation: ContextRelation
    target_hash: str
    fallback_inline: Optional[str] = None
    weight: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_id": self.target_id,
            "relation": self.relation.value,
            "target_hash": self.target_hash,
            "fallback_inline": self.fallback_inline,
            "weight": self.weight,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContextReference":
        return cls(
            target_id=str(data.get("target_id", "")),
            relation=ContextRelation(str(data.get("relation", ContextRelation.REFERENCES.value))),
            target_hash=str(data.get("target_hash", "")),
            fallback_inline=data.get("fallback_inline"),
            weight=float(data.get("weight", 1.0)),
        )


@dataclass
class ContextEntry:
    id: str
    summary: str
    content: str
    token_count: int
    timestamp: float
    entry_type: ContextEntryType
    outgoing_refs: List[ContextReference] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_retained: bool = False

    def content_hash(self) -> str:
        encoded = self.content.encode("utf-8")
        return f"sha256:{hashlib.sha256(encoded).hexdigest()}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "summary": self.summary,
            "content": self.content,
            "token_count": self.token_count,
            "timestamp": self.timestamp,
            "entry_type": self.entry_type.value,
            "outgoing_refs": [ref.to_dict() for ref in self.outgoing_refs],
            "metadata": dict(self.metadata),
            "is_retained": self.is_retained,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContextEntry":
        return cls(
            id=str(data.get("id", "")),
            summary=str(data.get("summary", "")),
            content=str(data.get("content", "")),
            token_count=int(data.get("token_count", 0)),
            timestamp=float(data.get("timestamp", 0.0)),
            entry_type=ContextEntryType(str(data.get("entry_type", ContextEntryType.NOTE.value))),
            outgoing_refs=[ContextReference.from_dict(item) for item in data.get("outgoing_refs", []) or []],
            metadata=dict(data.get("metadata", {}) or {}),
            is_retained=bool(data.get("is_retained", False)),
        )


@dataclass
class ContextGraph:
    graph_id: str = ""
    entries: Dict[str, ContextEntry] = field(default_factory=dict)

    def add_entry(self, entry: ContextEntry) -> ContextEntry:
        if not entry.token_count:
            entry.token_count = _estimate_tokens(entry.content)
        self.entries[entry.id] = entry
        return entry

    def add_reference(self, source_id: str, reference: ContextReference) -> ContextReference:
        source = self.entries.get(source_id)
        if source is None:
            raise KeyError(f"Unknown source entry: {source_id}")
        source.outgoing_refs.append(reference)
        return reference

    def get_entry(self, entry_id: str) -> Optional[ContextEntry]:
        return self.entries.get(entry_id)

    def get_incoming_refs(self, target_id: str) -> List[Tuple[ContextEntry, ContextReference]]:
        incoming: List[Tuple[ContextEntry, ContextReference]] = []
        for entry in self.entries.values():
            for ref in entry.outgoing_refs:
                if ref.target_id == target_id:
                    incoming.append((entry, ref))
        return incoming

    def query_subgraph(
        self,
        seed_ids: List[str],
        max_hops: int = 2,
        max_nodes: int = 50,
        min_relevance: float = 0.1,
    ) -> "ContextGraph":
        if not seed_ids:
            return ContextGraph(graph_id=f"{self.graph_id}_sub")

        visited: set[str] = set(seed_ids)
        frontier: List[Tuple[str, int, float]] = [(seed_id, 0, 1.0) for seed_id in seed_ids if seed_id in self.entries]
        scores: Dict[str, float] = {seed_id: 1.0 for seed_id in seed_ids if seed_id in self.entries}

        while frontier:
            current_id, hop, score = frontier.pop(0)
            if hop >= max_hops:
                continue
            current = self.entries.get(current_id)
            if current is None:
                continue
            for ref in current.outgoing_refs:
                target = self.entries.get(ref.target_id)
                if target is None:
                    continue
                propagated = score * ref.weight * (0.5 ** hop)
                if propagated < min_relevance:
                    continue
                if target.id not in visited:
                    visited.add(target.id)
                    scores[target.id] = propagated
                    frontier.append((target.id, hop + 1, propagated))

        ordered_ids = sorted(
            visited,
            key=lambda entry_id: (
                0 if entry_id in seed_ids else 1,
                -scores.get(entry_id, 0.0),
                self.entries.get(entry_id).timestamp if self.entries.get(entry_id) is not None else 0.0,
                entry_id,
            ),
        )
        if len(ordered_ids) > max_nodes:
            ordered_ids = ordered_ids[:max_nodes]

        subgraph = ContextGraph(graph_id=f"{self.graph_id}_sub")
        for entry_id in ordered_ids:
            if entry_id in self.entries:
                subgraph.add_entry(copy.deepcopy(self.entries[entry_id]))
        for entry in list(subgraph.entries.values()):
            filtered_refs = [ref for ref in entry.outgoing_refs if ref.target_id in subgraph.entries]
            entry.outgoing_refs = filtered_refs
        return subgraph

    def cascade_retain(self, entry_id: str, depth: int = 2) -> set[str]:
        retained: set[str] = set()
        queue: List[Tuple[str, int]] = [(entry_id, depth)]
        while queue:
            current_id, remaining_depth = queue.pop(0)
            if current_id in retained or remaining_depth < 0:
                continue
            current = self.entries.get(current_id)
            if current is None:
                continue
            current.is_retained = True
            retained.add(current_id)
            for ref in current.outgoing_refs:
                target = self.entries.get(ref.target_id)
                if target is None:
                    continue
                depth_cost = {
                    ContextRelation.REFERENCES: 1,
                    ContextRelation.CAUSED_BY: 1,
                    ContextRelation.CONTRADICTS: 0,
                    ContextRelation.ELABORATION_OF: 2,
                    ContextRelation.SUMMARY_OF: 0,
                    ContextRelation.VERSION_OF: 1,
                    ContextRelation.MERGED_FROM: 1,
                }.get(ref.relation, 1)
                new_depth = remaining_depth - depth_cost
                if new_depth >= 0:
                    queue.append((target.id, new_depth))
        return retained

    def prune_graph(self, anchor_id: str, token_budget: int) -> "ContextGraph":
        working = self.clone()
        for entry in working.entries.values():
            entry.is_retained = entry.entry_type == ContextEntryType.SYSTEM

        if anchor_id and anchor_id in working.entries:
            working.cascade_retain(anchor_id, depth=2)

        budget = max(0, int(token_budget))
        retained_entries = [entry for entry in working.entries.values() if entry.is_retained]
        retained_entries.sort(key=lambda entry: (_entry_priority(entry), entry.timestamp, entry.id))

        total_tokens = sum(entry.token_count for entry in retained_entries)
        if total_tokens > budget:
            drop_candidates = [entry for entry in retained_entries if entry.entry_type != ContextEntryType.SYSTEM]
            drop_candidates.sort(key=lambda entry: (_entry_importance(entry, working), entry.timestamp, entry.id))
            for entry in drop_candidates:
                if total_tokens <= budget:
                    break
                entry.is_retained = False
                total_tokens -= entry.token_count

        remaining = budget - sum(entry.token_count for entry in working.entries.values() if entry.is_retained)
        candidates = [
            entry
            for entry in working.entries.values()
            if not entry.is_retained and entry.entry_type != ContextEntryType.SYSTEM
        ]
        candidates.sort(key=lambda entry: (-_entry_importance(entry, working), entry.timestamp, entry.id))
        for entry in candidates:
            if entry.token_count <= remaining:
                entry.is_retained = True
                remaining -= entry.token_count

        working._resolve_missing_references()
        if sum(entry.token_count for entry in working.entries.values() if entry.is_retained) > budget:
            for entry in sorted(
                [item for item in working.entries.values() if item.is_retained and item.entry_type != ContextEntryType.SYSTEM],
                key=lambda item: (_entry_importance(item, working), item.timestamp, item.id),
            ):
                if sum(item.token_count for item in working.entries.values() if item.is_retained) <= budget:
                    break
                entry.is_retained = False
        return working

    def _resolve_missing_references(self) -> None:
        for entry in self.entries.values():
            if not entry.is_retained:
                continue
            resolved = entry.metadata.setdefault("resolved_refs", [])
            resolved_ids = set(str(item) for item in resolved)
            for ref in entry.outgoing_refs:
                if ref.target_id in self.entries and self.entries[ref.target_id].is_retained:
                    continue
                if ref.target_id in resolved_ids:
                    continue
                target = self.entries.get(ref.target_id)
                if target is None:
                    continue
                inline = ref.fallback_inline or target.summary or target.content[:120]
                if ref.relation == ContextRelation.REFERENCES:
                    entry.content = f"[引用: {inline}]\n{entry.content}".strip()
                elif ref.relation == ContextRelation.CAUSED_BY:
                    entry.content = f"[因果上下文: {inline}]\n{entry.content}".strip()
                elif ref.relation == ContextRelation.CONTRADICTS:
                    entry.content += f"\n[注: 与原观点 {target.id} 的矛盾论证因空间限制被裁剪]"
                elif ref.relation == ContextRelation.SUMMARY_OF:
                    entry.content = f"[摘要替代: {inline}]\n{entry.content}".strip()
                elif ref.relation == ContextRelation.VERSION_OF:
                    entry.content = f"[版本上下文: {inline}]\n{entry.content}".strip()
                elif ref.relation == ContextRelation.ELABORATION_OF:
                    entry.content = f"[展开上下文: {inline}]\n{entry.content}".strip()
                resolved.append(target.id)
                resolved_ids.add(target.id)
            entry.token_count = _estimate_tokens(entry.content)

    def assemble_prompt(
        self,
        *,
        anchor_id: Optional[str] = None,
        token_budget: int = 2048,
        title: str = "Context Graph",
    ) -> str:
        if not self.entries:
            return f"{title} (empty)"

        anchor = anchor_id
        if anchor is None or anchor not in self.entries:
            system_entry = next((entry for entry in self.entries.values() if entry.entry_type == ContextEntryType.SYSTEM), None)
            anchor = system_entry.id if system_entry is not None else next(iter(self.entries.keys()))

        pruned = self.prune_graph(anchor, token_budget=token_budget)
        retained = [
            entry
            for entry in pruned.entries.values()
            if entry.is_retained or entry.entry_type == ContextEntryType.SYSTEM
        ]
        retained.sort(
            key=lambda entry: (
                _entry_priority(entry),
                entry.timestamp,
                entry.id,
            )
        )

        lines: List[str] = [
            f"{title} (id={pruned.graph_id or self.graph_id}, entries={len(pruned.entries)})",
        ]
        for entry in retained:
            header = f"[{entry.entry_type.value.upper()}: {entry.id}]"
            if entry.summary and entry.summary != entry.content:
                header = f"{header} {entry.summary}"
            lines.append(header)
            if entry.outgoing_refs:
                ref_bits = []
                for ref in entry.outgoing_refs:
                    relation = ref.relation.value
                    ref_bits.append(f"{relation}->{ref.target_id}")
                lines.append(f"refs: {', '.join(ref_bits)}")
            lines.append(entry.content.strip() or entry.summary.strip() or "[empty]")
            lines.append("")
        return "\n".join(lines).strip()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "entries": [entry.to_dict() for entry in self.entries.values()],
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "ContextGraph":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(payload)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContextGraph":
        graph = cls(graph_id=str(data.get("graph_id", "")))
        for raw_entry in data.get("entries", []) or []:
            if isinstance(raw_entry, dict):
                graph.add_entry(ContextEntry.from_dict(raw_entry))
        return graph

    def clone(self) -> "ContextGraph":
        return ContextGraph.from_dict(self.to_dict())

    @classmethod
    def from_cognitive_graph(
        cls,
        cognitive_graph: CognitiveGraph,
        *,
        query: Optional[str] = None,
        seed_ids: Optional[List[str]] = None,
        purpose: str = "",
        max_nodes: int = 20,
        max_hops: int = 2,
    ) -> tuple["ContextGraph", List[str]]:
        if seed_ids:
            descriptor_roots = [seed_id for seed_id in seed_ids if seed_id in cognitive_graph.nodes]
            subgraph = cognitive_graph.query_subgraph(descriptor_roots, max_hops=max_hops, max_nodes=max_nodes)
        elif query:
            descriptor, subgraph = cognitive_graph.describe_subgraph(
                query=query,
                purpose=purpose,
                max_nodes=max_nodes,
                max_hops=max_hops,
            )
            descriptor_roots = list(descriptor.root_node_ids)
        else:
            descriptor_roots = list(cognitive_graph.nodes.keys())[:max_nodes]
            subgraph = cognitive_graph.query_subgraph(descriptor_roots, max_hops=max_hops, max_nodes=max_nodes)

        context_graph = cls(graph_id=f"{cognitive_graph.graph_id}_context")
        for node in subgraph.nodes.values():
            context_graph.add_entry(_context_entry_from_cognitive_node(node))
        for edge in subgraph.edges:
            if edge.source_id not in context_graph.entries or edge.target_id not in context_graph.entries:
                continue
            context_graph.add_reference(
                edge.source_id,
                ContextReference(
                    target_id=edge.target_id,
                    relation=_context_relation_from_cognitive_relation(edge.relation),
                    target_hash=context_graph.entries[edge.target_id].content_hash(),
                    fallback_inline=context_graph.entries[edge.target_id].summary or context_graph.entries[edge.target_id].content[:120],
                    weight=max(0.2, float(edge.strength)),
                ),
            )
        return context_graph, descriptor_roots or list(context_graph.entries.keys())[:1]


def _context_entry_from_cognitive_node(node: CognitiveNode) -> ContextEntry:
    entry_type = _context_entry_type_from_cognitive_node_type(node.node_type)
    content = str(node.content or "")
    summary = str(node.summary or content[:160]).strip()
    timestamp = _parse_timestamp(node.created_at)
    metadata = {
        "source": node.source,
        "confidence": node.confidence,
        "node_type": node.node_type.value,
        "version": node.version,
        "tags": list(node.tags),
    }
    return ContextEntry(
        id=node.node_id,
        summary=summary or content[:120],
        content=content,
        token_count=_estimate_tokens(content),
        timestamp=timestamp,
        entry_type=entry_type,
        metadata=metadata,
    )


def _context_entry_type_from_cognitive_node_type(node_type: CognitiveNodeType) -> ContextEntryType:
    mapping = {
        CognitiveNodeType.FACT: ContextEntryType.FACT,
        CognitiveNodeType.EVIDENCE: ContextEntryType.EVIDENCE,
        CognitiveNodeType.CLAIM: ContextEntryType.CLAIM,
        CognitiveNodeType.QUESTION: ContextEntryType.QUESTION,
        CognitiveNodeType.GOAL: ContextEntryType.GOAL,
        CognitiveNodeType.REASONING: ContextEntryType.NOTE,
        CognitiveNodeType.HYPOTHESIS: ContextEntryType.NOTE,
        CognitiveNodeType.GUESS: ContextEntryType.NOTE,
        CognitiveNodeType.ASSUMPTION: ContextEntryType.NOTE,
        CognitiveNodeType.DECISION: ContextEntryType.NOTE,
        CognitiveNodeType.RISK: ContextEntryType.NOTE,
        CognitiveNodeType.COUNTEREVIDENCE: ContextEntryType.EVIDENCE,
        CognitiveNodeType.TOOL_RESULT: ContextEntryType.MEMORY,
        CognitiveNodeType.EXECUTION_TRACE: ContextEntryType.MEMORY,
    }
    return mapping.get(node_type, ContextEntryType.NOTE)


def _context_relation_from_cognitive_relation(relation: CognitiveRelationType) -> ContextRelation:
    mapping = {
        CognitiveRelationType.SUPPORTS: ContextRelation.REFERENCES,
        CognitiveRelationType.OPPOSES: ContextRelation.CONTRADICTS,
        CognitiveRelationType.DERIVES_FROM: ContextRelation.CAUSED_BY,
        CognitiveRelationType.LEADS_TO: ContextRelation.ELABORATION_OF,
        CognitiveRelationType.DEPENDS_ON: ContextRelation.REFERENCES,
        CognitiveRelationType.QUESTIONS: ContextRelation.ELABORATION_OF,
        CognitiveRelationType.REFINES: ContextRelation.VERSION_OF,
        CognitiveRelationType.VERIFIES: ContextRelation.REFERENCES,
        CognitiveRelationType.DISPROVES: ContextRelation.CONTRADICTS,
        CognitiveRelationType.SPECULATES: ContextRelation.ELABORATION_OF,
        CognitiveRelationType.RELATES: ContextRelation.MERGED_FROM,
        CognitiveRelationType.EVIDENCE_FOR: ContextRelation.REFERENCES,
    }
    return mapping.get(relation, ContextRelation.REFERENCES)


def _estimate_tokens(content: str) -> int:
    return max(0, len(str(content)) // 4)


def _parse_timestamp(raw: Any) -> float:
    if isinstance(raw, (int, float)):
        return float(raw)
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
    except Exception:
        return datetime.now(timezone.utc).timestamp()


def _entry_priority(entry: ContextEntry) -> int:
    return {
        ContextEntryType.SYSTEM: 0,
        ContextEntryType.GOAL: 1,
        ContextEntryType.CLAIM: 2,
        ContextEntryType.FACT: 2,
        ContextEntryType.EVIDENCE: 3,
        ContextEntryType.QUESTION: 3,
        ContextEntryType.SUMMARY: 4,
        ContextEntryType.WORKSPACE: 5,
        ContextEntryType.MEMORY: 5,
        ContextEntryType.NOTE: 6,
        ContextEntryType.TASK: 6,
    }.get(entry.entry_type, 6)


def _entry_importance(entry: ContextEntry, graph: ContextGraph) -> float:
    outgoing = len(entry.outgoing_refs)
    incoming = len(graph.get_incoming_refs(entry.id))
    recency = entry.timestamp
    return (incoming * 2.0) + outgoing + (recency / 10_000_000_000.0)
