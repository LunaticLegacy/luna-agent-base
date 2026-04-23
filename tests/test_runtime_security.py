from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.swarm_spec import SwarmAppConfig, SwarmLoaderError, SwarmManifest
from core.swarm_loader import load_swarm_graph
from web.errors import NotFoundError
from web.runtime import RuntimeRegistry


class RuntimeSecurityTest(unittest.TestCase):
    def test_resolve_package_path_rejects_existing_directory_outside_swarm_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "agents"
            root.mkdir()
            outside = Path(tmp_dir) / "outside"
            outside.mkdir()
            registry = RuntimeRegistry(
                config_path=Path(tmp_dir) / "config.toml",
                root_config=SwarmAppConfig(swarm_root=root),
            )

            with self.assertRaises(NotFoundError):
                registry.resolve_package_path(outside)

    def test_graph_file_cannot_escape_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            package = Path(tmp_dir) / "swarm"
            package.mkdir()
            manifest = SwarmManifest(
                swarm_name="bad",
                graph_file="../graph.py",
                agent_files=["agents/a.py"],
            )

            with self.assertRaises(SwarmLoaderError):
                load_swarm_graph(package, manifest, core=object())


if __name__ == "__main__":
    unittest.main()
