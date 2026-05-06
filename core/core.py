"""Top-level runtime organization layer.

Core manages **multiple** :class:`AgentSwarm` instances.
Each swarm is a self-contained runtime (graph + agents + tools + LLM backend);
Core acts as the registry, loader, and lifecycle manager.
"""

from __future__ import annotations

import json
import time
import tomllib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from modules.llm_fetcher import LLMBackendConfig, LLMFetcher
from modules.llm_fetcher.agent import Agent
from modules.llm_fetcher.swarm.execution_graph import ExecutionGraph
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
        data = swarm.thinking_graph.to_dict()
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

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_agent_graph_snapshot(self, name: str) -> Dict[str, Any]:
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

    def __repr__(self) -> str:
        return f"Core(swarms={len(self.swarms)})"


__all__ = [
    "Agent",
    "AgentSwarm",
    "Core",
    "ExecutionGraph",
    "GlobalVariablesConfig",
    "LLMBackendConfig",
    "LLMFetcher",
    "RuntimeChangeRecord",
    "SwarmSpec",
    "ThinkingGraph",
    "Tool",
    "ToolRegistry",
]
