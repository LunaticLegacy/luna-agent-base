from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..policy import AgentNode, ToolNode
from ..results import ExecutionState, NodeExecutionResult, ToolRequest


class PayloadHelperMixin:
    """Structured payload helpers for graph execution."""

    _CONTROL_PAYLOAD_KEYS = {
        "content",
        "final_answer",
        "final_report",
        "approved_report",
        "draft_report",
        "report_text",
        "metadata_patch",
        "metadata_clear",
        "next_node_id",
        "next_node_ids",
        "branch",
        "branches",
        "status",
        "error",
        "decision",
        "verdict",
        "graph_edit",
        "tool_requests",
    }

    # ------------------------------------------------------------------
    # Envelope helpers
    # ------------------------------------------------------------------

    def _extract_metadata_patch(self, parsed_output: Dict[str, Any]) -> Dict[str, Any]:
        """Extract non-control fields from an agent output to store as metadata."""
        patch: Dict[str, Any] = {}
        for key, value in parsed_output.items():
            if key not in self._CONTROL_PAYLOAD_KEYS:
                patch[key] = value
        return patch

    def _extract_control_patch(self, parsed_output: Dict[str, Any]) -> Dict[str, Any]:
        """Extract routing / control fields from an agent output."""
        control: Dict[str, Any] = {}
        for key in ("next_node_id", "next_node_ids", "branch", "branches", "decision", "verdict", "graph_edit"):
            if key in parsed_output:
                control[key] = parsed_output[key]
        return control

    def _build_envelope_agent_input(self, state: ExecutionState, node: AgentNode) -> str:
        """Build a rich user message in envelope mode.

        The agent receives:
        1. The canonical original_request (immutable)
        2. Requirements / constraints / artifact from the envelope
        3. Summaries of previous node outputs (so the agent has full context)
        4. The node's additional_prompt
        """
        request = state.payload
        parts: List[str] = []

        # 1. Canonical request
        if isinstance(request, dict):
            orig = request.get("original_request")
            if orig:
                parts.append(f"## Original Request\n{orig}")
            artifact = request.get("artifact")
            if artifact:
                parts.append(f"## Target Artifact\n{artifact}")
            reqs = request.get("requirements")
            if reqs:
                parts.append(f"## Requirements\n{json.dumps(reqs, ensure_ascii=False, indent=2)}")
            constraints = request.get("constraints")
            if constraints:
                parts.append(f"## Constraints\n{json.dumps(constraints, ensure_ascii=False, indent=2)}")
            attachments = request.get("attachments")
            if attachments:
                parts.append(f"## Attachments\n{json.dumps(attachments, ensure_ascii=False, indent=2)}")
        else:
            parts.append(f"## Request\n{request}")

        # 2. Previous node outputs (chronological)
        outputs = state.metadata.get("outputs")
        if isinstance(outputs, dict) and outputs:
            parts.append("## Previous Node Outputs")
            for node_id, output in outputs.items():
                if isinstance(output, dict) and "content" in output:
                    text = str(output["content"])[:1200]
                    parts.append(f"### Node {node_id}\n{text}")
                elif isinstance(output, str):
                    parts.append(f"### Node {node_id}\n{output[:1200]}")
                else:
                    text = json.dumps(output, ensure_ascii=False, indent=2)[:1200]
                    parts.append(f"### Node {node_id}\n{text}")

        # 3. Additional prompt from the graph node
        if node.additional_prompt:
            parts.append(f"## Additional Instructions\n{node.additional_prompt}")

        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Legacy helpers (kept for backward compatibility)
    # ------------------------------------------------------------------

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

    def _get_latest_output_for_tool(self, state: ExecutionState) -> Any:
        """Return the most recent upstream node output for tool input.

        In Envelope mode, tools should receive the latest upstream agent/tool
        output as their primary input, not the immutable canonical payload.
        """
        outputs = state.metadata.get("outputs")
        if isinstance(outputs, dict) and outputs:
            last_key = list(outputs.keys())[-1]
            last_output = outputs[last_key]
            if isinstance(last_output, dict):
                for key in ("content", "final_answer", "final_report", "approved_report", "draft_report"):
                    if key in last_output:
                        return last_output[key]
                return last_output
            return last_output
        return state.payload

    def _build_tool_arguments(self, node: ToolNode, state: ExecutionState) -> Dict[str, Any]:
        if state.is_envelope:
            latest_output = self._get_latest_output_for_tool(state)
            base_arguments = {
                "input": latest_output,
                "canonical_payload": state.payload,
                "runtime_metadata": dict(state.metadata),
            }
        else:
            if isinstance(state.payload, dict):
                base_arguments = dict(state.payload)
            else:
                base_arguments = {"input": state.payload}
            base_arguments.setdefault("runtime_metadata", dict(state.metadata))
        base_arguments.update(node.input_mapping)
        return base_arguments

    # ------------------------------------------------------------------
    # Normalisation
    # ------------------------------------------------------------------

    def _normalize_agent_node_result(
        self,
        state: ExecutionState,
        node: AgentNode,
        result: Any,
        *,
        input_payload: Any,
    ) -> NodeExecutionResult:
        """Apply the agent output protocol and return routing-ready payloads."""
        parsed_output = self._parse_structured_agent_output(getattr(result, "assistant_message", None))
        state_payload = self._raw_agent_payload(result)
        output_payload = result
        routing_payload = state_payload
        next_node_override = self._extract_next_node_id(state_payload)
        metadata_patch: Optional[Dict[str, Any]] = None
        control_patch: Optional[Dict[str, Any]] = None

        if parsed_output is not None:
            output_payload = parsed_output
            routing_payload = parsed_output
            next_node_override = self._extract_next_node_id(parsed_output)

            if state.is_envelope:
                # Envelope mode: do NOT compress payload to a string.
                # Instead, split the output into metadata (node output) and control (routing).
                metadata_patch = self._extract_metadata_patch(parsed_output)
                control_patch = self._extract_control_patch(parsed_output)
                # state_payload is intentionally left as the raw assistant message
                # so that trace/events still show the raw output.
                state_payload = result.assistant_message if hasattr(result, "assistant_message") else parsed_output
            else:
                # Legacy mode: keep existing compression behaviour.
                state_payload = self._state_payload_from_structured_agent_output(
                    state,
                    parsed_output,
                    input_payload=input_payload,
                    fallback_payload=state_payload,
                )
        elif state.is_envelope:
            # Envelope mode: agent returned non-JSON (e.g. raw source code).
            # Use the raw assistant message as the output payload so downstream
            # tools/agents receive the actual content, not the result object.
            state_payload = self._raw_agent_payload(result)
            output_payload = state_payload
            routing_payload = state_payload

        if not state.is_envelope:
            self._capture_report_payload(state, node, state_payload)

        return NodeExecutionResult(
            output_payload=output_payload,
            routing_payload=routing_payload,
            state_payload=state_payload,
            next_node_override=next_node_override,
            metadata_patch=metadata_patch if metadata_patch is not None else {},
            control_patch=control_patch if control_patch is not None else {},
        )

    def _normalize_tool_node_result(
        self,
        state: ExecutionState,
        output_payload: Any,
        *,
        input_payload: Any,
    ) -> NodeExecutionResult:
        """Apply the tool output protocol and return routing-ready payloads."""
        state_payload = output_payload
        if isinstance(output_payload, dict):
            self._apply_metadata_updates(state.metadata, output_payload)
            self._preserve_report_fields(state, output_payload, input_payload=input_payload)
            final_payload = self._extract_final_report_payload(output_payload)
            if state.is_envelope:
                # Envelope mode: preserve the full dict so downstream agents can read
                # e.g. tool-written file paths, byte counts, etc.
                state_payload = output_payload
            else:
                if self._has_content(final_payload):
                    state_payload = final_payload
                elif "content" in output_payload:
                    state_payload = output_payload["content"]

        return NodeExecutionResult(
            output_payload=output_payload,
            routing_payload=output_payload,
            state_payload=state_payload,
            next_node_override=self._extract_next_node_id(output_payload),
            metadata_patch={},
            control_patch={},
        )

    def _raw_agent_payload(self, result: Any) -> Any:
        if getattr(result, "assistant_message", None):
            return result.assistant_message
        if getattr(result, "raw_response", None) is not None:
            return result.raw_response
        return result

    def _state_payload_from_structured_agent_output(
        self,
        state: ExecutionState,
        parsed_output: Any,
        *,
        input_payload: Any,
        fallback_payload: Any,
    ) -> Any:
        if isinstance(parsed_output, str):
            return parsed_output
        if not isinstance(parsed_output, dict):
            return fallback_payload

        self._apply_metadata_updates(state.metadata, parsed_output)
        self._copy_protocol_metadata(state.metadata, parsed_output)
        self._preserve_report_fields(state, parsed_output, input_payload=input_payload)

        final_payload = self._extract_final_report_payload(parsed_output)
        if self._has_content(final_payload):
            return final_payload
        if "content" in parsed_output and self._has_content(parsed_output["content"]):
            return parsed_output["content"]
        if self._is_review_control_payload(parsed_output):
            return self._latest_report_payload(state, input_payload)
        if "content" not in parsed_output:
            return parsed_output
        return fallback_payload

    def _copy_protocol_metadata(self, target_metadata: Dict[str, Any], payload: Dict[str, Any]) -> None:
        for key, value in payload.items():
            if key not in self._CONTROL_PAYLOAD_KEYS:
                target_metadata[key] = value

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

    def _extract_tool_requests(self, parsed_output: Any) -> Optional[List[ToolRequest]]:
        """Extract tool_requests from a parsed agent JSON envelope."""
        if not isinstance(parsed_output, dict):
            return None
        raw_requests = parsed_output.get("tool_requests")
        if not isinstance(raw_requests, list):
            return None
        requests: List[ToolRequest] = []
        for item in raw_requests:
            if not isinstance(item, dict):
                continue
            requests.append(
                ToolRequest(
                    id=str(item.get("id", f"req-{len(requests)}")),
                    tool=str(item.get("tool", "")),
                    args=dict(item.get("args", {})),
                    depends_on=list(item.get("depends_on", [])),
                    required=bool(item.get("required", True)),
                    on_success=str(item.get("on_success", "continue")),
                    on_failure=str(item.get("on_failure", "return_to_agent")),
                    timeout_ms=int(item.get("timeout_ms", 30000)),
                    resources=list(item.get("resources", [])),
                    metadata=dict(item.get("metadata", {})),
                )
            )
        return requests if requests else None

    def _format_agent_input(self, payload: Any, node: AgentNode) -> str:
        # Envelope mode is handled at the caller site (engine.py) via _build_envelope_agent_input.
        # This legacy path is kept for backward compatibility and for simple string payloads.
        if isinstance(payload, dict):
            if "input" in payload and len(payload) == 1:
                return str(payload["input"])
            return str(payload)
        if node.additional_prompt:
            return f"{payload}\n\n{node.additional_prompt}"
        return str(payload)
