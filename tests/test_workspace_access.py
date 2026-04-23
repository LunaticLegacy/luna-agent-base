from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.swarm_loader import build_core_from_package
from core.swarm_spec import SwarmLoaderError, load_swarm_manifest
from core.toodefl import ToolContext
from tools.file_writer_tool import FileWriterTool


class WorkspaceAccessTest(unittest.TestCase):
    def test_workspace_config_loads_from_swarm_manifest(self) -> None:
        with patch.dict("os.environ", {"MOONSHOT_API_KEY": "test-key"}):
            _, manifest = load_swarm_manifest(Path("agents/docs_verifier"))
        self.assertEqual(manifest.workspace.default_mode, "workspace")
        self.assertEqual(manifest.workspace.default_root, ".")
        self.assertEqual(manifest.tool_capabilities["file_writer"], ["file_write"])

    def test_workspace_root_resolves_relative_to_package(self) -> None:
        with patch.dict("os.environ", {"MOONSHOT_API_KEY": "test-key"}):
            manifest_path, manifest = load_swarm_manifest(Path("agents/docs_verifier"))
            loaded = build_core_from_package(
                Path("agents/docs_verifier"),
                manifest=manifest,
                manifest_path=manifest_path,
            )
        self.assertEqual(loaded.core.workspace_root, Path("agents/docs_verifier").resolve())
        self.assertEqual(loaded.core.get_tool_capabilities("file_writer"), {"file_write"})

    def test_workspace_config_rejects_invalid_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            package_path = Path(tmp_dir)
            (package_path / "agents").mkdir()
            (package_path / "skills").mkdir()
            (package_path / "tools").mkdir()
            (package_path / "graph.py").write_text("GRAPH = None\n", encoding="utf-8")
            (package_path / "agents" / "agent.py").write_text(
                'AGENT = {"agent_id": "a"}\n',
                encoding="utf-8",
            )
            (package_path / "swarm.toml").write_text(
                """
[swarm]
name = "tmp"
graph_file = "graph.py"
agent_files = ["agents/agent.py"]

[llm.default]
name = "tmp"
provider = "openai"
api_url = "https://example.com"
api_key = "key"
model = "model"

[workspace]
default_mode = "invalid"
default_root = "."
""".strip(),
                encoding="utf-8",
            )
            with self.assertRaises(SwarmLoaderError):
                load_swarm_manifest(package_path)

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
                        capabilities={"file_write"},
                    ),
                )
            )
            self.assertTrue(target.exists())
            self.assertEqual(target.read_text(encoding="utf-8"), "workspace ok")
            self.assertEqual(result["written"], True)

    def test_file_writer_resolves_relative_paths_inside_workspace(self) -> None:
        tool = FileWriterTool()
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir)
            target = workspace_root / "nested" / "report.txt"
            result = asyncio.run(
                tool.execute(
                    {
                        "path": "nested/report.txt",
                        "content": "relative workspace ok",
                    },
                    context=ToolContext(
                        agent_id="reviewer",
                        workspace_mode="workspace",
                        workspace_root=workspace_root,
                        capabilities={"file_write"},
                    ),
                )
            )
            self.assertTrue(target.exists())
            self.assertEqual(target.read_text(encoding="utf-8"), "relative workspace ok")
            self.assertEqual(Path(result["path"]), target.resolve())

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
                            capabilities={"file_write"},
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
                        capabilities={"file_write"},
                    ),
                )
            )
            self.assertTrue(blocked_target.exists())
            self.assertEqual(blocked_target.read_text(encoding="utf-8"), "full access ok")
            self.assertEqual(result["written"], True)
            blocked_target.unlink()

    def test_file_writer_blocks_sensitive_paths_even_with_full_access(self) -> None:
        tool = FileWriterTool()
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir)
            sensitive_target = workspace_root / ".git" / "config"
            with self.assertRaises(ValueError):
                asyncio.run(
                    tool.execute(
                        {
                            "path": str(sensitive_target),
                            "content": "nope",
                        },
                        context=ToolContext(
                            agent_id="reviewer",
                            workspace_mode="full_access",
                            workspace_root=workspace_root,
                            capabilities={"file_write"},
                        ),
                    )
                )

    def test_file_writer_requires_config_write_for_config_files(self) -> None:
        tool = FileWriterTool()
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir)
            target = workspace_root / "config.toml"
            with self.assertRaises(ValueError):
                asyncio.run(
                    tool.execute(
                        {
                            "path": str(target),
                            "content": "blocked",
                        },
                        context=ToolContext(
                            agent_id="reviewer",
                            workspace_mode="workspace",
                            workspace_root=workspace_root,
                            capabilities={"file_write"},
                        ),
                    )
                )

            result = asyncio.run(
                tool.execute(
                    {
                        "path": str(target),
                        "content": "allowed",
                    },
                    context=ToolContext(
                        agent_id="reviewer",
                        workspace_mode="workspace",
                        workspace_root=workspace_root,
                        capabilities={"file_write", "config_write"},
                    ),
                )
            )
            self.assertTrue(result["written"])
            self.assertEqual(target.read_text(encoding="utf-8"), "allowed")

    def test_file_writer_requires_file_write_capability(self) -> None:
        tool = FileWriterTool()
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir)
            with self.assertRaises(PermissionError):
                asyncio.run(
                    tool.execute(
                        {
                            "path": "blocked.txt",
                            "content": "no capability",
                        },
                        context=ToolContext(
                            agent_id="reviewer",
                            workspace_mode="workspace",
                            workspace_root=workspace_root,
                        ),
                    )
                )


if __name__ == "__main__":
    unittest.main()
