from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from ..agent import Agent
from ..config import AgentConfig
from ..core import Core
from ..policy import ExecutionGraph
from ..skills import SkillAsset
from .utils import (
    _backend_to_agent_config,
    _build_llm_handler,
    _merge_backends,
    _resolve_agent_prompt,
    _resolve_workspace_defaults,
    _resolve_workspace_for_agent,
    _resolve_workspace_path,
    _resolve_package_local_path,
    _load_module_from_entry,
    collect_tool_requirement_files,
    install_tool_requirements,
    load_swarm_tools,
    _resolve_module_path,
)
from ..swarm_spec import (
    AgentBlueprint,
    SwarmLoaderError,
    SwarmManifest,
    discover_swarm_packages,
    load_agent_blueprints,
    load_root_config,
    load_skill_assets,
    load_swarm_manifest,
)
from ..toodefl import ToolDefinition


@dataclass
class LoadedSwarm:
    """A fully loaded swarm package with a runtime core."""

    package_path: Path
    manifest_path: Path
    manifest: SwarmManifest
    core: Core
    skills: Dict[str, SkillAsset] = field(default_factory=dict)
    tools: Dict[str, ToolDefinition] = field(default_factory=dict)
    tool_requirement_files: List[Path] = field(default_factory=list)


def load_swarm_graph(package_path: Path, manifest: SwarmManifest, core: Core) -> ExecutionGraph:
    """Load the single execution graph file for a swarm package."""
    graph_path = _resolve_package_local_path(package_path, manifest.graph_file)
    backup_path = graph_path.with_name("graph_init.py")
    print(
        f"[angelus] loading graph: swarm={manifest.swarm_name} file={manifest.graph_file}",
        flush=True,
    )
    module = _load_module_from_entry(manifest.graph_file, package_path)
    if hasattr(module, "build_graph"):
        graph = module.build_graph(core)
    elif hasattr(module, "GRAPH"):
        graph = module.GRAPH
    else:
        raise SwarmLoaderError(
            f"Graph file '{manifest.graph_file}' must expose build_graph(core) or GRAPH."
        )

    if not isinstance(graph, ExecutionGraph):
        raise SwarmLoaderError(
            f"Graph file '{manifest.graph_file}' must return an ExecutionGraph instance."
        )

    core.set_execution_graph_artifacts(source_path=graph_path, backup_path=backup_path)
    core.ensure_execution_graph_backup()

    validation = graph.validate(core)
    if validation.is_valid:
        print(
            f"[angelus] graph ready: swarm={manifest.swarm_name} nodes={len(graph.nodes)} "
            f"edges={len(graph.edges)} entry={graph.entry_node_id} exit={graph.exit_node_id}",
            flush=True,
        )
    else:
        print(
            f"[angelus] graph invalid: swarm={manifest.swarm_name} errors={validation.errors}",
            flush=True,
        )
    if validation.warnings:
        print(
            f"[angelus] graph warnings: swarm={manifest.swarm_name} warnings={validation.warnings}",
            flush=True,
        )

    return graph


