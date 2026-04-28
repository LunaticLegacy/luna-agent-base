"""Low-level utilities for swarm package loading.

This module contains the nuts and bolts of module discovery, dynamic
import, requirement installation, and configuration resolution.  Most
callers should use the high-level functions in :mod:`core.swarm_loader_parts.build`
instead of importing from here directly.

Key responsibilities:

* Requirement file collection and ``pip install`` invocation.
* Dynamic module loading from package-local Python files.
* Tool extraction from module ``TOOL`` / ``TOOLS`` exports.
* LLM backend merging and handler construction.
* Agent prompt resolution (skill -> file -> inline text).
* Workspace path resolution with sandbox checks.

Exports:
    - Requirement helpers
    - :func:`load_swarm_tools`
    - :func:`load_swarm_apis`
    - :func:`_load_module_from_entry`
    - :func:`_load_module_from_path`
    - :func:`_resolve_module_path`
    - :func:`_merge_backends`
    - :func:`_backend_to_agent_config`
    - :func:`_resolve_agent_prompt`
    - :func:`_resolve_workspace_defaults`
    - :func:`_resolve_workspace_for_agent`
"""

from __future__ import annotations

import importlib
import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from modules.llm_fetcher import LLMBackendConfig, LLMFetcher

from ..config import AgentConfig
from ..skills import SkillAsset, load_skill_asset
from ..swarm_spec import AgentBlueprint, SwarmLoaderError, SwarmManifest
from ..toodefl import ToolDefinition


def collect_tool_requirement_files(
    package_paths: Sequence[Path],
    manifest_entries: Sequence[Tuple[Path, SwarmManifest]],
) -> List[Path]:
    """Collect adjacent tool requirement files for every declared tool.

    Args:
        package_paths: Sequence of swarm package directories.
        manifest_entries: Parallel sequence of ``(manifest_path, manifest)`` tuples.

    Returns:
        Sorted list of unique ``tool_requirements.txt`` paths.
    """
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
    """Install all tool requirement files before tool modules are imported.

    Args:
        requirement_files: Paths to ``requirements.txt`` files.

    Raises:
        SwarmLoaderError: If ``pip install`` fails.
    """
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
    """Load tool modules declared by a swarm package.

    Each tool module must expose ``TOOL`` (single tool) or ``TOOLS`` (list).

    Args:
        package_path: Path to the swarm directory.
        manifest: Parsed manifest.

    Returns:
        Tuple of ``(tools_dict, requirement_files)``.

    Raises:
        SwarmLoaderError: On duplicate tool names or malformed exports.
    """
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


def collect_api_requirement_files(
    package_paths: Sequence[Path],
    manifest_entries: Sequence[Tuple[Path, SwarmManifest]],
) -> List[Path]:
    """Collect adjacent API requirement files for every declared package API.

    Native APIs (prefixed with ``native:``) are skipped because they are
    assumed to be part of the base environment.

    Args:
        package_paths: Sequence of swarm package directories.
        manifest_entries: Parallel sequence of ``(manifest_path, manifest)`` tuples.

    Returns:
        Sorted list of unique ``api_requirements.txt`` paths.
    """
    requirement_files: List[Path] = []
    seen: set[Path] = set()

    for package_path, (_, manifest) in zip(package_paths, manifest_entries):
        for api_entry in manifest.api_files:
            if _is_native_api_entry(api_entry):
                continue
            module_path = _resolve_api_module_path(api_entry, package_path)
            if module_path is None:
                continue
            requirement_path = module_path.parent / "api_requirements.txt"
            if requirement_path.exists():
                resolved = requirement_path.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    requirement_files.append(resolved)

    return requirement_files


def install_api_requirements(requirement_files: Sequence[Path]) -> None:
    """Install all API requirement files before API modules are imported.

    Args:
        requirement_files: Paths to ``requirements.txt`` files.

    Raises:
        SwarmLoaderError: If ``pip install`` fails.
    """
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
                f"Failed to install API requirements from {requirement_file}: {exc}"
            ) from exc


