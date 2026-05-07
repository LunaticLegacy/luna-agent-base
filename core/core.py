"""Top-level runtime organization layer.

Core manages **multiple** :class:`AgentSwarm` instances.
Each swarm is a self-contained runtime (graph + agents + tools + LLM backend);
Core acts as the registry, loader, and lifecycle manager.
"""

from __future__ import annotations

import os
import json
import importlib.util
import time
import tomllib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from modules.llm_fetcher import LLMBackendConfig, LLMFetcher
from modules.llm_fetcher.agent import Agent
from modules.llm_fetcher.swarm.execution_graph import (
    AgentNode,
    Edge,
    ExecutionGraph,
    ExecutionNode,
    InputNode,
    JoinNode,
    OutputNode,
    RouterNode,
    ToolNode,
)
from modules.llm_fetcher.swarm.swarm import AgentSwarm, SwarmSpec
from modules.llm_fetcher.thinking_graph import ThinkingGraph
from modules.llm_fetcher.tool import Tool, ToolRegistry


# ---------------------------------------------------------------------------
# Public aliases
# ---------------------------------------------------------------------------

Node = Any
GraphExecutionGraph = ExecutionGraph


# ---------------------------------------------------------------------------
# Supporting dataclasses
# ---------------------------------------------------------------------------

@dataclass
class GlobalVariablesConfig:
    """Simple global-variable container."""

    values: Dict[str, Any] = field(default_factory=dict)
    visibility: Dict[str, List[str]] = field(default_factory=dict)

    def visible_values_for_agent(self, agent_id: str) -> Dict[str, Any]:
        visible: Dict[str, Any] = {}
        for key, value in self.values.items():
            allowed = self.visibility.get(key)
            if allowed is None or agent_id in allowed:
                visible[key] = value
        return visible


@dataclass
class RuntimeChangeRecord:
    """A lightweight audit record for runtime changes."""

    action: str
    subject_kind: str
    subject_id: str
    detail: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentPackageRecord:
    """Snapshot of one discovered agent package."""

    package_name: str
    package_root: Path
    manifest_path: Path
    workspace_root: Path
    valid: bool
    reason: str = ""
    swarm_name: Optional[str] = None
    swarm: Optional[AgentSwarm] = None


# ---------------------------------------------------------------------------
# Core — multi-swarm manager
# ---------------------------------------------------------------------------

