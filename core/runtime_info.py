from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RuntimeInfoManager:
    """Persist live runtime changes for one swarm package."""

    runtime_dir: Path
    agent_name: str
    state_filename: str = "current.json"
    events_filename: str = "events.jsonl"
    _counter: int = 0
    last_event: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.runtime_dir = self.runtime_dir.resolve()
        self.runtime_dir.mkdir(parents=True, exist_ok=True)

    @property
    def state_path(self) -> Path:
        return self.runtime_dir / self.state_filename

    @property
    def events_path(self) -> Path:
        return self.runtime_dir / self.events_filename

    def record(
        self,
        *,
        action: str,
        subject_kind: str,
        subject_id: Optional[str] = None,
        detail: Optional[Dict[str, Any]] = None,
        core: Any = None,
    ) -> Dict[str, Any]:
        """Record one runtime change and refresh the latest snapshot."""
        self._counter += 1
        safe_detail = _sanitize_detail(detail or {})
        current_event = {
            "sequence": self._counter,
            "timestamp": _utc_now_iso(),
            "agent_name": self.agent_name,
            "action": action,
            "subject_kind": subject_kind,
            "subject_id": subject_id,
            "detail": safe_detail,
        }
        self.last_event = current_event
        snapshot = self._build_snapshot(core=core, current_event=current_event)
        event = {
            **current_event,
            "snapshot": snapshot,
        }
        self._append_event(event)
        self._write_snapshot(event)
        return event

    def _build_snapshot(self, *, core: Any = None, current_event: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        graph = core.get_execution_graph() if core is not None else None
        graph_snapshot: Dict[str, Any]
        if graph is None:
            graph_snapshot = {
                "graph_name": None,
                "entry_node_id": None,
                "exit_node_id": None,
                "node_count": 0,
                "edge_count": 0,
            }
        else:
            graph_snapshot = {
                "graph_name": graph.graph_name,
                "entry_node_id": graph.entry_node_id,
                "exit_node_id": graph.exit_node_id,
                "node_count": len(graph.nodes),
                "edge_count": len(graph.edges),
            }

        return {
            "agent_name": self.agent_name,
            "updated_at": _utc_now_iso(),
            "agents": [
                getattr(agent, "agent_id", str(agent))
                for agent in (core.list_agents() if core is not None else [])
            ],
            "tools": sorted(list(core.tools.keys()) if core is not None else []),
            "skills": sorted([skill.name for skill in core.list_skills()] if core is not None else []),
            "graph": graph_snapshot,
            "last_event": {
                "sequence": (current_event or self.last_event).get("sequence"),
                "action": (current_event or self.last_event).get("action"),
                "subject_kind": (current_event or self.last_event).get("subject_kind"),
                "subject_id": (current_event or self.last_event).get("subject_id"),
            },
        }

    def _append_event(self, event: Dict[str, Any]) -> None:
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
            handle.write("\n")

    def _write_snapshot(self, event: Dict[str, Any]) -> None:
        tmp_path = self.state_path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(event, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        tmp_path.replace(self.state_path)


def _sanitize_detail(value: Any, *, max_string_length: int = 500) -> Any:
    if isinstance(value, dict):
        sanitized: Dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key).lower()
            if any(token in normalized_key for token in ("api_key", "token", "secret", "password")):
                sanitized[key] = "[redacted]"
            elif any(token in normalized_key for token in ("prompt", "content")):
                sanitized[key] = _truncate_string(str(item), max_string_length)
            else:
                sanitized[key] = _sanitize_detail(item, max_string_length=max_string_length)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_detail(item, max_string_length=max_string_length) for item in value]
    if isinstance(value, str):
        return _truncate_string(value, max_string_length)
    return value


def _truncate_string(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return f"{value[:max_length].rstrip()}...[truncated]"
