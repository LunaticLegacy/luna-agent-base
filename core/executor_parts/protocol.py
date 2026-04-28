from __future__ import annotations

import copy
import json
from typing import Any, Dict, List, Optional

from ..architecture_patch import ArchitecturePatch
from ..errors import OutputParseError
from ..policy import AgentNode, ExecutionGraph, ToolNode, _node_is_transient
from ..results import ExecutionState


class ExecutionProtocolMixin:
    """Payload normalisation, routing, and report-field helpers for graph execution."""

    # ------------------------------------------------------------------
    # Keys that are considered routing / control rather than metadata.
    # ------------------------------------------------------------------
    _CONTROL_PAYLOAD_KEYS = {
        "next_node_id",
        "next_node_ids",
        "branch",
        "branches",
        "decision",
        "verdict",
        "graph_edit",
        "final_answer",
        "final_report",
        "approved_report",
        "draft_report",
        "report_text",
        "metadata_patch",
        "metadata_clear",
    }

    # ------------------------------------------------------------------
    # Metadata helpers
    # ------------------------------------------------------------------

    def _apply_metadata_updates(self, target_metadata: Dict[str, Any], payload: Dict[str, Any]) -> None:
        metadata_patch = payload.get("metadata_patch")
        if isinstance(metadata_patch, dict):
            target_metadata.update(metadata_patch)
        metadata_clear = payload.get("metadata_clear")
        if isinstance(metadata_clear, list):
            for key in metadata_clear:
                target_metadata.pop(key, None)

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

    # ------------------------------------------------------------------
    # Report-field helpers
    # ------------------------------------------------------------------

    def _has_content(self, value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str) and not value.strip():
            return False
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
        # Reports may be stored in outputs.
        # Prefer the most recent *content* output, skipping reviewer/control
        # payloads that carry verdicts/branches but not actual report content.
        outputs = state.metadata.get("outputs")
        if isinstance(outputs, dict) and outputs:
            for last_output in reversed(list(outputs.values())):
                if isinstance(last_output, dict):
                    has_control = any(k in last_output for k in ("verdict", "branch", "next_node_id", "next_node_ids", "decision", "graph_edit"))
                    # If the dict carries report-specific keys, trust them even
                    # if it also has routing fields (e.g. a publisher node).
                    for key in ("final_answer", "final_report", "approved_report", "draft_report"):
                        value = last_output.get(key)
                        if self._has_content(value):
                            return value
                    # For generic "content", only accept it from non-control
                    # payloads so reviewer comments don't become the report.
                    if not has_control:
                        value = last_output.get("content")
                        if self._has_content(value):
                            return value
                    # If the dict is substantive and has no control keys, use it.
                    if not has_control and last_output:
                        return last_output
                elif self._has_content(last_output):
                    return last_output
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

    # ------------------------------------------------------------------
    # Parsing / extraction helpers
    # ------------------------------------------------------------------

    def _parse_structured_agent_output(
        self,
        assistant_message: Optional[str],
        *,
        required: bool = False,
        expected_schema: Optional[Any] = None,
        parser_stage: str = "agent_structured_output",
    ) -> Optional[Dict[str, Any]]:
        if not assistant_message:
            if required:
                raise OutputParseError(
                    "Expected JSON object but agent output was empty.",
                    raw_output="",
                    parser_stage=parser_stage,
                    expected_schema=expected_schema,
                )
            return None
        text = assistant_message.strip()
        if not text:
            if required:
                raise OutputParseError(
                    "Expected JSON object but agent output was empty.",
                    raw_output=assistant_message,
                    parser_stage=parser_stage,
                    expected_schema=expected_schema,
                )
            return None
        # Support markdown-fenced JSON
        if text.startswith("```"):
            lines = text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
            if required:
                raise OutputParseError(
                    "Expected JSON object but parsed output was not an object.",
                    raw_output=assistant_message,
                    parser_stage=parser_stage,
                    expected_schema=expected_schema,
                )
        except json.JSONDecodeError as exc:
            if required:
                raise OutputParseError(
                    f"Failed to parse required JSON output: {exc.msg}",
                    raw_output=assistant_message,
                    parser_stage=parser_stage,
                    expected_schema=expected_schema,
                    line=exc.lineno,
                    column=exc.colno,
                    pos=exc.pos,
                ) from exc
        return None

    def _node_output_mode(self, node: AgentNode) -> str:
        mode = str((node.metadata or {}).get("output_mode") or "").strip().lower()
        if mode:
            return mode
        node_name = str(getattr(node, "node_name", "")).lower()
        if any(token in node_name for token in ("writer", "report", "coder")):
            return "raw_text" if "coder" in node_name else "json_optional"
        return "json_optional"

    def _extract_next_node_id(self, payload: Any) -> Optional[int]:
        if isinstance(payload, dict):
            nid = payload.get("next_node_id")
            if isinstance(nid, int):
                return nid
            if isinstance(nid, str) and nid.isdigit():
                return int(nid)
        return None

    def _extract_artifact_path(self, payload: Dict[str, Any]) -> Optional[str]:
        path = payload.get("artifact")
        if path:
            return path
        # Fallback: scan the text for save-as patterns.
        text = json.dumps(payload, ensure_ascii=False)
        import re
        patterns = [
            r"(?:save as|save to|save it to|write to|write as|命名为|保存为|将该文件命名为|文件名为)\s+['\"]?([\w/\\.\-]+)['\"]?",
            r"(?:name it|call it)\s+['\"]?([\w/\\.\-]+)['\"]?",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(1)
        return None

    def _raw_agent_payload(self, result: Any) -> Any:
        if getattr(result, "assistant_message", None):
            return result.assistant_message
        if isinstance(result, dict):
            return result.get("assistant_message") or result.get("content") or result
        return result

    # ------------------------------------------------------------------
    # Tool argument builders
    # ------------------------------------------------------------------

    def _get_latest_output_for_tool(self, state: ExecutionState) -> Any:
        """Return the most recent upstream node output for tool input."""
        outputs = state.metadata.get("outputs")
        if isinstance(outputs, dict) and outputs:
            last_key = list(outputs.keys())[-1]
            last_output = outputs[last_key]
            if isinstance(last_output, dict):
                for key in ("final_answer", "final_report", "approved_report", "draft_report", "content"):
                    if key in last_output:
                        return last_output[key]
                return last_output
            return last_output
        return state.payload

    def _build_tool_arguments(self, node: ToolNode, state: ExecutionState) -> Dict[str, Any]:
        latest_output = self._get_latest_output_for_tool(state)
        base_arguments = {
            "input": latest_output,
            "payload": state.payload,
            "runtime_metadata": dict(state.metadata),
        }
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
    ) -> "NodeExecutionResult":
        """Apply the agent output protocol and return routing-ready payloads."""
        from ..results import NodeExecutionResult

        output_mode = self._node_output_mode(node)
        assistant_message = getattr(result, "assistant_message", None)
        expected_schema = node.metadata.get("output_schema") or node.metadata.get("expected_schema")
        parsed_output: Optional[Dict[str, Any]] = None
        if output_mode == "raw_text":
            parsed_output = None
        elif output_mode == "json_optional":
            parsed_output = self._parse_structured_agent_output(assistant_message, required=False)
        elif output_mode in {"json_required", "patch"}:
            parsed_output = self._parse_structured_agent_output(
                assistant_message,
                required=True,
                expected_schema=expected_schema or ("architecture_patch" if output_mode == "patch" else None),
            )
        elif output_mode == "tool_call_only":
            raw = str(assistant_message or "").strip()
            if raw and not raw.startswith("[External tool requests:"):
                raise OutputParseError(
                    "tool_call_only node returned plain assistant text.",
                    raw_output=raw,
                    parser_stage="agent_tool_call_only_output",
                    expected_schema="tool_calls",
                )
        else:
            parsed_output = self._parse_structured_agent_output(assistant_message, required=False)

        state_payload = self._raw_agent_payload(result)
        output_payload = result
        routing_payload = state_payload
        next_node_override = self._extract_next_node_id(state_payload)
        metadata_patch: Optional[Dict[str, Any]] = None
        control_patch: Optional[Dict[str, Any]] = None

        if parsed_output is not None:
            if output_mode == "patch":
                ArchitecturePatch.coerce(parsed_output.get("architecture_patch", parsed_output))
            output_payload = parsed_output
            routing_payload = parsed_output
            next_node_override = self._extract_next_node_id(parsed_output)

            # Split the output into metadata (node output) and control (routing).
            metadata_patch = self._extract_metadata_patch(parsed_output)
            control_patch = self._extract_control_patch(parsed_output)
            # Promote canonical report / verdict fields to root metadata so
            # downstream routing and final-output resolution can find them.
            self._preserve_report_fields(state, parsed_output, input_payload=input_payload)
            # state_payload is intentionally left as the raw assistant message
            # so that trace/events still show the raw output.
            state_payload = result.assistant_message if hasattr(result, "assistant_message") else parsed_output
        else:
            # Agent returned non-JSON (e.g. raw source code).
            # Use the raw assistant message as the output payload so downstream
            # tools/agents receive the actual content, not the result object.
            state_payload = self._raw_agent_payload(result)
            output_payload = state_payload
            routing_payload = state_payload

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
    ) -> "NodeExecutionResult":
        """Apply the tool output protocol and return routing-ready payloads."""
        from ..results import NodeExecutionResult

        state_payload = output_payload
        if isinstance(output_payload, dict):
            self._apply_metadata_updates(state.metadata, output_payload)
            self._preserve_report_fields(state, output_payload, input_payload=input_payload)
            final_payload = self._extract_final_report_payload(output_payload)
            # Preserve the full dict so downstream agents can read
            # e.g. tool-written file paths, byte counts, etc.
            state_payload = output_payload

        return NodeExecutionResult(
            output_payload=output_payload,
            routing_payload=output_payload,
            state_payload=state_payload,
            next_node_override=self._extract_next_node_id(output_payload),
            metadata_patch={},
            control_patch={},
        )

    # ------------------------------------------------------------------
    # Routing helpers
    # ------------------------------------------------------------------

    def _validate_next_targets(
        self,
        graph: ExecutionGraph,
        current_node: Any,
        next_targets: List[int],
    ) -> None:
        allowed_targets = {edge.to_node_id for edge in graph.outgoing_edges(current_node.node_id)}
        allowed_targets.update(current_node.next_node_ids)
        for next_node_id in next_targets:
            self._ensure_node_exists(
                graph,
                next_node_id,
                current_node_id=current_node.node_id,
                label="next_node_id",
            )
            if next_node_id in allowed_targets:
                continue
            if self._allows_dynamic_next_target(graph, current_node, next_node_id):
                continue
            raise ValueError(
                f"Node {current_node.node_id} resolved next_node_id {next_node_id}, "
                "but that target is not an allowed outgoing edge."
            )

    def _allows_dynamic_next_target(self, graph: ExecutionGraph, current_node: Any, next_node_id: int) -> bool:
        if not isinstance(current_node, ToolNode) or current_node.tool_name != "graph_editor":
            return False
        target = graph.nodes.get(next_node_id)
        metadata = getattr(target, "metadata", {}) if target is not None else {}
        return bool(isinstance(metadata, dict) and _node_is_transient(metadata))

    def _ensure_node_exists(
        self,
        graph: ExecutionGraph,
        node_id: int,
        *,
        current_node_id: int,
        label: str,
    ) -> None:
        if node_id not in graph.nodes:
            raise ValueError(
                f"Node {current_node_id} resolved {label} {node_id}, but that node does not exist."
            )

    def _resolve_next_targets(
        self,
        graph: ExecutionGraph,
        node: Any,
        payload: Any,
        next_node_override: Optional[int],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[int]:
        if next_node_override is not None:
            if next_node_override == node.node_id:
                next_node_override = None
            else:
                return [next_node_override]

        control = metadata.get("control") if isinstance(metadata, dict) else None
        if isinstance(control, dict):
            # Per-node control takes precedence; fall back to flat control for backward compatibility.
            node_control = control.get(str(node.node_id))
            effective_control = node_control if isinstance(node_control, dict) else control
            next_node_ids = effective_control.get("next_node_ids")
            if isinstance(next_node_ids, list) and next_node_ids:
                return [int(item) for item in next_node_ids]

            branch = effective_control.get("branch")
            if branch is not None:
                matched = self._match_branch_targets(graph, node.node_id, branch)
                if matched:
                    return matched

            branches = effective_control.get("branches")
            if isinstance(branches, list) and branches:
                resolved: List[int] = []
                for item in branches:
                    resolved.extend(self._match_branch_targets(graph, node.node_id, item))
                if resolved:
                    return list(dict.fromkeys(resolved))

        # Inspect payload dict for routing decisions.
        if isinstance(payload, dict):
            next_node_ids = payload.get("next_node_ids")
            if isinstance(next_node_ids, list) and next_node_ids:
                return [int(item) for item in next_node_ids]

            branch = payload.get("branch")
            if branch is not None:
                matched = self._match_branch_targets(graph, node.node_id, branch)
                if matched:
                    return matched

            branches = payload.get("branches")
            if isinstance(branches, list) and branches:
                resolved: List[int] = []
                for item in branches:
                    resolved.extend(self._match_branch_targets(graph, node.node_id, item))
                if resolved:
                    return list(dict.fromkeys(resolved))

        outgoing = graph.outgoing_edges(node.node_id)
        if outgoing:
            return [edge.to_node_id for edge in outgoing]
        return list(node.next_node_ids)

    def _match_branch_targets(
        self,
        graph: ExecutionGraph,
        node_id: int,
        branch_value: Any,
    ) -> List[int]:
        branch_label = str(branch_value).strip()
        if not branch_label:
            return []
        if branch_label.isdigit():
            return [int(branch_label)]

        matched = [
            edge.to_node_id
            for edge in graph.outgoing_edges(node_id)
            if edge.label == branch_label or edge.condition == branch_label
        ]
        return list(dict.fromkeys(matched))
