"""运行时注册表，管理已加载的 swarm 包与后台运行实例。

RuntimeRegistry 是 Angelus Web 层的核心状态容器，生命周期与
FastAPI 应用状态绑定，提供 swarm 的发现、加载、卸载、重载以及
运行注册表（RunRegistry）的聚合访问。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from core.swarm_loader import LoadedSwarm, SwarmLoaderError, build_core_from_package, load_all_swarms
from core.swarm_spec import SwarmAppConfig, discover_swarm_packages, load_root_config, load_swarm_manifest
from web.errors import ConflictError, NotFoundError
from web.runs import RunRegistry


@dataclass
class RuntimeRegistry:
    """已加载 swarm 与活跃运行的可变注册表。

    Attributes:
        config_path: 根配置文件路径。
        root_config: 解析后的 SwarmAppConfig，可能为 None（加载失败时）。
        swarms: 以 swarm_name 为键的已加载 swarm 字典。
        runs: 后台运行注册表，负责 launch / stop / snapshot。
        load_error: 最近一次全量加载的错误信息，成功时为 None。
    """

    config_path: Path
    root_config: Optional[SwarmAppConfig]
    swarms: Dict[str, LoadedSwarm] = field(default_factory=dict)
    runs: RunRegistry = field(default_factory=RunRegistry)
    load_error: Optional[str] = None

    @classmethod
    def from_config_path(cls, config_path: Path) -> "RuntimeRegistry":
        """从配置文件路径构建注册表并尝试加载全部 swarm。

        Args:
            config_path: 根配置文件（如 config.toml）路径。

        Returns:
            初始化后的 RuntimeRegistry，若加载失败则 load_error 被置位。
        """
        root_config = load_root_config(config_path)
        registry = cls(config_path=Path(config_path), root_config=root_config)
        try:
            registry.reload_all()
        except SwarmLoaderError as exc:
            # 加载失败不抛异常，允许应用在降级模式下启动
            registry.load_error = str(exc)
        return registry

    def reload_all(self) -> None:
        """从磁盘重新加载所有已发现的 swarm 包。

        成功加载的 swarm 会被更新或新增；加载失败的 swarm 保持原有状态，
        不会被移除，避免运行时可用性骤降。

        Raises:
            SwarmLoaderError: 根配置不可用时抛出。
        """
        if self.root_config is None:
            raise SwarmLoaderError("Root config is not available.")
        swarms = load_all_swarms(self.root_config.swarm_root)
        for swarm in swarms:
            self.swarms[swarm.manifest.swarm_name] = swarm
        self.load_error = None

    def list_swarms(self) -> Dict[str, LoadedSwarm]:
        """返回已加载 swarm 的副本。

        Returns:
            swarm 字典的浅拷贝。
        """
        return dict(self.swarms)

    def get_swarm(self, swarm_name: str) -> LoadedSwarm:
        """根据名称获取已加载的 swarm。

        Args:
            swarm_name: 目标 swarm 名称。

        Returns:
            LoadedSwarm 实例。

        Raises:
            NotFoundError: 指定 swarm 未加载时抛出。
        """
        try:
            return self.swarms[swarm_name]
        except KeyError as exc:
            raise NotFoundError(f"Unknown swarm: {swarm_name}") from exc

    def load_swarm(self, source: str | Path, *, replace: bool = False) -> LoadedSwarm:
        """加载单个 swarm 包到注册表。

        Args:
            source: swarm 包路径或名称。
            replace: 是否允许覆盖已存在的同名 swarm。

        Returns:
            加载后的 LoadedSwarm 实例。

        Raises:
            ConflictError: 该 swarm 已存在且 replace=False 时抛出。
            NotFoundError: 无法解析 source 时抛出。
        """
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
        self.load_error = None
        return loaded

    def unload_swarm(self, swarm_name: str, *, force: bool = False) -> LoadedSwarm:
        """从注册表中卸载指定 swarm。

        Args:
            swarm_name: 要卸载的 swarm 名称。
            force: 是否强制卸载，即使存在活跃运行。

        Returns:
            被卸载的 LoadedSwarm 实例。

        Raises:
            NotFoundError: swarm 不存在时抛出。
            ConflictError: 存在活跃运行且 force=False 时抛出。
        """
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
        """原子地重载单个 swarm。

        若提供 source，则使用新路径进行重载；否则使用当前 swarm 的
        package_path。

        Args:
            swarm_name: 要重载的 swarm 名称。
            force: 是否强制重载，即使存在活跃运行。
            source: 可选的新包路径或名称。

        Returns:
            重载后的 LoadedSwarm 实例。

        Raises:
            NotFoundError: swarm 不存在，或 source 解析失败时抛出。
            ConflictError: 存在活跃运行且 force=False，或重载后名称不匹配时抛出。
        """
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
        self.load_error = None
        return loaded

    def resolve_package_path(self, source: str | Path) -> Path:
        """将 swarm 名称或路径解析为绝对包路径。

        解析优先级：
        1. 若 source 为现有目录，直接校验并返回。
        2. 尝试在 swarm_root 下拼接 source 作为子目录。
        3. 遍历 swarm_root 下所有 swarm 包，匹配 swarm_name 或目录名。

        Args:
            source: 目录路径或 swarm 名称。

        Returns:
            绝对路径的 swarm 包目录。

        Raises:
            SwarmLoaderError: 根配置不可用时抛出。
            NotFoundError: 无法解析到有效 swarm 包时抛出。
        """
        if self.root_config is None:
            raise SwarmLoaderError("Root config is not available.")
        candidate = Path(source)
        swarm_root = self.root_config.swarm_root.resolve()
        # 优先处理直接传入的目录路径
        if candidate.exists() and candidate.is_dir():
            resolved_candidate = candidate.resolve()
            if not self._path_is_within_root(resolved_candidate, swarm_root):
                raise NotFoundError(f"Swarm package must be inside swarm_root: {source}")
            return resolved_candidate

        # 其次尝试在 swarm_root 下查找子目录
        direct = (swarm_root / candidate).resolve()
        if direct.exists() and direct.is_dir():
            if not self._path_is_within_root(direct, swarm_root):
                raise NotFoundError(f"Swarm package must be inside swarm_root: {source}")
            return direct

        # 最后全盘扫描 swarm_root，按名称匹配
        for package_path in discover_swarm_packages(swarm_root):
            try:
                _, manifest = load_swarm_manifest(package_path)
            except SwarmLoaderError:
                continue
            if manifest.swarm_name == str(source) or package_path.name == str(source):
                return package_path

        raise NotFoundError(f"Unable to resolve swarm package: {source}")

    def _path_is_within_root(self, path: Path, root: Path) -> bool:
        """判断 path 是否位于 root 目录树内（含 root 自身）。

        Args:
            path: 待检查路径。
            root: 基准根目录。

        Returns:
            True 表示 path 在 root 内部或等于 root；否则 False。
        """
        try:
            path.relative_to(root)
        except ValueError:
            return False
        return True