def build_core_from_package(
    package_path: Path,
    *,
    manifest: Optional[SwarmManifest] = None,
    manifest_path: Optional[Path] = None,
) -> LoadedSwarm:
    """Build a runtime core from one swarm package."""
    if manifest is None or manifest_path is None:
        manifest_path, manifest = load_swarm_manifest(package_path)

    assert manifest is not None
    assert manifest_path is not None

    print(
        f"[angelus] loading swarm package: name={manifest.swarm_name} "
        f"package={package_path} manifest={manifest_path}",
        flush=True,
    )

    blueprints = load_agent_blueprints(package_path, manifest)
    skills = load_skill_assets(package_path, manifest)
    skill_by_name = {skill.name: skill for skill in skills}
    skill_by_path = {skill.path.resolve(): skill for skill in skills}

    print(
        f"[angelus] loaded assets: swarm={manifest.swarm_name} "
        f"agents={len(blueprints)} skills={len(skills)} tools_declared={len(manifest.tool_files)}",
        flush=True,
    )

    default_config = manifest.default_llm or _backend_to_agent_config(manifest.llm_backends[0])
    default_workspace_mode, default_workspace_root = _resolve_workspace_defaults(package_path, manifest)
    core = Core(
        agent_name=manifest.swarm_name,
        agent_config=AgentConfig(
            api_url=default_config.api_url,
            api_key=default_config.api_key,
            model=default_config.model,
            provider=default_config.provider,
        ),
        workspace_root=default_workspace_root,
    )
    core.workspace_mode = default_workspace_mode
    core.set_runtime_info_dir(package_path / "runtime_info")

    for skill in skills:
        core.register_skill(skill)
        print(
            f"[angelus] registered skill: swarm={manifest.swarm_name} skill={skill.name}",
            flush=True,
        )

    package_backends = _merge_backends(manifest)
    if manifest.default_backend is not None and manifest.default_backend not in {
        backend.name for backend in package_backends
    }:
        raise SwarmLoaderError(
            f"Manifest default_backend '{manifest.default_backend}' does not match any declared LLM backend."
        )

    tools, tool_requirement_files = load_swarm_tools(package_path, manifest)
    for tool in tools.values():
        core.register_tool(tool)
        core.set_tool_capabilities(tool.tool_name, manifest.tool_capabilities.get(tool.tool_name, []))
        print(
            f"[angelus] registered tool: swarm={manifest.swarm_name} tool={tool.tool_name}",
            flush=True,
        )

    for blueprint in blueprints:
        prompt = _resolve_agent_prompt(
            blueprint,
            package_path=package_path,
            skill_by_name=skill_by_name,
            skill_by_path=skill_by_path,
        )
        llm_handler = _build_llm_handler(blueprint, package_backends, manifest.default_backend)
        workspace_mode, workspace_root = _resolve_workspace_for_agent(package_path, manifest, blueprint)

        agent_tools = []
        for tool_name in blueprint.tools:
            if tool_name in core.tools:
                agent_tools.append(core.tools[tool_name])
            else:
                print(
                    f"[angelus] warning: agent '{blueprint.agent_id}' references unknown tool '{tool_name}'",
                    flush=True,
                )

        core.create_agent(
            agent_id=blueprint.agent_id,
            character_prompt=prompt,
            name=blueprint.name,
            llm_handler=llm_handler,
            tools=agent_tools if agent_tools else None,
            workspace_mode=workspace_mode,
            workspace_root=workspace_root,
        )
        print(
            f"[angelus] loaded agent: swarm={manifest.swarm_name} agent={blueprint.agent_id}"
            + (f" backend={blueprint.backend_name}" if blueprint.backend_name else ""),
            flush=True,
        )

    graph = load_swarm_graph(package_path, manifest, core)
    core.set_execution_graph(graph)
    print(
        f"[angelus] swarm loaded: name={manifest.swarm_name} agents={len(core.agents)} "
        f"skills={len(core.skills)} tools={len(core.tools)}",
        flush=True,
    )
    return LoadedSwarm(
        package_path=package_path,
        manifest_path=manifest_path,
        manifest=manifest,
        core=core,
        skills={skill.name: skill for skill in skills},
        tools=tools,
        tool_requirement_files=tool_requirement_files,
    )


def load_all_swarms(root: Path, *, preinstall_tool_requirements: bool = False) -> List[LoadedSwarm]:
    """Discover and load every swarm package in the given root."""
    package_paths = discover_swarm_packages(root)
    print(
        f"[angelus] discovered swarm packages: root={root} count={len(package_paths)}",
        flush=True,
    )
    manifest_entries = [load_swarm_manifest(package_path) for package_path in package_paths]

    if preinstall_tool_requirements:
        requirements = collect_tool_requirement_files(package_paths, manifest_entries)
        if requirements:
            print(
                f"[angelus] preinstalling tool requirements: files={len(requirements)}",
                flush=True,
            )
        install_tool_requirements(requirements)

    swarms: List[LoadedSwarm] = []
    for package_path, (manifest_path, manifest) in zip(package_paths, manifest_entries):
        swarms.append(
            build_core_from_package(
                package_path,
                manifest=manifest,
                manifest_path=manifest_path,
            )
        )
    print(
        f"[angelus] swarm loading complete: loaded={len(swarms)}",
        flush=True,
    )
    return swarms


def _load_module_from_entry(entry: str, package_path: Path):
    from .utils import _load_module_from_entry as load

    return load(entry, package_path)
