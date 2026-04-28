from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from core.toodefl import ToolContext, ToolDefinition


class OutputRepairTool(ToolDefinition):
    """Best-effort repair for malformed structured agent outputs."""

    def __init__(self) -> None:
        super().__init__(
            tool_name="output_repair",
            description="Repair malformed JSON-like structured output without executing privileged actions.",
            schema={
                "type": "object",
                "properties": {
                    "raw_output": {"type": "string"},
                    "expected_mode": {"type": "string"},
                    "expected_schema": {"type": "object"},
                },
                "required": ["raw_output"],
            },
        )

    async def execute(self, arguments: Dict[str, Any], *, context: Optional[ToolContext] = None) -> Any:
        raw_output = str(arguments.get("raw_output") or "")
        candidate = self._strip_fence(raw_output)
        candidate = self._extract_first_object(candidate)
        candidate = self._remove_trailing_commas(candidate)
        try:
            repaired = json.loads(candidate)
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "repaired_text": candidate[:1000],
            }
        if not isinstance(repaired, dict):
            return {
                "success": False,
                "error": "Repaired output is not a JSON object.",
                "repaired_text": candidate[:1000],
            }
        return {
            "success": True,
            "repaired": repaired,
            "repaired_text": json.dumps(repaired, ensure_ascii=False),
        }

    def _strip_fence(self, text: str) -> str:
        stripped = text.strip()
        if not stripped.startswith("```"):
            return stripped
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()

    def _extract_first_object(self, text: str) -> str:
        start = text.find("{")
        if start < 0:
            return text
        depth = 0
        in_string = False
        escape = False
        for index, char in enumerate(text[start:], start=start):
            if escape:
                escape = False
                continue
            if char == "\\":
                escape = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start:index + 1]
        return text[start:]

    def _remove_trailing_commas(self, text: str) -> str:
        return re.sub(r",\s*([}\]])", r"\1", text)


TOOL = OutputRepairTool()
