from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from modules.llm_fetcher import LLMFetcher

from ..agent import Agent
from ..cognitive import CognitiveGraph
from ..protocols import AgentLike
from ..skills import SkillAsset
from ..toodefl import ToolDefinition, normalize_capabilities


class AgentInstancePool:
    """Resolve agent blueprints into runtime instances."""

    def __init__(self, core: Any) -> None:
        self.core = core
        self._quarantined: Set[str] = set()
        self._active_counts: Dict[str, int] = {}

    def acquire(self, blueprint_ref: str, *, instance_policy: str = "singleton", parallel_context: bool = False) -> AgentLike:
        if blueprint_ref in self._quarantined:
            raise RuntimeError(f"Agent blueprint '{blueprint_ref}' is quarantined.")
        normalized_policy = str(instance_policy or "singleton").strip().lower() or "singleton"
        self._active_counts[blueprint_ref] = self._active_counts.get(blueprint_ref, 0) + 1
        if normalized_policy == "singleton" and not parallel_context:
            return self.core.get_agent_blueprint(blueprint_ref)

        if normalized_policy not in ("singleton", "per_call"):
            raise ValueError(f"Unsupported agent instance policy: {instance_policy}")

        prototype = self.core.get_agent_blueprint(blueprint_ref)
        clone_for_runtime = getattr(prototype, "clone_for_runtime", None)
        if not callable(clone_for_runtime):
            return prototype
        instance = clone_for_runtime()
        set_run_id = getattr(instance, "set_run_id", None)
        if callable(set_run_id):
            set_run_id(self.core.current_run_id)
        return instance

    def release(self, blueprint_ref: str) -> None:
        if blueprint_ref not in self._active_counts:
            return
        remaining = max(0, int(self._active_counts.get(blueprint_ref, 0)) - 1)
        if remaining == 0:
            self._active_counts.pop(blueprint_ref, None)
            return
        self._active_counts[blueprint_ref] = remaining

    def quarantine(self, blueprint_ref: str) -> None:
        if blueprint_ref:
            self._quarantined.add(blueprint_ref)

    def restore(self, blueprint_ref: str) -> None:
        self._quarantined.discard(blueprint_ref)

    async def drain(self, blueprint_ref: str, timeout: float = 5.0) -> Dict[str, Any]:
        deadline = asyncio.get_running_loop().time() + max(0.0, float(timeout))
        while self._active_counts.get(blueprint_ref, 0) > 0:
            if asyncio.get_running_loop().time() >= deadline:
                return {
                    "blueprint_ref": blueprint_ref,
                    "drained": False,
                    "active_count": self._active_counts.get(blueprint_ref, 0),
                }
            await asyncio.sleep(0.01)
        return {
            "blueprint_ref": blueprint_ref,
            "drained": True,
            "active_count": 0,
        }


