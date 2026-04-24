from __future__ import annotations

import json
import threading
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from web.utils import to_jsonable


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso_timestamp(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def _read_json_list(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def _write_json_list(path: Path, items: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(items, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)


def _normalize_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _json_size(value: Any) -> str:
    text = json.dumps(to_jsonable(value), ensure_ascii=False, indent=2)
    size = len(text.encode("utf-8"))
    if size < 1024:
        return f"{size}B"
    if size < 1024 * 1024:
        return f"{round(size / 1024, 1)}KB"
    return f"{round(size / (1024 * 1024), 1)}MB"


@dataclass
class ContentStore:
    """Persistent content store for knowledge and memory data."""

    data_dir: Path
    runtime_registry: Any
    knowledge_filename: str = "knowledge.json"
    memory_filename: str = "memory.json"
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)
    _knowledge: List[Dict[str, Any]] = field(default_factory=list, init=False, repr=False)
    _memory: List[Dict[str, Any]] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        self.data_dir = Path(self.data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.knowledge_path = self.data_dir / self.knowledge_filename
        self.memory_path = self.data_dir / self.memory_filename
        self._knowledge = _read_json_list(self.knowledge_path)
        self._memory = _read_json_list(self.memory_path)
        if not self._knowledge:
            self._knowledge = self._seed_knowledge()
            self._persist_knowledge()
        if not self._memory:
            self._memory = self._seed_memory()
            self._persist_memory()

    @classmethod
    def from_runtime_registry(cls, data_dir: Path, runtime_registry: Any) -> "ContentStore":
        return cls(data_dir=Path(data_dir), runtime_registry=runtime_registry)

    def list_knowledge(
        self,
        *,
        type_filter: Optional[str] = None,
        source: Optional[str] = None,
        tag: Optional[str] = None,
        q: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> Dict[str, Any]:
        with self._lock:
            items = [deepcopy(item) for item in self._knowledge]
        filtered = self._filter_knowledge(items, type_filter=type_filter, source=source, tag=tag, q=q)
        return self._paginate_knowledge(filtered, page=page, limit=limit)

    def get_knowledge(self, knowledge_id: str) -> Dict[str, Any]:
        with self._lock:
            for item in self._knowledge:
                if item.get("id") == knowledge_id:
                    return deepcopy(item)
        raise KeyError(f"Unknown knowledge id: {knowledge_id}")

    def create_knowledge(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            item = self._normalize_knowledge(payload)
            if any(existing.get("id") == item["id"] for existing in self._knowledge):
                raise ValueError(f"Knowledge id already exists: {item['id']}")
            self._knowledge.append(item)
            self._persist_knowledge()
            return deepcopy(item)

    def update_knowledge(self, knowledge_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            for index, existing in enumerate(self._knowledge):
                if existing.get("id") == knowledge_id:
                    merged = deepcopy(existing)
                    merged.update({key: value for key, value in payload.items() if key not in {"id", "created_at"}})
                    merged["id"] = knowledge_id
                    merged = self._normalize_knowledge(merged, existing=existing)
                    self._knowledge[index] = merged
                    self._persist_knowledge()
                    return deepcopy(merged)
        raise KeyError(f"Unknown knowledge id: {knowledge_id}")

    def delete_knowledge(self, knowledge_id: str) -> Dict[str, Any]:
        with self._lock:
            for index, existing in enumerate(self._knowledge):
                if existing.get("id") == knowledge_id:
                    removed = self._knowledge.pop(index)
                    self._persist_knowledge()
                    return deepcopy(removed)
        raise KeyError(f"Unknown knowledge id: {knowledge_id}")

    def list_memory(
        self,
        *,
        type_filter: Optional[str] = None,
        source: Optional[str] = None,
        q: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> Dict[str, Any]:
        with self._lock:
            items = [deepcopy(item) for item in self._memory]
        filtered = self._filter_memory(items, type_filter=type_filter, source=source, q=q)
        return self._paginate_memory(filtered, page=page, limit=limit)

    def get_memory(self, memory_id: str) -> Dict[str, Any]:
        with self._lock:
            for item in self._memory:
                if item.get("id") == memory_id:
                    return deepcopy(item)
        raise KeyError(f"Unknown memory id: {memory_id}")

    def create_memory(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            item = self._normalize_memory(payload)
            if any(existing.get("id") == item["id"] for existing in self._memory):
                raise ValueError(f"Memory id already exists: {item['id']}")
            self._memory.append(item)
            self._persist_memory()
            return deepcopy(item)

    def delete_memory(self, memory_id: str) -> Dict[str, Any]:
        with self._lock:
            for index, existing in enumerate(self._memory):
                if existing.get("id") == memory_id:
                    removed = self._memory.pop(index)
                    self._persist_memory()
                    return deepcopy(removed)
        raise KeyError(f"Unknown memory id: {memory_id}")

    def _persist_knowledge(self) -> None:
        _write_json_list(self.knowledge_path, self._knowledge)

    def _persist_memory(self) -> None:
        _write_json_list(self.memory_path, self._memory)

    def _seed_knowledge(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        now = _utc_now_iso()
        for swarm in self.runtime_registry.swarms.values():
            graph = swarm.core.get_execution_graph()
            if graph is None:
                continue
            graph_summary = {
                "swarm": swarm.manifest.swarm_name,
                "graph_name": graph.graph_name,
                "entry_node_id": graph.entry_node_id,
                "exit_node_id": graph.exit_node_id,
                "node_count": len(graph.nodes),
                "edge_count": len(graph.edges),
            }
            items.append(
                {
                    "id": f"kb-{swarm.manifest.swarm_name}-graph",
                    "title": f"{swarm.manifest.swarm_name} Graph Overview",
                    "type": "document",
                    "source": "Graph Snapshot",
                    "tags": [swarm.manifest.swarm_name, "graph", "overview"],
                    "status": "active",
                    "citations": max(1, len(graph.nodes)),
                    "created_at": now,
                    "content": json.dumps(graph_summary, ensure_ascii=False, indent=2),
                    "meta": {
                        "author": "System",
                        "version": "1.0",
                        "updated_at": now,
                        "size": _json_size(graph_summary),
                    },
                    "related": [],
                }
            )
            for node in sorted(graph.nodes.values(), key=lambda item: item.node_id):
                metadata = node.metadata if isinstance(node.metadata, dict) else {}
                if not metadata:
                    continue
                item_id = f"kb-{swarm.manifest.swarm_name}-node-{node.node_id}"
                items.append(
                    {
                        "id": item_id,
                        "title": node.node_name,
                        "type": str(metadata.get("knowledge_type") or "snippet"),
                        "source": str(metadata.get("source") or "Graph Metadata"),
                        "tags": sorted(
                            {
                                "graph",
                                node.__class__.__name__.replace("Node", "").lower(),
                                *[str(tag).strip() for tag in _normalize_list(metadata.get("tags"))],
                            }
                        ),
                        "status": str(metadata.get("status") or "active"),
                        "citations": int(metadata.get("citations") or 0),
                        "created_at": now,
                        "content": json.dumps(metadata, ensure_ascii=False, indent=2),
                        "meta": {
                            "author": str(metadata.get("author") or "System"),
                            "version": str(metadata.get("version") or "1.0"),
                            "updated_at": now,
                            "size": _json_size(metadata),
                        },
                        "related": [str(next_id) for next_id in getattr(node, "next_node_ids", [])],
                    }
                )
        return items

    def _seed_memory(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for record in self.runtime_registry.runs.list_runs():
            snapshot = record.snapshot()
            created_at = snapshot.get("finished_at") or snapshot.get("started_at") or snapshot.get("created_at")
            run_summary = {
                "run_id": snapshot.get("run_id"),
                "swarm": snapshot.get("swarm"),
                "status": snapshot.get("status"),
                "rounds": snapshot.get("rounds"),
                "event_count": snapshot.get("event_count"),
                "current_node_name": snapshot.get("current_node_name"),
                "current_node_type": snapshot.get("current_node_type"),
            }
            items.append(
                {
                    "id": f"mem-{snapshot.get('run_id')}",
                    "summary": f"{snapshot.get('swarm')} 运行快照",
                    "content": json.dumps(run_summary, ensure_ascii=False, indent=2),
                    "timestamp": created_at or _utc_now_iso(),
                    "type": "episodic" if snapshot.get("status") in {"completed", "failed"} else "working",
                    "source": str(snapshot.get("swarm") or "system"),
                    "sentiment": 0.7 if snapshot.get("status") == "completed" else (-0.4 if snapshot.get("status") == "failed" else 0.0),
                    "importance": min(100, 60 + int(snapshot.get("event_count") or 0) * 2),
                    "related_ids": [],
                }
            )
            for event in getattr(record, "events", [])[:3]:
                if not isinstance(event, dict):
                    continue
                event_type = str(event.get("event_type") or "")
                if event_type not in {"node.completed", "node.failed", "node.skipped", "run.completed", "run.failed", "architecture_adjusted"}:
                    continue
                data = event.get("data") if isinstance(event.get("data"), dict) else {}
                created = event.get("timestamp")
                created_iso = datetime.fromtimestamp(float(created), tz=timezone.utc).isoformat() if isinstance(created, (int, float)) else _utc_now_iso()
                items.append(
                    {
                        "id": f"mem-{snapshot.get('run_id')}-{len(items)}",
                        "summary": f"{event_type} · {event.get('node_name') or snapshot.get('swarm')}",
                        "content": json.dumps({"event": event, "data": data}, ensure_ascii=False, indent=2),
                        "timestamp": created_iso,
                        "type": "working",
                        "source": str(snapshot.get("swarm") or "system"),
                        "sentiment": -0.2 if event_type.endswith("failed") else 0.2,
                        "importance": 40 + len(items) % 30,
                        "related_ids": [],
                    }
                )
        return items

    def _normalize_knowledge(self, payload: Dict[str, Any], *, existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        now = _utc_now_iso()
        item_id = str(payload.get("id") or (existing or {}).get("id") or f"kb-{uuid.uuid4().hex[:8]}")
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        merged_meta = {
            "author": str(meta.get("author") or (existing or {}).get("meta", {}).get("author") or "System"),
            "version": str(meta.get("version") or (existing or {}).get("meta", {}).get("version") or "1.0"),
            "updated_at": now,
            "size": str(meta.get("size") or (existing or {}).get("meta", {}).get("size") or "0B"),
        }
        if "size" not in meta:
            merged_meta["size"] = _json_size(payload.get("content", (existing or {}).get("content", "")))
        return {
            "id": item_id,
            "title": str(payload.get("title") or (existing or {}).get("title") or item_id),
            "type": str(payload.get("type") or (existing or {}).get("type") or "snippet"),
            "source": str(payload.get("source") or (existing or {}).get("source") or "manual"),
            "tags": _normalize_list(payload.get("tags") or (existing or {}).get("tags") or []),
            "status": str(payload.get("status") or (existing or {}).get("status") or "draft"),
            "citations": int(payload.get("citations") if payload.get("citations") is not None else (existing or {}).get("citations", 0)),
            "created_at": str(payload.get("created_at") or (existing or {}).get("created_at") or now),
            "content": str(payload.get("content") or (existing or {}).get("content") or ""),
            "meta": merged_meta,
            "related": _normalize_list(payload.get("related") or (existing or {}).get("related") or []),
        }

    def _normalize_memory(self, payload: Dict[str, Any], *, existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        now = _utc_now_iso()
        item_id = str(payload.get("id") or (existing or {}).get("id") or f"mem-{uuid.uuid4().hex[:8]}")
        return {
            "id": item_id,
            "summary": str(payload.get("summary") or (existing or {}).get("summary") or item_id),
            "content": str(payload.get("content") or (existing or {}).get("content") or ""),
            "timestamp": str(payload.get("timestamp") or (existing or {}).get("timestamp") or now),
            "type": str(payload.get("type") or (existing or {}).get("type") or "working"),
            "source": str(payload.get("source") or (existing or {}).get("source") or "system"),
            "sentiment": float(payload.get("sentiment") if payload.get("sentiment") is not None else (existing or {}).get("sentiment", 0.0)),
            "importance": int(payload.get("importance") if payload.get("importance") is not None else (existing or {}).get("importance", 50)),
            "related_ids": _normalize_list(payload.get("related_ids") or (existing or {}).get("related_ids") or []),
        }

    def _filter_knowledge(
        self,
        items: List[Dict[str, Any]],
        *,
        type_filter: Optional[str] = None,
        source: Optional[str] = None,
        tag: Optional[str] = None,
        q: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        normalized_type = str(type_filter or "").strip().lower()
        normalized_source = str(source or "").strip().lower()
        normalized_tag = str(tag or "").strip().lower()
        normalized_query = str(q or "").strip().lower()
        filtered: List[Dict[str, Any]] = []
        for item in items:
            if normalized_type and str(item.get("type", "")).lower() != normalized_type:
                continue
            if normalized_source and normalized_source not in str(item.get("source", "")).lower():
                continue
            if normalized_tag and normalized_tag not in " ".join(str(tag) for tag in item.get("tags", [])).lower():
                continue
            if normalized_query:
                searchable = " ".join(
                    [
                        str(item.get("id", "")),
                        str(item.get("title", "")),
                        str(item.get("source", "")),
                        " ".join(str(tag) for tag in item.get("tags", [])),
                        str(item.get("content", "")),
                        str(item.get("status", "")),
                    ]
                ).lower()
                if normalized_query not in searchable:
                    continue
            filtered.append(item)
        return sorted(filtered, key=lambda item: str(item.get("created_at") or ""), reverse=True)

    def _filter_memory(
        self,
        items: List[Dict[str, Any]],
        *,
        type_filter: Optional[str] = None,
        source: Optional[str] = None,
        q: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        normalized_type = str(type_filter or "").strip().lower()
        normalized_source = str(source or "").strip().lower()
        normalized_query = str(q or "").strip().lower()
        filtered: List[Dict[str, Any]] = []
        for item in items:
            if normalized_type and str(item.get("type", "")).lower() != normalized_type:
                continue
            if normalized_source and normalized_source not in str(item.get("source", "")).lower():
                continue
            if normalized_query:
                searchable = " ".join(
                    [
                        str(item.get("id", "")),
                        str(item.get("summary", "")),
                        str(item.get("content", "")),
                        str(item.get("source", "")),
                        " ".join(str(ref) for ref in item.get("related_ids", [])),
                    ]
                ).lower()
                if normalized_query not in searchable:
                    continue
            filtered.append(item)
        return sorted(filtered, key=lambda item: str(item.get("timestamp") or ""), reverse=True)

    def _paginate_knowledge(self, items: List[Dict[str, Any]], *, page: int, limit: int) -> Dict[str, Any]:
        total = len(items)
        page = max(1, int(page or 1))
        limit = max(1, int(limit or 20))
        start = (page - 1) * limit
        page_items = items[start : start + limit]
        return {
            "total": total,
            "page": page,
            "limit": limit,
            "items": page_items,
            "stats": {
                "total": total,
                "documents": sum(1 for item in items if str(item.get("type", "")).lower() == "document"),
                "vectors": sum(1 for item in items if str(item.get("type", "")).lower() == "vector"),
                "rules": sum(1 for item in items if str(item.get("type", "")).lower() == "rule"),
            },
        }

    def _paginate_memory(self, items: List[Dict[str, Any]], *, page: int, limit: int) -> Dict[str, Any]:
        total = len(items)
        page = max(1, int(page or 1))
        limit = max(1, int(limit or 20))
        start = (page - 1) * limit
        page_items = items[start : start + limit]
        now = datetime.now(timezone.utc)
        recent_cutoff = now - timedelta(days=30)
        return {
            "total": total,
            "page": page,
            "limit": limit,
            "items": page_items,
            "stats": {
                "total": total,
                "active": sum(1 for item in items if (parsed := _parse_iso_timestamp(str(item.get("timestamp") or ""))) is not None and parsed >= recent_cutoff),
                "avg_importance": int(round(sum(float(item.get("importance", 0)) for item in items) / total)) if total else 0,
                "long_term": sum(1 for item in items if str(item.get("type", "")).lower() in {"episodic", "semantic", "procedural"}),
                "working": sum(1 for item in items if str(item.get("type", "")).lower() == "working"),
            },
        }
