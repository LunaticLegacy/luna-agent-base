from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from core.swarm_spec import SwarmLoaderError, _coerce_agent_blueprint
from core.toodefl import ToolContext
from tools.file_writer_tool import FileWriterTool


class WorkspaceAccessTest(unittest.TestCase):
    def test_agent_blueprint_parses_workspace_fields(self) -> None:
        blueprint = _coerce_agent_blueprint(
            {
                "agent_id": "reviewer",
                "workspace_mode": "workspace",
                "workspace_root": "agents/docs_verifier",
            },
            Path("agents/docs_verifier/agents/reviewer.py"),
        )
        self.assertEqual(blueprint.workspace_mode, "workspace")
        self.assertEqual(blueprint.workspace_root, "agents/docs_verifier")

    def test_agent_blueprint_rejects_invalid_workspace_mode(self) -> None:
        with self.assertRaises(SwarmLoaderError):
            _coerce_agent_blueprint(
                {
                    "agent_id": "reviewer",
                    "workspace_mode": "invalid",
                },
                Path("agents/docs_verifier/agents/reviewer.py"),
            )

    def test_file_writer_allows_workspace_writes(self) -> None:
        tool = FileWriterTool()
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir)
            target = workspace_root / "nested" / "report.txt"
            result = asyncio.run(
                tool.execute(
                    {
                        "path": str(target),
                        "content": "workspace ok",
                    },
                    context=ToolContext(
                        agent_id="reviewer",
                        workspace_mode="workspace",
                        workspace_root=workspace_root,
                    ),
                )
            )
            self.assertTrue(target.exists())
            self.assertEqual(target.read_text(encoding="utf-8"), "workspace ok")
            self.assertEqual(result["written"], True)

    def test_file_writer_blocks_outside_workspace(self) -> None:
        tool = FileWriterTool()
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir)
            blocked_target = workspace_root.parent / "blocked.txt"
            with self.assertRaises(ValueError):
                asyncio.run(
                    tool.execute(
                        {
                            "path": str(blocked_target),
                            "content": "should fail",
                        },
                        context=ToolContext(
                            agent_id="reviewer",
                            workspace_mode="workspace",
                            workspace_root=workspace_root,
                        ),
                    )
                )

    def test_file_writer_allows_full_access_writes(self) -> None:
        tool = FileWriterTool()
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir)
            blocked_target = workspace_root.parent / "full_access_ok.txt"
            if blocked_target.exists():
                blocked_target.unlink()
            result = asyncio.run(
                tool.execute(
                    {
                        "path": str(blocked_target),
                        "content": "full access ok",
                    },
                    context=ToolContext(
                        agent_id="reviewer",
                        workspace_mode="full_access",
                        workspace_root=workspace_root,
                    ),
                )
            )
            self.assertTrue(blocked_target.exists())
            self.assertEqual(blocked_target.read_text(encoding="utf-8"), "full access ok")
            self.assertEqual(result["written"], True)
            blocked_target.unlink()


if __name__ == "__main__":
    unittest.main()
