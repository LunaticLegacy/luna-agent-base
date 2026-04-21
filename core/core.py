from __future__ import annotations

from typing import Dict, List, Optional, TYPE_CHECKING

from modules.llm_fetcher import LLMFetcher

from .agent import Agent
from .config import AgentConfig
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

    async def init(self) -> None:
        """Initialize runtime resources and validate the current graph."""
        if self._execution_graph is not None:
            self.check_execution_graph_complete()

    def create_agent(
        self,
        agent_id: str,
        character_prompt: str,
        *,
        name: Optional[str] = None,
        llm_handler: Optional[LLMFetcher] = None,
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
        )
        self.add_agent(agent)
        return agent

    def add_agent(self, agent: AgentLike) -> None:
        """Register a managed or external agent."""
        if agent.agent_id in self.agents:
            raise ValueError(f"Duplicate agent_id: {agent.agent_id}")
        self.agents[agent.agent_id] = agent

    def remove_agent(self, agent_id: str) -> None:
        """Remove an agent from the runtime registry."""
        agent = self.agents.pop(agent_id, None)
        if agent is not None:
            agent.reset_context()

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

    def register_skill(self, skill: SkillAsset) -> None:
        """Register a runtime skill asset."""
        if skill.name in self.skills:
            raise ValueError(f"Duplicate skill name: {skill.name}")
        self.skills[skill.name] = skill

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
        self.tools.pop(tool_name, None)

    def get_tool(self, tool_name: str) -> ToolDefinition:
        """Fetch a registered tool by name."""
        try:
            return self.tools[tool_name]
        except KeyError as exc:
            raise KeyError(f"Unknown tool_name: {tool_name}") from exc

    def set_execution_graph(self, graph: "ExecutionGraph") -> None:
        """Attach the current execution graph."""
        self._execution_graph = graph

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
