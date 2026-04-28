from __future__ import annotations

import json
from typing import Any, Dict, Optional


class ToolContractError(RuntimeError):
    """Raised when runtime tools and graph/tool declarations are inconsistent."""

    failure_kind = "tool_contract_validation_failed"

    def __init__(self, report: Any, message: Optional[str] = None) -> None:
        self.report = report
        super().__init__(message or "tool_contract_validation_failed")


class RequiredToolFailedError(RuntimeError):
    """Raised when an external required tool request fails."""

    failure_kind = "required_tool_failed"

    def __init__(self, batch_result: Any, message: Optional[str] = None) -> None:
        self.batch_result = batch_result
        summary = getattr(batch_result, "summary", {}) or {}
        failed_tools = [
            getattr(result, "tool", None)
            for result in getattr(batch_result, "results", []) or []
            if getattr(result, "status", None) == "failed"
        ]
        self.tool_name = next((tool for tool in failed_tools if tool), None)
        self.failed_results = [
            {
                "request_id": getattr(result, "request_id", None),
                "tool": getattr(result, "tool", None),
                "status": getattr(result, "status", None),
                "error": getattr(result, "error", None),
                "output": getattr(result, "output", None),
            }
            for result in getattr(batch_result, "results", []) or []
            if getattr(result, "status", None) == "failed"
        ]
        detail = message or f"Required tool failed: {self.tool_name or json.dumps(summary, ensure_ascii=False)}"
        super().__init__(detail)

    def to_detail(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "tool_batch_summary": getattr(self.batch_result, "summary", {}),
            "failed_results": self.failed_results,
        }


class ToolPolicyDeniedError(PermissionError):
    """Raised when a tool rejects an unsafe or unsupported command shape."""

    failure_kind = "tool_policy_denied"

    def __init__(
        self,
        *,
        tool_name: str,
        command: str,
        reason: str,
        blocked_tokens: list[str],
        suggested_safe_calls: list[dict[str, Any]],
        message: Optional[str] = None,
    ) -> None:
        self.tool_name = tool_name
        self.command = command
        self.reason = reason
        self.blocked_tokens = list(blocked_tokens)
        self.suggested_safe_calls = list(suggested_safe_calls)
        super().__init__(
            message
            or f"{tool_name} policy denied command ({reason}): {command}"
        )

    def to_detail(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "command": self.command,
            "reason": self.reason,
            "blocked_tokens": list(self.blocked_tokens),
            "suggested_safe_calls": list(self.suggested_safe_calls),
        }


class OutputParseError(ValueError):
    """Raised when an agent output must be structured but cannot be parsed."""

    failure_kind = "output_parse_error"

    def __init__(
        self,
        message: str,
        *,
        raw_output: str,
        parser_stage: str,
        expected_schema: Optional[Any] = None,
        line: Optional[int] = None,
        column: Optional[int] = None,
        pos: Optional[int] = None,
    ) -> None:
        self.raw_output = raw_output
        self.parser_stage = parser_stage
        self.expected_schema = expected_schema
        self.line = line
        self.column = column
        self.pos = pos
        self.raw_output_prefix = raw_output[:500]
        self.raw_output_near_error = self._near_error(raw_output, pos)
        super().__init__(message)

    @staticmethod
    def _near_error(raw_output: str, pos: Optional[int]) -> str:
        if pos is None:
            return raw_output[:240]
        start = max(0, int(pos) - 120)
        end = min(len(raw_output), int(pos) + 120)
        return raw_output[start:end]

    def to_detail(self) -> Dict[str, Any]:
        return {
            "parser_stage": self.parser_stage,
            "expected_schema": self.expected_schema,
            "line": self.line,
            "column": self.column,
            "pos": self.pos,
            "raw_output_prefix": self.raw_output_prefix,
            "raw_output_near_error": self.raw_output_near_error,
        }


class ArchitecturePatchError(ValueError):
    """Raised when an architecture patch cannot be validated or applied."""

    failure_kind = "mutation_error"


class SchemaValidationError(ValueError):
    """Raised when lightweight runtime state schema validation fails."""

    failure_kind = "schema_validation_error"
