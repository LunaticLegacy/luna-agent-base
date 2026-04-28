"""调试回显工具。

本模块提供 ``EchoTool``，用于将收到的参数原样返回，
方便在流水线中对工具调用链路进行快速冒烟测试与数据观察。

主要导出内容：
    - :class:`EchoTool`: 回显工具定义。
    - ``TOOL``: 模块级单例实例。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from core.toodefl import ToolContext, ToolDefinition


class EchoTool(ToolDefinition):
    """Return the received payload for debugging and wiring checks."""

    def __init__(self) -> None:
        super().__init__(tool_name="echo", description="Echo the input payload.")

    async def execute(
        self,
        arguments: Dict[str, Any],
        *,
        context: Optional[ToolContext] = None,
    ) -> Any:
        """回显输入参数并附加当前上下文摘要。

        Args:
            arguments: 需要回显的任意字典。
            context: 当前工具执行上下文。

        Returns:
            Dict[str, Any]: 包含 ``echo``（原始参数）和 ``context``（上下文摘要）的字典。
        """
        return {
            "echo": arguments,
            "context": {
                "agent_id": context.agent_id if context else None,
                "node_id": context.node_id if context else None,
                "rounds": context.rounds if context else None,
            },
        }


TOOL = EchoTool()
