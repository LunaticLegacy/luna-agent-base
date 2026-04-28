"""Agent 结构化输出修复工具。

本模块提供 ``OutputRepairTool``，用于对模型生成的、不符合 JSON 规范的
结构化输出进行最佳-effort 修复。修复策略包括去除 Markdown 代码围栏、
提取首个 JSON 对象、去除尾部逗号等。

主要导出内容：
    - :class:`OutputRepairTool`: 输出修复工具定义。
    - ``TOOL``: 模块级单例实例。
"""

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
        """尝试修复原始输出并返回结构化结果。

        依次执行：去除代码围栏 → 提取首个 JSON 对象 → 去除尾部逗号 → json.loads。
        若仍失败则返回包含错误信息的友好结构。

        Args:
            arguments: 工具入参，需包含 ``raw_output``。
            context: 工具执行上下文（当前未使用）。

        Returns:
            Dict[str, Any]: 修复成功时返回 ``{"success": True, "repaired": ..., "repaired_text": ...}``；
            失败时返回 ``{"success": False, "error": ..., "repaired_text": ...}``。
        """
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
        """去除 Markdown 代码围栏（``` ... ```）。

        若文本不以 ``` 开头则原样返回。

        Args:
            text: 原始文本。

        Returns:
            去除围栏后的文本。
        """
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
        """从文本中提取首个完整的 JSON 对象（按括号深度匹配）。

        采用状态机方式跟踪字符串逃逸与大括号深度，避免被嵌套结构误导。

        Args:
            text: 可能包含多个对象或杂项内容的文本。

        Returns:
            提取出的 JSON 对象字符串；若未找到 `{` 则返回原样。
        """
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
        """去除 JSON 对象或数组中尾部多余的逗号。

        这是模型输出中最常见的语法错误之一，正则替换即可快速修复。

        Args:
            text: 待清理的 JSON 文本。

        Returns:
            清理后的文本。
        """
        return re.sub(r",\s*([}\]])", r"\1", text)


TOOL = OutputRepairTool()
