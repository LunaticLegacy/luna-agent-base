from __future__ import annotations

import importlib
import importlib.util
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from modules.llm_fetcher import LLMBackendConfig, LLMFetcher

from .config import AgentConfig
from .core import Core
from .policy import ExecutionGraph
from .skills import SkillAsset, load_skill_asset
from .swarm_spec import (
    AgentBlueprint,
    SwarmLoaderError,
    SwarmManifest,
    discover_swarm_packages,
    load_agent_blueprints,
    load_root_config,
    load_skill_assets,
    load_swarm_manifest,
)
from .toodefl import ToolDefinition


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

    # Register tools BEFORE creating agents so that agent blueprints can reference them
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

        # Resolve blueprint tools to actual ToolDefinition instances
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


def collect_tool_requirement_files(
    package_paths: Sequence[Path],
    manifest_entries: Sequence[Tuple[Path, SwarmManifest]],
) -> List[Path]:
    """Collect adjacent tool requirement files for every declared tool."""
    requirement_files: List[Path] = []
    seen: set[Path] = set()

    for package_path, (_, manifest) in zip(package_paths, manifest_entries):
        for tool_entry in manifest.tool_files:
            module_path = _resolve_module_path(tool_entry, package_path)
            if module_path is None:
                continue
            requirement_path = module_path.parent / "tool_requirements.txt"
            if requirement_path.exists():
                resolved = requirement_path.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    requirement_files.append(resolved)

    return requirement_files


def install_tool_requirements(requirement_files: Sequence[Path]) -> None:
    """Install all tool requirement files before tool modules are imported."""
    for requirement_file in requirement_files:
        if not requirement_file.exists():
            continue
        if requirement_file.stat().st_size == 0:
            continue
        try:
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "-r",
                    str(requirement_file),
                ],
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            raise SwarmLoaderError(
                f"Failed to install tool requirements from {requirement_file}: {exc}"
            ) from exc


def load_swarm_tools(package_path: Path, manifest: SwarmManifest) -> tuple[Dict[str, ToolDefinition], List[Path]]:
    """Load tool modules declared by a swarm package."""
    tools: Dict[str, ToolDefinition] = {}
    requirement_files: List[Path] = []
    seen_requirements: set[Path] = set()

    for tool_entry in manifest.tool_files:
        module_path = _resolve_module_path(tool_entry, package_path)
        module = _load_module_from_entry(tool_entry, package_path)
        tool_module_requirements = _discover_module_requirement_file(module_path)
        if tool_module_requirements and tool_module_requirements not in seen_requirements:
            seen_requirements.add(tool_module_requirements)
            requirement_files.append(tool_module_requirements)
        extracted = _extract_tools_from_module(module)
        for tool in extracted:
            if tool.tool_name in tools:
                raise SwarmLoaderError(f"Duplicate tool name: {tool.tool_name}")
            tools[tool.tool_name] = tool

    return tools, requirement_files


def _load_module_from_entry(entry: str, package_path: Path):
    module_path = _resolve_module_path(entry, package_path)
    if module_path is not None:
        return _load_module_from_path(module_path)

    try:
        return importlib.import_module(entry)
    except Exception as exc:
        raise SwarmLoaderError(f"Unable to import module '{entry}': {exc}") from exc


