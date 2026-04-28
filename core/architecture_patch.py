from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


SUPPORTED_ARCHITECTURE_OPS = {
    "add_agent",
    "remove_agent",
    "add_agent_node",
    "add_tool_node",
    "remove_node",
    "add_edge",
    "remove_edge",
    "replace_next",
    "insert_after",
    "update_node_metadata",
    "update_route",
    "update_retry_policy",
    "update_output_mode",
    "rollback_patch",
}


@dataclass
class ArchitectureOperation:
    op: str
    payload: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "ArchitectureOperation":
        payload = dict(raw)
        op = str(payload.pop("op", "")).strip()
        return cls(op=op, payload=payload)

    def to_dict(self) -> Dict[str, Any]:
        return {"op": self.op, **dict(self.payload)}


@dataclass
class ArchitecturePatch:
    patch_id: str
    reason: str
    scope: str = "package"
    operations: List[ArchitectureOperation] = field(default_factory=list)
    rollback: Dict[str, Any] = field(default_factory=lambda: {"action": "revert_patch"})
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "ArchitecturePatch":
        if not isinstance(raw, dict):
            raise ValueError("architecture_patch must be an object.")
        operations = [
            ArchitectureOperation.from_dict(item)
            for item in raw.get("operations", []) or []
            if isinstance(item, dict)
        ]
        return cls(
            patch_id=str(raw.get("patch_id") or "").strip(),
            reason=str(raw.get("reason") or "").strip(),
            scope=str(raw.get("scope") or "package").strip() or "package",
            operations=operations,
            rollback=dict(raw.get("rollback", {"action": "revert_patch"}) or {}),
            metadata=dict(raw.get("metadata", {}) or {}),
        )

    @classmethod
    def coerce(cls, raw: Any) -> "ArchitecturePatch":
        if isinstance(raw, ArchitecturePatch):
            return raw
        return cls.from_dict(raw)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "patch_id": self.patch_id,
            "reason": self.reason,
            "scope": self.scope,
            "operations": [op.to_dict() for op in self.operations],
            "rollback": dict(self.rollback),
            "metadata": dict(self.metadata),
        }


def architecture_patch_example() -> Dict[str, Any]:
    return {
        "patch_id": "patch-output-repairer-001",
        "reason": "coder structured output parse failed",
        "scope": "package",
        "operations": [
            {
                "op": "add_agent",
                "agent_id": "output_repairer",
                "name": "Output Repairer",
                "character_prompt": "Repair malformed structured outputs. Do not execute tools.",
                "tools": [],
                "tool_execution_mode": "disabled",
            },
            {
                "op": "add_agent_node",
                "node_id": "auto",
                "node_name": "output_repairer_node",
                "agent_id": "output_repairer",
                "persistence": "transient",
                "lifetime_policy": "run",
            },
            {
                "op": "insert_after",
                "target_node_id": 2,
                "new_node_ref": "output_repairer_node",
                "preserve_downstream": True,
            },
        ],
        "rollback": {"action": "revert_patch"},
    }
