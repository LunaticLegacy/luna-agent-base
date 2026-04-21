from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from modules.llm_fetcher import LLMFetcher

from .agent import Agent
from .cognitive import CognitiveGraph, merge_cognitive_graphs
from .config import AgentConfig
from .runtime_info import RuntimeInfoManager
from .toodefl import ToolDefinition
from .skills import SkillAsset
from .protocols import AgentLike
from .results import GraphValidationResult

if TYPE_CHECKING:
    from .policy import ExecutionGraph


class Core:
    """Runtime container for agents, tools, and execution graphs."""

    def __init__(
        self,
        agent_name: str,
        agent_config: AgentConfig,
    ) -> None:
        self.agent_name = agent_name
        self.agent_config = agent_config
        self.agents: Dict[str, AgentLike] = {}
        self.tools: Dict[str, ToolDefinition] = {}
        self.skills: Dict[str, SkillAsset] = {}
        self._execution_graph: Optional["ExecutionGraph"] = None
        self._runtime_info: Optional[RuntimeInfoManager] = None
        self.swarm_cognitive_graph = CognitiveGraph(graph_id=f"swarm_{agent_name}")

    async def init(self) -> None:
        """Initialize runtime resources and validate the current graph."""
        if self._execution_graph is not None:
            self.check_execution_graph_complete()

    def set_runtime_info_dir(self, runtime_dir: Path) -> None:
        """Attach a runtime info recorder for live state persistence."""
        self._runtime_info = RuntimeInfoManager(runtime_dir=runtime_dir, agent_name=self.agent_name)
        self._record_runtime_change(
            action="runtime_info_initialized",
            subject_kind="runtime",
            subject_id=self.agent_name,
            detail={"runtime_dir": str(runtime_dir)},
        )

    def create_agent(
        self,
        agent_id: str,
        character_prompt: str,
        *,
        name: Optional[str] = None,
        llm_handler: Optional[LLMFetcher] = None,
        tools: Optional[List[Any]] = None,
        cognitive_graph: Optional[CognitiveGraph] = None,
    ) -> Agent:
        """Create a new managed agent and register it immediately."""
        handler = llm_handler or LLMFetcher(
            api_url=self.agent_config.api_url,
            api_key=self.agent_config.api_key,
            model=self.agent_config.model,
            provider=self.agent_config.provider,
        )
        agent = Agent(
            agent_id=agent_id,
            llm_handler=handler,
            character_prompt=character_prompt,
            name=name,
            tools=tools,
            core=self,
            max_tool_rounds=5,
            cognitive_graph=cognitive_graph,
        )
        self.add_agent(agent)
        return agent

    def add_agent(self, agent: AgentLike) -> None:
        """Register a managed or external agent."""
        if agent.agent_id in self.agents:
            raise ValueError(f"Duplicate agent_id: {agent.agent_id}")
        self.agents[agent.agent_id] = agent
        self._record_runtime_change(
            action="add_agent",
            subject_kind="agent",
            subject_id=agent.agent_id,
            detail={
                "name": getattr(agent, "name", agent.agent_id),
            },
        )

    def remove_agent(self, agent_id: str) -> None:
        """Remove an agent from the runtime registry."""
        agent = self.agents.pop(agent_id, None)
        if agent is not None:
            agent.reset_context()
            self._record_runtime_change(
                action="remove_agent",
                subject_kind="agent",
                subject_id=agent_id,
                detail={"name": getattr(agent, "name", agent_id)},
            )

    def destroy_agent(self, agent_id: str) -> None:
        """Alias for method `remove_agent`."""
        self.remove_agent(agent_id)

    def get_agent(self, agent_id: str) -> AgentLike:
        """Fetch a registered agent by id."""
        try:
            return self.agents[agent_id]
        except KeyError as exc:
            raise KeyError(f"Unknown agent_id: {agent_id}") from exc

    def list_agents(self) -> List[AgentLike]:
        """Return the registered agents in insertion order."""
        return list(self.agents.values())

    def register_tool(self, tool: ToolDefinition) -> None:
        """Register a runtime tool."""
        tool.validate()
        if tool.tool_name in self.tools:
            raise ValueError(f"Duplicate tool_name: {tool.tool_name}")
        self.tools[tool.tool_name] = tool
        self._record_runtime_change(
            action="register_tool",
            subject_kind="tool",
            subject_id=tool.tool_name,
            detail={"description": getattr(tool, "description", "")},
        )

    def register_skill(self, skill: SkillAsset) -> None:
        """Register a runtime skill asset."""
        if skill.name in self.skills:
            raise ValueError(f"Duplicate skill name: {skill.name}")
        self.skills[skill.name] = skill
        self._record_runtime_change(
            action="register_skill",
            subject_kind="skill",
            subject_id=skill.name,
            detail={"path": str(skill.path)},
        )

    def get_skill(self, skill_name: str) -> SkillAsset:
        """Fetch a registered skill by name."""
        try:
            return self.skills[skill_name]
        except KeyError as exc:
            raise KeyError(f"Unknown skill_name: {skill_name}") from exc

    def list_skills(self) -> List[SkillAsset]:
        """Return the registered skills in insertion order."""
        return list(self.skills.values())

    def remove_tool(self, tool_name: str) -> None:
        """Remove a tool from the runtime registry."""
        removed = self.tools.pop(tool_name, None)
        if removed is not None:
            self._record_runtime_change(
                action="remove_tool",
                subject_kind="tool",
                subject_id=tool_name,
                detail={"description": getattr(removed, "description", "")},
            )

    def get_tool(self, tool_name: str) -> ToolDefinition:
        """Fetch a registered tool by name."""
        try:
            return self.tools[tool_name]
        except KeyError as exc:
            raise KeyError(f"Unknown tool_name: {tool_name}") from exc

    def set_execution_graph(self, graph: "ExecutionGraph") -> None:
        """Attach the current execution graph."""
        self._execution_graph = graph
        self._record_runtime_change(
            action="set_execution_graph",
            subject_kind="graph",
            subject_id=getattr(graph, "graph_name", None),
            detail={
                "entry_node_id": getattr(graph, "entry_node_id", None),
                "exit_node_id": getattr(graph, "exit_node_id", None),
            },
        )

    def get_execution_graph(self) -> Optional["ExecutionGraph"]:
        """Return the current execution graph."""
        return self._execution_graph

    def check_execution_graph_available(self) -> GraphValidationResult:
        """Check whether a graph exists and is usable."""
        if self._execution_graph is None:
            return GraphValidationResult(
                is_valid=False,
                errors=["Execution graph is not attached."],
            )
        return self._execution_graph.validate(self)

    def check_execution_graph_complete(self) -> GraphValidationResult:
        """Check whether the graph is structurally complete."""
        if self._execution_graph is None:
            return GraphValidationResult(
                is_valid=False,
                errors=["Execution graph is not attached."],
            )
        return self._execution_graph.validate(self)

    def _record_runtime_change(
        self,
        *,
        action: str,
        subject_kind: str,
        subject_id: Optional[str] = None,
        detail: Optional[Dict[str, Any]] = None,
    ) -> None:
        if self._runtime_info is None:
            return
        self._runtime_info.record(
            action=action,
            subject_kind=subject_kind,
            subject_id=subject_id,
            detail=detail,
            core=self,
        )

    def record_runtime_change(
        self,
        *,
        action: str,
        subject_kind: str,
        subject_id: Optional[str] = None,
        detail: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a runtime mutation into the package runtime-info directory."""
        self._record_runtime_change(
            action=action,
            subject_kind=subject_kind,
            subject_id=subject_id,
            detail=detail,
        )

    def merge_agent_cognitive_graph(self, agent_id: str) -> None:
        """Merge an agent's private cognitive graph into the swarm shared graph."""
        agent = self.agents.get(agent_id)
        if agent is None:
            return
        agent_cg = getattr(agent, "cognitive_graph", None)
        if agent_cg is None or not isinstance(agent_cg, CognitiveGraph):
            return
        merge_cognitive_graphs(self.swarm_cognitive_graph, agent_cg)

    def get_cognitive_graph_export(self, query: Optional[str] = None, max_nodes: int = 20) -> str:
        """Return a human-readable export of the swarm cognitive graph for LLM prompting."""
        return self.swarm_cognitive_graph.export_for_llm(query=query, max_nodes=max_nodes)

    def get_cognitive_graph_snapshot(self) -> Dict[str, Any]:
        """Return a JSON-serializable snapshot of the swarm cognitive graph."""
        return self.swarm_cognitive_graph.snapshot()
