from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from core.swarm_loader import LoadedSwarm, SwarmLoaderError, build_core_from_package, load_all_swarms
from core.swarm_spec import SwarmAppConfig, discover_swarm_packages, load_root_config, load_swarm_manifest
from core.task_graph import TaskGraph
from web.errors import ConflictError, NotFoundError
from web.runs import RunRegistry


@dataclass
class RuntimeRegistry:
    """Mutable registry for loaded swarms and live runs."""

    config_path: Path
    root_config: Optional[SwarmAppConfig]
    swarms: Dict[str, LoadedSwarm] = field(default_factory=dict)
    runs: RunRegistry = field(default_factory=RunRegistry)
    load_error: Optional[str] = None

    @classmethod
    def from_config_path(cls, config_path: Path) -> "RuntimeRegistry":
        root_config = load_root_config(config_path)
        registry = cls(config_path=Path(config_path), root_config=root_config)
        try:
            registry.reload_all()
        except SwarmLoaderError as exc:
            registry.load_error = str(exc)
        return registry

    def _task_graph_path(self, swarm_name: str) -> Path:
        return self.config_path.parent / "data" / f"tasks_{swarm_name}.json"

    def _load_task_graph(self, swarm: LoadedSwarm) -> None:
        path = self._task_graph_path(swarm.manifest.swarm_name)
        task_graph = TaskGraph.load(path)
        task_graph.graph_id = f"tasks_{swarm.manifest.swarm_name}"
        swarm.core.set_task_graph(task_graph, persist_path=path)

    def _save_task_graph(self, swarm_name: str) -> None:
        swarm = self.swarms.get(swarm_name)
        if swarm and swarm.core.task_graph is not None:
            swarm.core.task_graph.save(self._task_graph_path(swarm_name))

    def reload_all(self) -> None:
        """Reload every discovered swarm package from disk."""
        if self.root_config is None:
            raise SwarmLoaderError("Root config is not available.")
        swarms = load_all_swarms(self.root_config.swarm_root)
        self.swarms = {swarm.manifest.swarm_name: swarm for swarm in swarms}
        for swarm in self.swarms.values():
            self._load_task_graph(swarm)
        self.load_error = None

    def list_swarms(self) -> Dict[str, LoadedSwarm]:
        """Return the loaded swarm registry."""
        return dict(self.swarms)

    def get_swarm(self, swarm_name: str) -> LoadedSwarm:
        try:
            return self.swarms[swarm_name]
        except KeyError as exc:
            raise NotFoundError(f"Unknown swarm: {swarm_name}") from exc

    def load_swarm(self, source: str | Path, *, replace: bool = False) -> LoadedSwarm:
        """Load one swarm package into the registry."""
        package_path = self.resolve_package_path(source)
        manifest_path, manifest = load_swarm_manifest(package_path)
        existing = self.swarms.get(manifest.swarm_name)
        if existing is not None and not replace:
            raise ConflictError(f"Swarm '{manifest.swarm_name}' is already loaded.")

        loaded = build_core_from_package(
            package_path,
            manifest=manifest,
            manifest_path=manifest_path,
        )
        self.swarms[manifest.swarm_name] = loaded
        self._load_task_graph(loaded)
        self.load_error = None
        return loaded

    def unload_swarm(self, swarm_name: str, *, force: bool = False) -> LoadedSwarm:
        """Remove one swarm from the registry."""
        swarm = self.get_swarm(swarm_name)
        if self.runs.active_run_count(swarm_name) > 0 and not force:
            raise ConflictError(
                f"Swarm '{swarm_name}' still has active runs; use force=true to unload it."
            )
        del self.swarms[swarm_name]
        return swarm

    def reload_swarm(
        self,
        swarm_name: str,
        *,
        force: bool = False,
        source: str | Path | None = None,
    ) -> LoadedSwarm:
        """Reload one swarm atomically."""
        current = self.get_swarm(swarm_name)
        if self.runs.active_run_count(swarm_name) > 0 and not force:
            raise ConflictError(
                f"Swarm '{swarm_name}' still has active runs; use force=true to reload it."
            )

        package_path = self.resolve_package_path(source or current.package_path)
        manifest_path, manifest = load_swarm_manifest(package_path)
        if manifest.swarm_name != swarm_name:
            raise ConflictError(
                f"Reload source '{package_path}' resolves to swarm '{manifest.swarm_name}', "
                f"not '{swarm_name}'."
            )
        loaded = build_core_from_package(
            package_path,
            manifest=manifest,
            manifest_path=manifest_path,
        )
        self.swarms[manifest.swarm_name] = loaded
        self._load_task_graph(loaded)
        self.load_error = None
        return loaded

    def resolve_package_path(self, source: str | Path) -> Path:
        """Resolve a swarm package path from a directory or swarm name."""
        if self.root_config is None:
            raise SwarmLoaderError("Root config is not available.")
        candidate = Path(source)
        swarm_root = self.root_config.swarm_root.resolve()
        if candidate.exists() and candidate.is_dir():
            resolved_candidate = candidate.resolve()
            if not self._path_is_within_root(resolved_candidate, swarm_root):
                raise NotFoundError(f"Swarm package must be inside swarm_root: {source}")
            return resolved_candidate

        direct = (swarm_root / candidate).resolve()
        if direct.exists() and direct.is_dir():
            if not self._path_is_within_root(direct, swarm_root):
                raise NotFoundError(f"Swarm package must be inside swarm_root: {source}")
            return direct

        for package_path in discover_swarm_packages(swarm_root):
            try:
                _, manifest = load_swarm_manifest(package_path)
            except SwarmLoaderError:
                continue
            if manifest.swarm_name == str(source) or package_path.name == str(source):
                return package_path

        raise NotFoundError(f"Unable to resolve swarm package: {source}")

    def _path_is_within_root(self, path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
        except ValueError:
            return False
        return True