class Core:
    """Manage multiple :class:`AgentSwarm` instances.

    Core does not own agents, graphs, or tools directly;
    each swarm owns its own runtime objects.
    Core provides:

    * swarm registry (load / unload / list)
    * run history per swarm
    * lightweight global config / bookkeeping
    """

    def __init__(self) -> None:
        self.swarms: Dict[str, AgentSwarm] = {}
        self._history: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._global_variables = GlobalVariablesConfig()
        self._tool_capabilities: Dict[str, Set[str]] = {}
        self.valid_agent_packages: Dict[str, AgentPackageRecord] = {}
        self.invalid_agent_packages: Dict[str, AgentPackageRecord] = {}
        self.architecture_manager: Dict[str, Any] = {
            "runtime_changes": [],
        }

    # ------------------------------------------------------------------
    # Swarm lifecycle
    # ------------------------------------------------------------------

    def register_swarm(self, name: str, swarm: AgentSwarm) -> None:
        """Register an already-created swarm."""
        self.swarms[name] = swarm

    def create_swarm(
        self,
        name: str,
        llm_fetcher: LLMFetcher,
        spec: Optional[SwarmSpec] = None,
        max_concurrency: Optional[int] = None,
    ) -> AgentSwarm:
        """Create a fresh swarm and register it."""
        swarm = AgentSwarm(
            llm_fetcher=llm_fetcher,
            name=name,
            spec=spec,
            max_concurrency=max_concurrency,
        )
        self.swarms[name] = swarm
        return swarm

    def get_swarm(self, name: str) -> AgentSwarm:
        """Return a registered swarm by name."""
        if name not in self.swarms:
            raise KeyError(f"Swarm '{name}' is not registered.")
        return self.swarms[name]

    def remove_swarm(self, name: str) -> None:
        """Unload a swarm from the registry."""
        self.swarms.pop(name, None)
        self._history.pop(name, None)

    def list_swarms(self) -> List[Dict[str, Any]]:
        """Return metadata for all registered swarms."""
        return [
            {
                "name": name,
                "agent_count": len(swarm.agents),
                "tool_count": len(swarm.tool_registry._tools),
                "run_count": swarm._run_count,
            }
            for name, swarm in self.swarms.items()
        ]

    # ------------------------------------------------------------------
    # Loading helpers
    # ------------------------------------------------------------------

    def load_swarm_from_config(
        self,
        name: str,
        llm_fetcher: LLMFetcher,
        tools: Optional[List[Tool]] = None,
    ) -> AgentSwarm:
        """Create a minimal swarm from an LLM fetcher and optional tools."""
        swarm = self.create_swarm(name, llm_fetcher)
        if tools:
            for tool in tools:
                swarm.add_tool(tool)
        return swarm

    def discover_agent_package_roots(self, swarm_root: str | Path = "agents") -> List[Path]:
        """Return all package directories under ``swarm_root`` that contain ``swarm.toml``."""
        root = Path(swarm_root).expanduser().resolve()
        if not root.exists():
            return []
        packages: List[Path] = []
        for entry in sorted(root.iterdir()):
            if entry.is_dir() and (entry / "swarm.toml").is_file():
                packages.append(entry.resolve())
        return packages

    def initialize_agent_packages(self, swarm_root: str | Path = "agents") -> Dict[str, List[AgentPackageRecord]]:
        """Load every agent package found under ``swarm_root`` and classify it."""
        self.valid_agent_packages.clear()
        self.invalid_agent_packages.clear()
        for package_root in self.discover_agent_package_roots(swarm_root):
            record = self._inspect_agent_package(package_root)
            target = self.valid_agent_packages if record.valid else self.invalid_agent_packages
            target[record.package_name] = record
        return {
            "valid": list(self.valid_agent_packages.values()),
            "invalid": list(self.invalid_agent_packages.values()),
        }

    def load_swarm_from_source(self, source: str | Path) -> AgentPackageRecord:
        """Load one swarm package from a directory or ``swarm.toml`` file."""
        path = Path(source).expanduser().resolve()
        if path.is_dir():
            package_root = path
        elif path.is_file() and path.suffix == ".toml":
            package_root = path.parent
        else:
            raise ValueError(f"Unsupported swarm source: {source}")

        record = self._build_runtime_swarm_from_package(package_root)
        if not record.valid or record.swarm is None:
            raise ValueError(record.reason or f"Failed to load swarm package: {package_root}")
        return record

    def _inspect_agent_package(self, package_root: Path) -> AgentPackageRecord:
        manifest_path = package_root / "swarm.toml"
        workspace_root = (package_root / "workspace").resolve()
        workspace_root.mkdir(parents=True, exist_ok=True)
        swarm: Optional[AgentSwarm] = None

        try:
            with manifest_path.open("rb") as handle:
                manifest = tomllib.load(handle)
            swarm_block = manifest.get("swarm", {})
            package_name = str(swarm_block.get("name") or package_root.name)
            graph_file = str(swarm_block.get("graph_file") or "").strip()
            agent_files = swarm_block.get("agent_files", [])
            if not graph_file:
                raise ValueError("missing swarm.graph_file")
            if not isinstance(agent_files, list) or not agent_files:
                raise ValueError("missing swarm.agent_files")

            graph_path = package_root / graph_file
            if not graph_path.is_file():
                raise FileNotFoundError(f"Graph file not found: {graph_path}")

            for rel_path in agent_files:
                agent_path = (package_root / str(rel_path)).resolve()
                if not agent_path.is_file():
                    raise FileNotFoundError(f"Agent file not found: {agent_path}")

            fetcher = self._resolve_fetcher_from_manifest(manifest, fallback_name=package_name)
            if fetcher is None:
                raise ValueError("missing llm.default.api_url/model")

            swarm = self.create_swarm(package_name, llm_fetcher=fetcher)
            graph = self._load_package_execution_graph(package_root, graph_file, swarm)
            swarm.execution_graph = graph
            record = AgentPackageRecord(
                package_name=package_name,
                package_root=package_root,
                manifest_path=manifest_path,
                workspace_root=workspace_root,
                valid=True,
                swarm_name=package_name,
                swarm=swarm,
            )
            return record
        except Exception as exc:
            return AgentPackageRecord(
                package_name=package_root.name,
                package_root=package_root,
                manifest_path=manifest_path,
                workspace_root=workspace_root,
                valid=False,
                reason=str(exc),
            )

    def _build_runtime_swarm_from_package(self, package_root: Path) -> AgentPackageRecord:
        manifest_path = package_root / "swarm.toml"
        workspace_root = (package_root / "workspace").resolve()
        workspace_root.mkdir(parents=True, exist_ok=True)
        package_name = package_root.name
        swarm: Optional[AgentSwarm] = None

        try:
            with manifest_path.open("rb") as handle:
                manifest = tomllib.load(handle)
            swarm_block = manifest.get("swarm", {})
            package_name = str(swarm_block.get("name") or package_root.name)
            graph_file = str(swarm_block.get("graph_file") or "").strip()
            agent_files = swarm_block.get("agent_files", [])
            if not graph_file:
                raise ValueError("missing swarm.graph_file")
            if not isinstance(agent_files, list) or not agent_files:
                raise ValueError("missing swarm.agent_files")

            fetcher = self._resolve_fetcher_from_manifest(manifest, fallback_name=package_name)
            if fetcher is None:
                raise ValueError("missing llm.default.api_url/api_key/model")

            swarm = self.create_swarm(package_name, llm_fetcher=fetcher)
            graph = self._load_package_execution_graph(package_root, graph_file, swarm)
            swarm.execution_graph = graph

            globals_cfg = manifest.get("globals")
            if globals_cfg is not None:
                self.set_global_variables(globals_cfg)

            tool_caps = manifest.get("tool_capabilities", {})
            for tool_name, caps in tool_caps.items():
                if isinstance(caps, list):
                    self.set_tool_capabilities(tool_name, caps)

            record = AgentPackageRecord(
                package_name=package_name,
                package_root=package_root,
                manifest_path=manifest_path,
                workspace_root=workspace_root,
                valid=True,
                swarm_name=package_name,
                swarm=swarm,
            )
            self.register_swarm(package_name, swarm)
            return record
        except Exception as exc:
            if swarm is not None:
                self.swarms.pop(package_name, None)
            return AgentPackageRecord(
                package_name=package_root.name,
                package_root=package_root,
                manifest_path=manifest_path,
                workspace_root=workspace_root,
                valid=False,
                reason=str(exc),
            )

    def _load_package_execution_graph(
        self,
        package_root: Path,
        graph_file: str,
        swarm: AgentSwarm,
    ) -> ExecutionGraph:
        graph_path = package_root / graph_file
        if not graph_path.is_file():
            raise FileNotFoundError(f"Graph file not found: {graph_path}")

        spec = importlib.util.spec_from_file_location(
            f"_angelus_swarm_graph_{package_root.name}",
            graph_path,
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load graph file: {graph_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if not hasattr(module, "build_graph"):
            raise AttributeError(f"Graph file does not define build_graph(): {graph_path}")

        graph = module.build_graph(swarm)
        if graph is None:
            graph = getattr(swarm, "execution_graph", None)
        if not isinstance(graph, ExecutionGraph):
            raise TypeError(f"build_graph() did not return an ExecutionGraph for {package_root.name}")
        return graph

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def record_run(
        self,
        name: str,
        input_text: str,
        output: str,
        trace: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._history[name].append(
            {
                "timestamp": time.time(),
                "input": input_text,
                "output": output,
                "trace": trace,
            }
        )

    def get_history(self, name: str, limit: int = 20) -> List[Dict[str, Any]]:
        return self._history.get(name, [])[-limit:]

    # ------------------------------------------------------------------
    # Global variables
    # ------------------------------------------------------------------

    def set_global_variables(self, config: Any) -> None:
        if isinstance(config, GlobalVariablesConfig):
            self._global_variables = config
            return
        if isinstance(config, dict):
            values = dict(config.get("values") or config.get("globals") or config)
            visibility = dict(config.get("visibility") or {})
            self._global_variables = GlobalVariablesConfig(values=values, visibility=visibility)
            return
        values = dict(getattr(config, "values", {}) or getattr(config, "globals", {}) or {})
        visibility = dict(getattr(config, "visibility", {}) or {})
        self._global_variables = GlobalVariablesConfig(values=values, visibility=visibility)

    def get_global_variables_for_agent(self, agent_id: str) -> Dict[str, Any]:
        return self._global_variables.visible_values_for_agent(agent_id)

    # ------------------------------------------------------------------
    # Tool capabilities (global registry)
    # ------------------------------------------------------------------

    def set_tool_capabilities(self, tool_name: str, capabilities: List[str]) -> None:
        self._tool_capabilities[tool_name] = {str(cap).strip() for cap in capabilities if str(cap).strip()}

    def get_tool_capabilities(self, tool_name: str) -> Set[str]:
        return set(self._tool_capabilities.get(tool_name, []))

    # ------------------------------------------------------------------
    # Runtime bookkeeping
    # ------------------------------------------------------------------

    def record_runtime_change(self, **kwargs: Any) -> None:
        action = str(kwargs.get("action", "runtime_change"))
        subject_kind = str(kwargs.get("subject_kind", "unknown"))
        subject_id = str(kwargs.get("subject_id", ""))
        detail = dict(kwargs.get("detail", {}))
        self.architecture_manager["runtime_changes"].append(
            RuntimeChangeRecord(
                action=action,
                subject_kind=subject_kind,
                subject_id=subject_id,
                detail=detail,
            )
        )

    def get_cognitive_graph_export(
        self,
        swarm_name: str,
        query: Optional[str] = None,
        max_nodes: Optional[int] = None,
    ) -> str:
        swarm = self.get_swarm(swarm_name)
        data = swarm.thinking_graph.serialize()
        if query:
            query_lower = query.lower()
            nodes = {
                nid: node
                for nid, node in data["nodes"].items()
                if query_lower in json.dumps(node, ensure_ascii=False).lower()
            }
            data = dict(data)
            data["nodes"] = nodes
            data["node_count"] = len(nodes)
        if max_nodes is not None and max_nodes >= 0:
            node_items = list(data["nodes"].items())[:max_nodes]
            data = dict(data)
            data["nodes"] = dict(node_items)
            data["node_count"] = len(node_items)
        return json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)

    def get_thinking_graph_snapshot(self, name: str) -> Dict[str, Any]:
        swarm = self.get_swarm(name)
        return swarm.thinking_graph.serialize()

    def _resolve_fetcher_from_manifest(
        self,
        manifest: Dict[str, Any],
        *,
        fallback_name: str,
    ) -> Optional[LLMFetcher]:
        llm_block = manifest.get("llm", {}).get("default", {})
        if llm_block.get("api_url") and llm_block.get("model"):
            backend = LLMBackendConfig(
                name=str(llm_block.get("name") or fallback_name or "default"),
                provider=llm_block.get("provider", "openai"),
                api_url=llm_block["api_url"],
                api_key=self._resolve_api_key(llm_block.get("api_key", "")),
                model=llm_block.get("model", ""),
            )
            return LLMFetcher(backends=[backend])
        return None

    @staticmethod
    def _resolve_api_key(expr: str) -> str:
        if expr.startswith("${") and expr.endswith("}"):
            return os.environ.get(expr[2:-1], "")
        return expr

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_execution_graph_snapshot(self, name: str) -> Dict[str, Any]:
        swarm = self.get_swarm(name)
        graph = swarm.execution_graph
        nodes = graph.nodes
        edges = graph.edges
        from modules.llm_fetcher.swarm.execution_graph import AgentNode
        graph_kind = "agent" if any(isinstance(node, AgentNode) for node in nodes.values()) else "graph"
        return {
            "graph_name": name,
            "graph_kind": graph_kind,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "nodes": {
                nid: {
                    "type": getattr(node, "node_type", type(node).__name__),
                    "class": type(node).__name__,
                }
                for nid, node in nodes.items()
            },
            "edges": [
                {
                    "source": edge.source_id,
                    "target": edge.target_id,
                    "label": edge.label,
                }
                for edge in edges
            ],
        }

    def get_agent_graph_snapshot(self, name: str) -> Dict[str, Any]:
        """Compatibility alias for the execution graph snapshot."""
        return self.get_execution_graph_snapshot(name)

    def __repr__(self) -> str:
        return f"Core(swarms={len(self.swarms)})"


__all__ = [
    "Agent",
    "AgentNode",
    "AgentPackageRecord",
    "AgentSwarm",
    "Edge",
    "Core",
    "ExecutionGraph",
    "ExecutionNode",
    "GlobalVariablesConfig",
    "LLMBackendConfig",
    "LLMFetcher",
    "InputNode",
    "JoinNode",
    "RuntimeChangeRecord",
    "OutputNode",
    "RouterNode",
    "SwarmSpec",
    "ThinkingGraph",
    "Tool",
    "ToolRegistry",
    "ToolNode",
]
