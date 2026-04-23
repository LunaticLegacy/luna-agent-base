from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..policy import AgentNode, ToolNode
from ..results import ExecutionState


class PayloadHelperMixin:
    """Structured payload helpers for graph execution."""

    def _apply_metadata_updates(self, target_metadata: Dict[str, Any], payload: Dict[str, Any]) -> None:
        metadata_patch = payload.get("metadata_patch")
        if isinstance(metadata_patch, dict):
            target_metadata.update(metadata_patch)

        metadata_clear = payload.get("metadata_clear")
        for key in self._coerce_metadata_keys(metadata_clear):
            target_metadata.pop(key, None)

    def _coerce_metadata_keys(self, raw: Any) -> List[str]:
        if raw is None:
            return []
        if isinstance(raw, str):
            return [raw]
        if isinstance(raw, list):
            return [str(item) for item in raw if item is not None]
        return [str(raw)]

    def _has_content(self, value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (list, dict)):
            return bool(value)
        return True

    def _is_review_control_payload(self, payload: Dict[str, Any]) -> bool:
        verdict = str(payload.get("verdict", "") or payload.get("branch", "")).strip().lower()
        has_routing = any(key in payload for key in ("next_node_id", "next_node_ids", "branch", "branches"))
        return verdict in {"approve", "approved", "revise", "re_research", "reject"} or has_routing

    def _latest_report_payload(self, state: ExecutionState, input_payload: Any) -> Any:
        for key in ("approved_report", "final_report", "final_answer", "draft_report", "latest_report", "report_text"):
            value = state.metadata.get(key)
            if self._has_content(value):
                return value
        return input_payload

    def _preserve_report_fields(
        self,
        state: ExecutionState,
        payload: Dict[str, Any],
        *,
        input_payload: Any,
    ) -> None:
        for key in ("report_text", "draft_report", "approved_report", "final_report", "final_answer"):
            value = payload.get(key)
            if self._has_content(value):
                state.metadata["final_report" if key == "final_answer" else key] = value
                state.metadata["latest_report"] = value

        verdict = str(payload.get("verdict", "") or payload.get("branch", "")).strip().lower()
        if verdict in {"approve", "approved"}:
            approved = (
                payload.get("approved_report")
                or payload.get("final_report")
                or payload.get("final_answer")
                or self._latest_report_payload(state, input_payload)
            )
            if self._has_content(approved):
                state.metadata["approved_report"] = approved
                state.metadata["latest_report"] = approved

    def _extract_final_report_payload(self, payload: Dict[str, Any]) -> Any:
        for key in ("final_report", "final_answer", "approved_report"):
            value = payload.get(key)
            if self._has_content(value):
                return value
        return None

    def _capture_report_payload(self, state: ExecutionState, node: AgentNode, payload: Any) -> None:
        if not self._has_content(payload) or not isinstance(payload, str):
            return
        node_name = node.node_name.lower()
        agent_id = node.agent_id.lower()
        if "writer" in node_name or "writer" in agent_id:
            state.metadata["draft_report"] = payload
            state.metadata["latest_report"] = payload
        elif "publisher" in node_name or "publisher" in agent_id:
            state.metadata["final_report"] = payload
            state.metadata["latest_report"] = payload

    def _build_tool_arguments(self, node: ToolNode, payload: Any, runtime_metadata: Dict[str, Any]) -> Dict[str, Any]:
        if isinstance(payload, dict):
            base_arguments = dict(payload)
        else:
            base_arguments = {"input": payload}
        base_arguments.update(node.input_mapping)
        base_arguments.setdefault("runtime_metadata", dict(runtime_metadata))
        return base_arguments

    def _extract_next_node_id(self, payload: Any) -> Optional[int]:
        if not isinstance(payload, dict):
            return None
        next_node_id = payload.get("next_node_id")
        if next_node_id is None:
            return None
        return int(next_node_id)

    def _parse_structured_agent_output(self, assistant_message: Optional[str]) -> Any:
        if not isinstance(assistant_message, str):
            return None
        candidate = assistant_message.strip()
        if not candidate:
            return None
        if candidate.startswith("```"):
            candidate = self._strip_code_fence(candidate)
        if not candidate.startswith("{") and not candidate.startswith("["):
            return None
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            return None

    def _strip_code_fence(self, text: str) -> str:
        lines = text.splitlines()
        if len(lines) >= 2 and lines[0].strip().startswith("```") and lines[-1].strip().startswith("```"):
            inner = lines[1:-1]
            if inner and inner[0].strip().lower() == "json":
                inner = inner[1:]
            return "\n".join(inner).strip()
        return text.strip()

    def _format_agent_input(self, payload: Any, node: AgentNode) -> str:
        if isinstance(payload, dict):
            if "input" in payload and len(payload) == 1:
                return str(payload["input"])
            return str(payload)
        if node.additional_prompt:
            return f"{payload}\n\n{node.additional_prompt}"
        return str(payload)