def _load_module_from_path(path: Path):
    if not path.exists():
        raise SwarmLoaderError(f"Python file not found: {path}")

    module_name = f"angelus_swarm_{path.parent.name}_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise SwarmLoaderError(f"Unable to load module from {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _resolve_module_path(entry: str, package_path: Path) -> Optional[Path]:
    entry_path = Path(entry)
    if entry_path.suffix == ".py" or entry_path.exists():
        if entry_path.is_absolute():
            resolved = entry_path.resolve()
        else:
            resolved = (package_path / entry_path).resolve()
        _ensure_allowed_module_path(resolved, package_path)
        return resolved

    spec = importlib.util.find_spec(entry)
    if spec and spec.origin and spec.origin not in {"built-in", "frozen"}:
        resolved = Path(spec.origin).resolve()
        _ensure_allowed_module_path(resolved, package_path)
        return resolved
    return None


def _resolve_package_local_path(package_path: Path, value: str | Path) -> Path:
    path = Path(value)
    resolved = path.resolve() if path.is_absolute() else (package_path / path).resolve()
    try:
        resolved.relative_to(package_path.resolve())
    except ValueError as exc:
        raise SwarmLoaderError(f"Path '{value}' escapes swarm package '{package_path}'.") from exc
    return resolved


def _ensure_allowed_module_path(module_path: Path, package_path: Path) -> None:
    allowed_roots = [package_path.resolve(), (Path.cwd() / "tools").resolve()]
    for root in allowed_roots:
        try:
            module_path.relative_to(root)
            return
        except ValueError:
            continue
    raise SwarmLoaderError(
        f"Module path '{module_path}' is outside the swarm package and allowed tool roots."
    )


def _discover_module_requirement_file(module_path: Optional[Path]) -> Optional[Path]:
    if module_path is None:
        return None
    requirement_file = module_path.parent / "tool_requirements.txt"
    if requirement_file.exists():
        return requirement_file.resolve()
    return None


def _extract_tools_from_module(module) -> List[ToolDefinition]:
    if hasattr(module, "TOOLS"):
        raw = getattr(module, "TOOLS")
        if not isinstance(raw, list):
            raise SwarmLoaderError("TOOLS must be a list of ToolDefinition instances.")
        tools = []
        for index, item in enumerate(raw):
            if not isinstance(item, ToolDefinition):
                raise SwarmLoaderError(f"TOOLS[{index}] is not a ToolDefinition instance.")
            tools.append(item)
        return tools

    if hasattr(module, "TOOL"):
        tool = getattr(module, "TOOL")
        if not isinstance(tool, ToolDefinition):
            raise SwarmLoaderError("TOOL must be a ToolDefinition instance.")
        return [tool]

    raise SwarmLoaderError(
        f"Tool module '{getattr(module, '__name__', '<unknown>')}' must expose TOOL or TOOLS."
    )


def _merge_backends(manifest: SwarmManifest) -> List[LLMBackendConfig]:
    backends: List[LLMBackendConfig] = []
    if manifest.default_llm is not None:
        backends.append(manifest.default_llm)
    backends.extend(manifest.llm_backends)

    deduped: Dict[str, LLMBackendConfig] = {}
    for backend in backends:
        deduped[backend.name] = backend
    return list(deduped.values())


def _backend_to_agent_config(backend: LLMBackendConfig) -> AgentConfig:
    return AgentConfig(
        api_url=str(backend.api_url or ""),
        api_key=backend.api_key,
        model=backend.model,
        provider=backend.provider,
    )


def _resolve_agent_prompt(
    blueprint: AgentBlueprint,
    *,
    package_path: Path,
    skill_by_name: Dict[str, SkillAsset],
    skill_by_path: Dict[Path, SkillAsset],
) -> str:
    if blueprint.character_prompt:
        return blueprint.character_prompt

    if blueprint.prompt_text:
        return blueprint.prompt_text.strip()

    if blueprint.skill_name:
        skill = skill_by_name.get(blueprint.skill_name)
        if skill is None:
            raise SwarmLoaderError(
                f"Agent '{blueprint.agent_id}' references unknown skill '{blueprint.skill_name}'."
            )
        return skill.content

    if blueprint.prompt_file:
        prompt_path = _resolve_package_local_path(package_path, blueprint.prompt_file)
        skill = skill_by_path.get(prompt_path)
        if skill is not None:
            return skill.content
        if prompt_path.exists():
            return load_skill_asset(prompt_path).content
        raise SwarmLoaderError(
            f"Agent '{blueprint.agent_id}' references missing prompt file '{blueprint.prompt_file}'."
        )

    raise SwarmLoaderError(
        f"Agent '{blueprint.agent_id}' must define character_prompt, prompt_text, prompt_file, or skill_name."
    )


def _build_llm_handler(
    blueprint: AgentBlueprint,
    backends: Sequence[LLMBackendConfig],
    default_backend_name: Optional[str],
) -> LLMFetcher:
    if blueprint.api_key or blueprint.model:
        return LLMFetcher(
            api_url=blueprint.api_url,
            api_key=blueprint.api_key,
            model=blueprint.model,
            provider=blueprint.provider,
        )

    if not backends:
        raise SwarmLoaderError(
            f"Agent '{blueprint.agent_id}' has no inline llm config and the package provides no backends."
        )

    if blueprint.backend_name is not None:
        if blueprint.backend_name not in {backend.name for backend in backends}:
            raise SwarmLoaderError(
                f"Agent '{blueprint.agent_id}' references unknown backend '{blueprint.backend_name}'."
            )
        return LLMFetcher(backends=backends, default_backend=blueprint.backend_name)

    if default_backend_name and default_backend_name in {backend.name for backend in backends}:
        return LLMFetcher(backends=backends, default_backend=default_backend_name)

    return LLMFetcher(backends=backends)


def _resolve_workspace_defaults(package_path: Path, manifest: SwarmManifest) -> tuple[str, Path]:
    workspace = manifest.workspace
    root_value = workspace.default_root if workspace.default_root is not None else "."
    return workspace.default_mode, _resolve_workspace_path(package_path, root_value)


def _resolve_workspace_for_agent(
    package_path: Path,
    manifest: SwarmManifest,
    blueprint: AgentBlueprint,
) -> tuple[str, Path]:
    workspace = manifest.workspace
    agent_override = workspace.agents.get(blueprint.agent_id)

    mode = (
        agent_override.workspace_mode
        if agent_override and agent_override.workspace_mode is not None
        else getattr(blueprint, "workspace_mode", None)
    )
    if mode is None:
        mode = workspace.default_mode

    root_value = (
        agent_override.workspace_root
        if agent_override and agent_override.workspace_root is not None
        else getattr(blueprint, "workspace_root", None)
    )
    if root_value is None:
        root_value = workspace.default_root if workspace.default_root is not None else "."

    return mode, _resolve_workspace_path(package_path, root_value)


def _resolve_workspace_path(package_path: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path.resolve()
    return (package_path / path).resolve()
