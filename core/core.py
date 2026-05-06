"""Top-level runtime organization layer.

This module acts as the public facade for the current Angelus runtime:

* it re-exports the graph / agent / tool primitives that existing examples
  already import from ``core``
* it provides a lightweight ``Core`` object that groups together agents,
  tools, execution graphs, thinking graphs, APIs, and runtime metadata
* it can assemble an :class:`~modules.llm_fetcher.swarm.swarm.AgentSwarm`
  from already-existing live objects via ``build_swarm`` / ``get_swarm``

The goal is to give the repo one stable organizational entry point without
forcing the rest of the codebase to know where the low-level pieces live.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from modules.llm_fetcher import (
    AgentFileIOManager,
    AgentFileLocations,
    AgentFileSnapshot,
    AgentWorkspacePolicy,
    LLMBackendConfig,
    LLMBackendError,
    LLMContext,
    LLMError,
    LLMFetcher,
    LLMTimeoutError,
)
from modules.llm_fetcher.agent import Agent
from modules.llm_fetcher.swarm.execution_graph import (
    AgentNode,
    Edge,
    ExecutionGraph,
    ExecutionNode,
    GraphContext,
    InputNode,
    JoinNode,
    OutputNode,
    RouterNode,
    ToolNode,
)
from modules.llm_fetcher.swarm.swarm import AgentSwarm, SwarmSpec
from modules.llm_fetcher.thinking_graph import ThinkingEdgeType, ThinkingGraph, ThinkingNodeType
from modules.llm_fetcher.tool import Tool, ToolRegistry
from modules.llm_fetcher.tools.execution_graph_tools import create_execution_graph_tools
from modules.llm_fetcher.tools.thinking_graph_tools import create_thinking_graph_tools


# ---------------------------------------------------------------------------
# Public aliases
# ---------------------------------------------------------------------------

Node = ExecutionNode
GraphExecutionGraph = ExecutionGraph


@dataclass
class GlobalVariablesConfig:
    """Simple global-variable container used by the runtime core."""

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
class ArchitectureManagerState:
    """Minimal architecture-management state kept by ``Core``."""

    rollback_records: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    runtime_changes: List[RuntimeChangeRecord] = field(default_factory=list)


class Core:
    """Organize the runtime system around agents, graphs, tools, and metadata."""

    def __init__(
        self,
        *,
        agent_name: str = "default",
        agent_config: Optional[Any] = None,
        llm_fetcher: Optional[LLMFetcher] = None,
        execution_graph: Optional[ExecutionGraph] = None,
        thinking_graph: Optional[ThinkingGraph] = None,
        tool_registry: Optional[ToolRegistry] = None,
        workspace_mode: str = "workspace",
        workspace_root: Optional[str | Path] = None,
        spec: Optional[SwarmSpec] = None,
        max_concurrency: Optional[int] = None,
    ) -> None:
        self.agent_name = agent_name
        self.agent_config = agent_config
        self._llm_fetcher = llm_fetcher
        self._spec = spec or SwarmSpec(name=agent_name)

        self.workspace_mode = workspace_mode
        self.workspace_root = Path(workspace_root).expanduser().resolve() if workspace_root else Path.cwd().resolve()
        self.current_run_id: Optional[str] = None

        self.execution_graph = execution_graph or ExecutionGraph(
            llm_fetcher=llm_fetcher,
            max_concurrency=max_concurrency,
        )
        self.thinking_graph = thinking_graph or ThinkingGraph()
        self.tool_registry = tool_registry or ToolRegistry()

        self.agents: Dict[str, Any] = {}
        self.agent_blueprints: Dict[str, Any] = {}
        self.tools: Dict[str, Tool] = {}
        self.apis: Dict[str, Any] = {}
        self._api_metadata: Dict[str, Dict[str, Any]] = {}
        self._tool_capabilities: Dict[str, Set[str]] = {}
        self._global_variables = GlobalVariablesConfig()
        self.architecture_policy: Dict[str, Any] = {
            "max_agents": None,
            "max_tools": None,
        }
        self.architecture_manager = ArchitectureManagerState()
        self.execution_graph_artifacts: Dict[str, Optional[Path]] = {
            "source_path": None,
            "backup_path": None,
        }
        self._swarm: Optional[AgentSwarm] = None

    # ------------------------------------------------------------------
    # Core assembly
    # ------------------------------------------------------------------

    def build_swarm(self) -> AgentSwarm:
        """Assemble a swarm from the currently attached live objects."""
        if self._llm_fetcher is None:
            raise RuntimeError("Cannot build a swarm without llm_fetcher.")

        self._swarm = AgentSwarm.from_existing(
            execution_graph=self.execution_graph,
            agents=self.agents,
            llm_fetcher=self._llm_fetcher,
            thinking_graph=self.thinking_graph,
            tool_registry=self.tool_registry,
            spec=self._spec,
            name=self.agent_name,
        )
        return self._swarm

    def get_swarm(self) -> AgentSwarm:
        """Return the current swarm, building it lazily if needed."""
        if self._swarm is None:
            return self.build_swarm()
        return self._swarm

    # ------------------------------------------------------------------
    # Agents
    # ------------------------------------------------------------------

    def add_agent(self, agent: Any) -> Any:
        """Register an already-created agent object."""
        agent_id = str(getattr(agent, "agent_id", getattr(agent, "name", ""))).strip()
        if not agent_id:
            raise ValueError("agent must expose a stable agent_id or name.")
        self.agents[agent_id] = agent
        self.agent_blueprints[agent_id] = agent
        self._swarm = None
        return agent

    def create_agent(
        self,
        *,
        agent_id: str,
        character_prompt: str,
        name: Optional[str] = None,
        workspace_mode: Optional[str] = None,
        workspace_root: Optional[str | Path] = None,
        tools: Optional[Sequence[Tool]] = None,
    ) -> Any:
        """Create a live agent using the configured LLM fetcher."""
        if self._llm_fetcher is None:
            raise RuntimeError("create_agent requires llm_fetcher.")

        agent = Agent(
            llm_handler=self._llm_fetcher,
            system_prompt=character_prompt,
            tools=list(tools) if tools else None,
        )
        agent.agent_id = agent_id
        agent.name = name or agent_id
        agent.workspace_mode = workspace_mode or self.workspace_mode
        agent.workspace_root = Path(workspace_root).expanduser().resolve() if workspace_root else self.workspace_root
        agent.tools = list(tools or [])
        return self.add_agent(agent)

    def destroy_agent(self, agent_id: str) -> None:
        self.agents.pop(agent_id, None)
        self.agent_blueprints.pop(agent_id, None)
        self._swarm = None

    def register_agent_blueprint(self, blueprint_ref: str, blueprint: Any) -> None:
        self.agent_blueprints[blueprint_ref] = blueprint

    def has_agent_blueprint(self, ref: str) -> bool:
        return ref in self.agent_blueprints

    def get_agent_blueprint(self, ref: str) -> Any:
        return self.agent_blueprints[ref]

    def acquire_agent_instance(self, ref: str, **kwargs: Any) -> Any:
        """Return a live agent instance for the given blueprint ref."""
        if ref in self.agents:
            return self.agents[ref]
        blueprint = self.get_agent_blueprint(ref)
        if callable(blueprint):
            agent = blueprint(**kwargs)
            self.add_agent(agent)
            return agent
        return blueprint

    def release_agent_instance(self, ref: str) -> None:
        """Release an acquired agent instance. Default implementation is a no-op."""
        return None

    # ------------------------------------------------------------------
    # Execution graph
    # ------------------------------------------------------------------

    def set_execution_graph(self, graph: ExecutionGraph) -> None:
        self.execution_graph = graph
        self._swarm = None

    def get_execution_graph(self) -> ExecutionGraph:
        return self.execution_graph

    def set_execution_graph_artifacts(
        self,
        *,
        source_path: Optional[str | Path] = None,
        backup_path: Optional[str | Path] = None,
    ) -> None:
        self.execution_graph_artifacts = {
            "source_path": Path(source_path).resolve() if source_path else None,
            "backup_path": Path(backup_path).resolve() if backup_path else None,
        }

    def get_agent_graph_snapshot(self) -> Dict[str, Any]:
        graph = self.execution_graph
        nodes = graph.nodes
        edges = graph.edges
        graph_kind = "agent" if any(isinstance(node, AgentNode) for node in nodes.values()) else "graph"
        return {
            "graph_name": self._spec.name,
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
            "artifacts": {
                key: str(value) if value is not None else None
                for key, value in self.execution_graph_artifacts.items()
            },
        }

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    def register_tool(self, tool: Tool, *, capabilities: Optional[Iterable[str]] = None) -> None:
        self.tools[tool.name] = tool
        self.tool_registry.register(tool)
        self.execution_graph.register_tool(tool)
        if capabilities is not None:
            self._tool_capabilities[tool.name] = {str(cap).strip() for cap in capabilities if str(cap).strip()}

    def add_tool(self, tool: Tool) -> None:
        self.register_tool(tool)

    def get_tool(self, tool_name: str) -> Tool:
        if tool_name in self.tools:
            return self.tools[tool_name]
        return self.tool_registry.get(tool_name)

    def get_tool_scheduler(self) -> Any:
        """Return the active tool scheduler if the runtime package provides one."""
        try:
            from .executor_parts.tool_scheduler import ToolScheduler  # type: ignore
        except Exception as exc:  # pragma: no cover - optional compatibility path
            raise RuntimeError("ToolScheduler subsystem is not available in this runtime core.") from exc
        return ToolScheduler(self)

    def get_tool_capabilities(self, tool_name: str) -> Set[str]:
        if tool_name in self._tool_capabilities:
            return set(self._tool_capabilities[tool_name])
        tool = self.tools.get(tool_name)
        if tool is None:
            try:
                tool = self.tool_registry.get(tool_name)
            except Exception:
                return set()
        caps = getattr(tool, "capabilities", None) or getattr(tool, "required_capabilities", None) or []
        return {str(cap).strip() for cap in caps if str(cap).strip()}

    def set_tool_capabilities(self, tool_name: str, capabilities: Iterable[str]) -> None:
        self._tool_capabilities[tool_name] = {str(cap).strip() for cap in capabilities if str(cap).strip()}

    # ------------------------------------------------------------------
    # APIs
    # ------------------------------------------------------------------

    def register_api(self, api_name: str, api: Any, *, origin: str = "package", source: Optional[str] = None) -> None:
        self.apis[api_name] = api
        self._api_metadata[api_name] = {
            "origin": origin,
            "source": source,
        }

    def get_api(self, api_name: str) -> Any:
        return self.apis[api_name]

    def get_api_metadata(self, api_name: str) -> Dict[str, Any]:
        return dict(self._api_metadata.get(api_name, {}))

    def list_apis(self, *, origin: Optional[str] = None) -> List[str]:
        if origin is None:
            return sorted(self.apis.keys())
        return sorted(
            name
            for name, meta in self._api_metadata.items()
            if meta.get("origin") == origin
        )

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

    def build_global_context_export(self, agent_id: str) -> str:
        return json.dumps(self.get_global_variables_for_agent(agent_id), ensure_ascii=False, sort_keys=True)

    # ------------------------------------------------------------------
    # Runtime bookkeeping
    # ------------------------------------------------------------------

    def merge_agent_cognitive_delta(self, *args: Any, **kwargs: Any) -> None:
        """Compatibility hook for systems that merge agent cognitive snapshots."""
        self.architecture_manager.runtime_changes.append(
            RuntimeChangeRecord(
                action="merge_agent_cognitive_delta",
                subject_kind="agent",
                subject_id=str(kwargs.get("agent_id", "")),
                detail={"args": args, "kwargs": kwargs},
            )
        )

    def get_cognitive_graph_export(self, query: Optional[str] = None, max_nodes: Optional[int] = None) -> str:
        data = self.thinking_graph.to_dict()
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

    def record_runtime_change(self, **kwargs: Any) -> None:
        action = str(kwargs.get("action", "runtime_change"))
        subject_kind = str(kwargs.get("subject_kind", "unknown"))
        subject_id = str(kwargs.get("subject_id", ""))
        detail = dict(kwargs.get("detail", {}))
        self.architecture_manager.runtime_changes.append(
            RuntimeChangeRecord(
                action=action,
                subject_kind=subject_kind,
                subject_id=subject_id,
                detail=detail,
            )
        )

    def cleanup_transient_execution_nodes(self, *, graph: Optional[ExecutionGraph] = None) -> List[str]:
        target_graph = graph or self.execution_graph
        removed: List[str] = []
        for node_id, node in list(target_graph.nodes.items()):
            metadata = getattr(node, "metadata", None)
            if isinstance(metadata, dict) and metadata.get("runtime_transient"):
                target_graph.remove_node(node_id)
                removed.append(node_id)
        return removed

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def init(self) -> None:
        """Perform lightweight initialization checks."""
        if self.execution_graph is None:
            raise RuntimeError("Core has no execution graph.")
        _ = self.execution_graph.nodes

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"Core(agent_name={self.agent_name!r}, "
            f"agents={len(self.agents)}, "
            f"tools={len(self.tools)}, "
            f"apis={len(self.apis)})"
        )


__all__ = [
    "Agent",
    "AgentFileIOManager",
    "AgentFileLocations",
    "AgentFileSnapshot",
    "AgentNode",
    "AgentSwarm",
    "AgentWorkspacePolicy",
    "ArchitectureManagerState",
    "Core",
    "Edge",
    "ExecutionGraph",
    "ExecutionNode",
    "GraphContext",
    "GraphExecutionGraph",
    "GlobalVariablesConfig",
    "InputNode",
    "JoinNode",
    "LLMBackendConfig",
    "LLMBackendError",
    "LLMContext",
    "LLMError",
    "LLMFetcher",
    "LLMTimeoutError",
    "Node",
    "OutputNode",
    "RouterNode",
    "SwarmSpec",
    "ThinkingEdgeType",
    "ThinkingGraph",
    "ThinkingNodeType",
    "Tool",
    "ToolNode",
    "ToolRegistry",
    "create_execution_graph_tools",
    "create_thinking_graph_tools",
]
