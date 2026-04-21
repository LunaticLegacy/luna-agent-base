from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from core.toodefl import ToolContext, ToolDefinition


class FileWriterTool(ToolDefinition):
    """Write text content to a file path."""

    def __init__(self) -> None:
        super().__init__(tool_name="file_writer", description="Write text to a file.")

    async def execute(
        self,
        arguments: Dict[str, Any],
        *,
        context: Optional[ToolContext] = None,
    ) -> Any:
        path_value = str(arguments.get("path", "")).strip()
        if not path_value:
            raise ValueError("file_writer requires a non-empty 'path'.")
        target_path = Path(path_value)
        content = str(arguments.get("content", ""))
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")
        return {
            "written": True,
            "path": str(target_path),
            "bytes": len(content.encode("utf-8")),
            "context": {
                "agent_id": context.agent_id if context else None,
                "node_id": context.node_id if context else None,
                "rounds": context.rounds if context else None,
            },
        }


TOOL = FileWriterTool()
