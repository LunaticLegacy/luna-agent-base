from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
import tomllib

from core import AgentConfig, Core
from modules.llm_fetcher import LLMFetcher


DEFAULT_CONFIG_PATH = Path("config.toml")


@dataclass
class AgentSpec:
    """Agent definition loaded from config.toml."""

    agent_id: str
    character_prompt: str
    name: Optional[str] = None
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    provider: str = "openai"


@dataclass
class AppSpec:
    """Top-level application configuration."""

    agent_name: str
    agent_config: AgentConfig
    agents: List[AgentSpec]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Angelus runtime bootstrapper")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to the config.toml file.",
    )
    return parser.parse_args()


def load_toml_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _load_agent_specs(raw_agents: Any) -> List[AgentSpec]:
    if not raw_agents:
        return []
    if not isinstance(raw_agents, list):
        raise ValueError("`agents` must be an array of tables in config.toml.")

    specs: List[AgentSpec] = []
    for index, item in enumerate(raw_agents):
        if not isinstance(item, dict):
            raise ValueError(f"Agent definition at index {index} must be a table.")
        agent_id = str(item.get("agent_id", "")).strip()
        character_prompt = str(item.get("character_prompt", "")).strip()
        if not agent_id:
            raise ValueError(f"Agent definition at index {index} is missing `agent_id`.")
        if not character_prompt:
            raise ValueError(
                f"Agent definition at index {index} is missing `character_prompt`."
            )
        specs.append(
            AgentSpec(
                agent_id=agent_id,
                character_prompt=character_prompt,
                name=item.get("name"),
                api_url=item.get("api_url"),
                api_key=item.get("api_key"),
                model=item.get("model"),
                provider=str(item.get("provider", "openai")),
            )
        )
    return specs


def load_app_spec(path: Path) -> AppSpec:
    raw_config = load_toml_config(path)

    core_section = raw_config.get("core", {})
    if not isinstance(core_section, dict):
        raise ValueError("[core] must be a TOML table.")

    agent_section = raw_config.get("agent", {})
    if not isinstance(agent_section, dict):
        raise ValueError("[agent] must be a TOML table.")

    agent_config = AgentConfig(
        api_url=str(
            core_section.get("api_url")
            or agent_section.get("api_url")
            or ""
        ),
        api_key=str(
            core_section.get("api_key")
            or agent_section.get("api_key")
            or ""
        ),
        model=(
            core_section.get("model")
            or agent_section.get("model")
            or None
        ),
        provider=str(
            core_section.get("provider")
            or agent_section.get("provider")
            or "openai"
        ),
    )

    agent_name = str(core_section.get("agent_name", "angelus")).strip() or "angelus"
    agents = _load_agent_specs(raw_config.get("agents"))
    return AppSpec(agent_name=agent_name, agent_config=agent_config, agents=agents)


def _resolve_agent_backend(spec: AgentSpec, fallback: AgentConfig) -> AgentConfig:
    return AgentConfig(
        api_url=str(spec.api_url or fallback.api_url or ""),
        api_key=str(spec.api_key or fallback.api_key or ""),
        model=spec.model or fallback.model,
        provider=str(spec.provider or fallback.provider or "openai"),
    )


async def bootstrap_app(config_path: Path) -> Core:
    app_spec = load_app_spec(config_path)
    core = Core(agent_name=app_spec.agent_name, agent_config=app_spec.agent_config)

    for agent_spec in app_spec.agents:
        backend = _resolve_agent_backend(agent_spec, app_spec.agent_config)
        if not backend.api_key or not backend.model:
            print(
                f"[skip] Agent '{agent_spec.agent_id}' has no usable backend config; "
                "it was not created."
            )
            continue
        core.create_agent(
            agent_id=agent_spec.agent_id,
            character_prompt=agent_spec.character_prompt,
            name=agent_spec.name,
            llm_handler=LLMFetcher(
                api_url=backend.api_url,
                api_key=backend.api_key,
                model=backend.model,
                provider=backend.provider,
            ),
        )

    await core.init()
    return core


async def main() -> None:
    """Application entry point."""
    args = parse_args()
    core = await bootstrap_app(args.config)

    validation = core.check_execution_graph_available()
    print(f"runtime: {core.agent_name}")
    print(f"agents: {len(core.list_agents())}")
    print(f"graph_attached: {core.get_execution_graph() is not None}")
    if not validation.is_valid:
        print(f"graph_status: invalid ({'; '.join(validation.errors)})")
    else:
        print("graph_status: valid")


if __name__ == "__main__":
    asyncio.run(main())