class RuntimeRegistryMixin:
    """Agent, tool, and skill registry helpers for a runtime core."""

    def register_agent_blueprint(self, blueprint_ref: str, agent: AgentLike) -> None:
        self.agent_blueprints[blueprint_ref] = agent

    def has_agent_blueprint(self, blueprint_ref: str) -> bool:
        return blueprint_ref in self.agent_blueprints or blueprint_ref in self.agents

    def get_agent_blueprint(self, blueprint_ref: str) -> AgentLike:
        if blueprint_ref in self.agent_blueprints:
            return self.agent_blueprints[blueprint_ref]
        return self.get_agent(blueprint_ref)

    def create_agent(
        self,
        agent_id: str,
        character_prompt: str,
        *,
        name: Optional[str] = None,
        llm_handler: Optional[LLMFetcher] = None,
        tools: Optional[List[Any]] = None,
        cognitive_graph: Optional[CognitiveGraph] = None,
        workspace_mode: str = "workspace",
        workspace_root: Optional[Path] = None,
        tool_execution_mode: str = "internal",
    ) -> Agent:
        handler = llm_handler or LLMFetcher(
            api_url=self.agent_config.api_url,
            api_key=self.agent_config.api_key,
            model=self.agent_config.model,
            provider=self.agent_config.provider,
            limiter=self.limiter,
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
            workspace_mode=workspace_mode,
            workspace_root=workspace_root if workspace_root is not None else self.workspace_root,
            swarm_name=self.agent_name,
            tool_execution_mode=tool_execution_mode,
        )
        agent.set_run_id(self.current_run_id)
        self.add_agent(agent)
        self.register_agent_blueprint(agent_id, agent)
        return agent

    def add_agent(self, agent: AgentLike) -> None:
        if agent.agent_id in self.agents:
            raise ValueError(f"Duplicate agent_id: {agent.agent_id}")
        self.agents[agent.agent_id] = agent
        self._record_runtime_change(
            action="add_agent",
            subject_kind="agent",
            subject_id=agent.agent_id,
            detail={"name": getattr(agent, "name", agent.agent_id)},
        )

    def remove_agent(self, agent_id: str) -> None:
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
        self.remove_agent(agent_id)

    def get_agent(self, agent_id: str) -> AgentLike:
        try:
            return self.agents[agent_id]
        except KeyError as exc:
            raise KeyError(f"Unknown agent_id: {agent_id}") from exc

    def acquire_agent_instance(
        self,
        blueprint_ref: str,
        *,
        instance_policy: str = "singleton",
        parallel_context: bool = False,
    ) -> AgentLike:
        return self.agent_instance_pool.acquire(
            blueprint_ref,
            instance_policy=instance_policy,
            parallel_context=parallel_context,
        )

    def release_agent_instance(self, blueprint_ref: str) -> None:
        self.agent_instance_pool.release(blueprint_ref)

    def list_agents(self) -> List[AgentLike]:
        return list(self.agents.values())

    def register_tool(self, tool: ToolDefinition) -> None:
        tool.validate()
        if tool.tool_name in self.tools:
            raise ValueError(f"Duplicate tool_name: {tool.tool_name}")
        self.tools[tool.tool_name] = tool
        self.tool_capabilities.setdefault(tool.tool_name, set())
        self._record_runtime_change(
            action="register_tool",
            subject_kind="tool",
            subject_id=tool.tool_name,
            detail={"description": getattr(tool, "description", "")},
        )

    def set_tool_capabilities(self, tool_name: str, capabilities: Iterable[str]) -> None:
        self.tool_capabilities[tool_name] = normalize_capabilities(capabilities)

    def get_tool_capabilities(self, tool_name: str) -> Set[str]:
        return set(self.tool_capabilities.get(tool_name, set()))

    def remove_tool(self, tool_name: str) -> None:
        removed = self.tools.pop(tool_name, None)
        if removed is not None:
            self._record_runtime_change(
                action="remove_tool",
                subject_kind="tool",
                subject_id=tool_name,
                detail={"description": getattr(removed, "description", "")},
            )

    def get_tool(self, tool_name: str) -> ToolDefinition:
        try:
            return self.tools[tool_name]
        except KeyError as exc:
            raise KeyError(f"Unknown tool_name: {tool_name}") from exc

    def register_api(
        self,
        api_name: str,
        api: Any,
        *,
        origin: str = "package",
        source: Optional[str] = None,
    ) -> None:
        normalized_name = str(api_name).strip()
        if not normalized_name:
            raise ValueError("api_name must not be empty.")
        if normalized_name in self.apis:
            raise ValueError(f"Duplicate api_name: {normalized_name}")
        normalized_origin = str(origin or "package").strip().lower() or "package"
        self.apis[normalized_name] = api
        self.api_sources[normalized_name] = {
            "origin": normalized_origin,
            "source": source,
        }
        self._record_runtime_change(
            action="register_api",
            subject_kind="api",
            subject_id=normalized_name,
            detail={
                "origin": normalized_origin,
                "source": source,
                "type": api.__class__.__name__,
            },
        )

    def get_api(self, api_name: str) -> Any:
        try:
            return self.apis[api_name]
        except KeyError as exc:
            raise KeyError(f"Unknown api_name: {api_name}") from exc

    def get_api_metadata(self, api_name: str) -> Dict[str, Any]:
        if api_name not in self.api_sources:
            raise KeyError(f"Unknown api_name: {api_name}")
        return dict(self.api_sources[api_name])

    def list_apis(self, *, origin: Optional[str] = None) -> List[Any]:
        if origin is None:
            return list(self.apis.values())
        normalized_origin = str(origin).strip().lower()
        return [
            api
            for name, api in self.apis.items()
            if str(self.api_sources.get(name, {}).get("origin", "")).strip().lower() == normalized_origin
        ]

    def remove_api(self, api_name: str) -> None:
        removed = self.apis.pop(api_name, None)
        metadata = self.api_sources.pop(api_name, None)
        if removed is not None or metadata is not None:
            self._record_runtime_change(
                action="remove_api",
                subject_kind="api",
                subject_id=api_name,
                detail=metadata or {},
            )

    def register_skill(self, skill: SkillAsset) -> None:
        canonical = f"{self.agent_name}/{skill.name}"
        if canonical in self.skills:
            raise ValueError(f"Duplicate skill name: {canonical}")
        self.skills[canonical] = skill
        if skill.name in self.skills and self.skills[skill.name].name != skill.name:
            pass
        else:
            self.skills[skill.name] = skill
        self._record_runtime_change(
            action="register_skill",
            subject_kind="skill",
            subject_id=canonical,
            detail={"path": str(skill.path), "alias": skill.name},
        )

    def get_skill(self, skill_name: str) -> SkillAsset:
        if skill_name in self.skills:
            return self.skills[skill_name]
        canonical = f"{self.agent_name}/{skill_name}"
        if canonical in self.skills:
            return self.skills[canonical]
        raise KeyError(f"Unknown skill_name: {skill_name} (also tried {canonical})")

    def list_skills(self) -> List[SkillAsset]:
        return list(self.skills.values())