def load_swarm_apis(package_path: Path, manifest: SwarmManifest) -> tuple[Dict[str, Dict[str, Any]], List[Path]]:
    """Load API modules declared by a swarm package.

    API entries may be:

    * ``native:module.name`` — import from the Python environment.
    * ``package:path/to/module.py`` — load from the swarm directory.

    Args:
        package_path: Path to the swarm directory.
        manifest: Parsed manifest.

    Returns:
        Tuple of ``(apis_dict, requirement_files)``.

    Raises:
        SwarmLoaderError: On duplicate names or malformed entries.
    """
    apis: Dict[str, Dict[str, Any]] = {}
    requirement_files: List[Path] = []
    seen_requirements: set[Path] = set()

    for api_entry in manifest.api_files:
        origin, module_entry = _parse_api_entry(api_entry)
        if origin == "native":
            module = importlib.import_module(module_entry)
            api_name = _resolve_api_name(module, module_entry)
            apis[api_name] = {
                "api": module,
                "origin": "native",
                "source": module_entry,
            }
            continue

        module_path = _resolve_api_module_path(module_entry, package_path)
        if module_path is None:
            raise SwarmLoaderError(
                f"API entry '{api_entry}' must be a native import or a package-local Python file."
            )
        module = _load_module_from_path(module_path)
        api_module_requirements = _discover_api_requirement_file(module_path)
        if api_module_requirements and api_module_requirements not in seen_requirements:
            seen_requirements.add(api_module_requirements)
            requirement_files.append(api_module_requirements)
        api_name = _resolve_api_name(module, module_path.stem)
        if api_name in apis:
            raise SwarmLoaderError(f"Duplicate api name: {api_name}")
        apis[api_name] = {
            "api": module,
            "origin": "package",
            "source": str(module_path),
        }

    return apis, requirement_files


def _load_module_from_entry(entry: str, package_path: Path):
    """Load a module by entry string, trying package-local then global import.

    Args:
        entry: Module path (``.py`` file) or dotted module name.
        package_path: Base directory for package-local resolution.

    Returns:
            The loaded module.

    Raises:
        SwarmLoaderError: If neither resolution strategy succeeds.
    """
    module_path = _resolve_module_path(entry, package_path)
    if module_path is not None:
        return _load_module_from_path(module_path)

    try:
        return importlib.import_module(entry)
    except Exception as exc:
        raise SwarmLoaderError(f"Unable to import module '{entry}': {exc}") from exc


def _load_module_from_path(path: Path):
    """Dynamically load a Python file as a module.

    If the file lives inside a package directory (i.e. an ``__init__.py``
    exists in the parent), the parent package is registered in ``sys.modules``
    so that relative imports work.

    Args:
        path: Absolute path to the Python file.

    Returns:
        The loaded module.

    Raises:
        SwarmLoaderError: If the file does not exist or cannot be loaded.
    """
    if not path.exists():
        raise SwarmLoaderError(f"Python file not found: {path}")

    parent = path.parent
    package_name = f"angelus_swarm_{parent.name}"
    init_path = parent / "__init__.py"

    # If the file lives inside a package directory, register the parent package
    # so that relative imports (e.g. ``from .common import ...``) work.
    if init_path.exists() and package_name not in sys.modules:
        pkg_spec = importlib.util.spec_from_file_location(
            package_name, str(init_path), submodule_search_locations=[str(parent)]
        )
        if pkg_spec is not None:
            pkg = importlib.util.module_from_spec(pkg_spec)
            sys.modules[package_name] = pkg
            if pkg_spec.loader is not None:
                pkg_spec.loader.exec_module(pkg)

    if init_path.exists():
        module_name = f"{package_name}.{path.stem}"
    else:
        module_name = f"angelus_swarm_{parent.name}_{path.stem}"

    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise SwarmLoaderError(f"Unable to load module from {path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _resolve_module_path(entry: str, package_path: Path) -> Optional[Path]:
    """Resolve *entry* to an absolute file path within the package.

    Falls back to ``importlib.util.find_spec`` for dotted module names.

    Args:
        entry: File path or dotted module name.
        package_path: Base directory for relative resolution.

    Returns:
        Absolute :class:`Path` or ``None``.
    """
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


def _parse_api_entry(entry: str) -> tuple[str, str]:
    """Split an API entry string into ``(origin, module_entry)``.

    Defaults to ``"package"`` if no prefix is present.
    """
    raw = str(entry or "").strip()
    if raw.startswith("native:"):
        return "native", raw.removeprefix("native:").strip()
    if raw.startswith("package:"):
        return "package", raw.removeprefix("package:").strip()
    return "package", raw


def _is_native_api_entry(entry: str) -> bool:
    """Return whether *entry* is a native (environment) import."""
    return str(entry or "").strip().startswith("native:")


def _resolve_api_module_path(entry: str, package_path: Path) -> Optional[Path]:
    """Resolve an API module path, returning ``None`` for native entries."""
    if _is_native_api_entry(entry):
        return None
    return _resolve_module_path(entry, package_path)


def _discover_api_requirement_file(module_path: Optional[Path]) -> Optional[Path]:
    """Look for ``api_requirements.txt`` next to *module_path*."""
    if module_path is None:
        return None
    requirement_file = module_path.parent / "api_requirements.txt"
    if requirement_file.exists():
        return requirement_file.resolve()
    return None


def _resolve_api_name(module: Any, fallback: str) -> str:
    """Resolve an API name from module attributes.

    Prefers ``API_NAME``, then ``api_name`` / ``name`` in a dict, then *fallback*.
    """
    explicit_name = getattr(module, "API_NAME", None)
    if isinstance(explicit_name, str) and explicit_name.strip():
        return explicit_name.strip()
    if isinstance(module, dict):
        value = module.get("api_name") or module.get("name")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return str(fallback).strip()


def _resolve_package_local_path(package_path: Path, value: str | Path) -> Path:
    """Resolve *value* relative to *package_path* and enforce sandbox containment.

    Args:
        package_path: The swarm package directory.
        value: Relative or absolute path.

    Returns:
        Absolute :class:`Path`.

    Raises:
        SwarmLoaderError: If the resolved path escapes *package_path*.
    """
    path = Path(value)
    resolved = path.resolve() if path.is_absolute() else (package_path / path).resolve()
    try:
        resolved.relative_to(package_path.resolve())
    except ValueError as exc:
        raise SwarmLoaderError(f"Path '{value}' escapes swarm package '{package_path}'.") from exc
    return resolved


def _ensure_allowed_module_path(module_path: Path, package_path: Path) -> None:
    """Enforce that *module_path* is inside the package or the tool root.

    Args:
        module_path: The module file path.
        package_path: The swarm package directory.

    Raises:
        SwarmLoaderError: If the path is outside allowed roots.
    """
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
    """Look for ``tool_requirements.txt`` next to *module_path*."""
    if module_path is None:
        return None
    requirement_file = module_path.parent / "tool_requirements.txt"
    if requirement_file.exists():
        return requirement_file.resolve()
    return None


def _extract_tools_from_module(module) -> List[ToolDefinition]:
    """Extract :class:`ToolDefinition` objects from a loaded module.

    Supports ``TOOLS`` (list) and ``TOOL`` (single) exports.

    Args:
        module: The loaded module.

    Returns:
        List of tool definitions.

    Raises:
        SwarmLoaderError: If the export is missing or malformed.
    """
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
    """Deduplicate and merge LLM backends from a manifest.

    The default backend is always included first; backends are keyed by name.

    Args:
        manifest: Parsed manifest.

    Returns:
        List of unique :class:`LLMBackendConfig` objects.
    """
    backends: List[LLMBackendConfig] = []
    if manifest.default_llm is not None:
        backends.append(manifest.default_llm)
    backends.extend(manifest.llm_backends)

    deduped: Dict[str, LLMBackendConfig] = {}
    for backend in backends:
        deduped[backend.name] = backend
    return list(deduped.values())


def _backend_to_agent_config(backend: LLMBackendConfig) -> AgentConfig:
    """Convert an :class:`LLMBackendConfig` to an :class:`AgentConfig`."""
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
    """Resolve the character prompt for an agent blueprint.

    Resolution order:

    1. ``character_prompt`` (inline).
    2. ``prompt_text`` (inline).
    3. ``skill_name`` (lookup in *skill_by_name*).
    4. ``prompt_file`` (load from disk or *skill_by_path*).

    Args:
        blueprint: The agent blueprint.
        package_path: The swarm package directory.
        skill_by_name: Map of loaded skills by name.
        skill_by_path: Map of loaded skills by absolute path.

    Returns:
        The resolved prompt string.

    Raises:
        SwarmLoaderError: If no prompt source is available.
    """
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
    limiter: Optional[Any] = None,
) -> LLMFetcher:
    """Construct an :class:`LLMFetcher` for an agent blueprint.

    Resolution order:

    1. Inline ``api_key`` / ``model`` on the blueprint.
    2. Named ``backend_name`` referencing a backend in *backends*.
    3. ``default_backend_name`` if it exists in *backends*.
    4. First available backend.

    Args:
        blueprint: The agent blueprint.
        backends: Available LLM backends.
        default_backend_name: Optional default backend name.
        limiter: Optional concurrency limiter.

    Returns:
        Configured :class:`LLMFetcher`.

    Raises:
        SwarmLoaderError: If no backend can be resolved.
    """
    if blueprint.api_key or blueprint.model:
        return LLMFetcher(
            api_url=blueprint.api_url,
            api_key=blueprint.api_key,
            model=blueprint.model,
            provider=blueprint.provider,
            limiter=limiter,
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
        return LLMFetcher(backends=backends, default_backend=blueprint.backend_name, limiter=limiter)

    if default_backend_name and default_backend_name in {backend.name for backend in backends}:
        return LLMFetcher(backends=backends, default_backend=default_backend_name, limiter=limiter)

    return LLMFetcher(backends=backends, limiter=limiter)


def _resolve_workspace_defaults(package_path: Path, manifest: SwarmManifest) -> tuple[str, Path]:
    """Resolve swarm-level workspace defaults.

    Args:
        package_path: The swarm package directory.
        manifest: Parsed manifest.

    Returns:
        Tuple of ``(mode, root_path)``.
    """
    workspace = manifest.workspace
    root_value = workspace.default_root if workspace.default_root is not None else "."
    return workspace.default_mode, _resolve_workspace_path(_workspace_base_path(package_path), root_value)


def _resolve_workspace_for_agent(
    package_path: Path,
    manifest: SwarmManifest,
    blueprint: AgentBlueprint,
) -> tuple[str, Path]:
    """Resolve workspace settings for a specific agent.

    Agent-level overrides in ``manifest.workspace.agents`` take precedence,
    followed by blueprint attributes, then swarm defaults.

    Args:
        package_path: The swarm package directory.
        manifest: Parsed manifest.
        blueprint: The agent blueprint.

    Returns:
        Tuple of ``(mode, root_path)``.
    """
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

    return mode, _resolve_workspace_path(_workspace_base_path(package_path), root_value)


def _workspace_base_path(package_path: Path) -> Path:
    """Return the default workspace base directory for a package."""
    return (package_path / "workspace").resolve()


def _resolve_workspace_path(base_path: Path, value: str | Path) -> Path:
    """Resolve a workspace path relative to *base_path*.

    Absolute paths are returned as-is.
    """
    path = Path(value)
    if path.is_absolute():
        return path.resolve()
    return (base_path / path).resolve()
