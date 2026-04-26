from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, Optional
import importlib.util
import os
import re
import tomllib

from modules.llm_fetcher import LLMBackendConfig
from .skills import SkillAsset, load_skill_asset


class SwarmLoaderError(ValueError):
    """Raised when a swarm package cannot be parsed or loaded."""


@dataclass
class ApiConfig:
    """Mutable API/runtime settings persisted in config.toml."""

    base_url: str = "/api"
    timeout_seconds: int = 30
    sse_reconnect_interval_seconds: int = 5
    auto_reconnect: bool = True
    require_auth: bool = False
    api_token: Optional[str] = None
    api_token_env: str = "ANGELUS_API_TOKEN"
    cors_allowed_origins: List[str] = field(default_factory=list)


@dataclass
class SwarmAppConfig:
    """Root application config for discovering swarm packages."""

    swarm_root: Path = Path("agents")
    api: ApiConfig = field(default_factory=ApiConfig)


@dataclass
class AgentBlueprint:
    """One agent definition loaded from a Python file."""

    agent_id: str
    character_prompt: Optional[str] = None
    name: Optional[str] = None
    backend_name: Optional[str] = None
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    provider: str = "openai"
    skill_name: Optional[str] = None
    prompt_file: Optional[str] = None
    prompt_text: Optional[str] = None
    tools: List[str] = field(default_factory=list)
    tool_execution_mode: str = "internal"


@dataclass
class WorkspaceAgentConfig:
    """Workspace override for one agent, declared in swarm.toml."""

    workspace_mode: Optional[str] = None
    workspace_root: Optional[str] = None


@dataclass
class WorkspaceConfig:
    """Swarm-level workspace settings parsed from swarm.toml."""

    default_mode: str = "workspace"
    default_root: Optional[str] = None
    agents: Dict[str, WorkspaceAgentConfig] = field(default_factory=dict)


@dataclass
class GlobalVariablesConfig:
    """Swarm-level variables that can be injected into selected agents."""

    values: Dict[str, Any] = field(default_factory=dict)
    visibility: Dict[str, List[str]] = field(default_factory=dict)

    def visible_values_for_agent(self, agent_id: str) -> Dict[str, Any]:
        visible: Dict[str, Any] = {}
        for key, value in self.values.items():
            agents = self.visibility.get(key)
            if agents is None or agent_id in agents:
                visible[key] = value
        return visible


@dataclass
class SwarmManifest:
    """Swarm package manifest parsed from TOML."""

    swarm_name: str
    graph_file: str
    agent_files: List[str]
    tool_files: List[str] = field(default_factory=list)
    api_files: List[str] = field(default_factory=list)
    tool_capabilities: Dict[str, List[str]] = field(default_factory=dict)
    skill_files: List[str] = field(default_factory=list)
    default_backend: Optional[str] = None
    default_llm: Optional[LLMBackendConfig] = None
    llm_backends: List[LLMBackendConfig] = field(default_factory=list)
    workspace: WorkspaceConfig = field(default_factory=WorkspaceConfig)
    global_variables: GlobalVariablesConfig = field(default_factory=GlobalVariablesConfig)


def load_root_config(path: Path) -> SwarmAppConfig:
    """Load the top-level application config."""
    if not path.exists():
        return SwarmAppConfig()

    with path.open("rb") as handle:
        raw = tomllib.load(handle)

    app_section = raw.get("app", raw)
    if not isinstance(app_section, dict):
        raise SwarmLoaderError("[app] must be a TOML table.")

    api_section = raw.get("api", {})
    if not isinstance(api_section, dict):
        raise SwarmLoaderError("[api] must be a TOML table.")

    swarm_root = str(app_section.get("swarm_root", "agents")).strip() or "agents"
    base_url = str(api_section.get("base_url", "/api")).strip() or "/api"
    timeout_seconds = _coerce_positive_int(api_section.get("timeout_seconds", 30), fallback=30)
    sse_reconnect_interval_seconds = _coerce_positive_int(
        api_section.get("sse_reconnect_interval_seconds", 5),
        fallback=5,
    )
    auto_reconnect = _coerce_bool(api_section.get("auto_reconnect", True), fallback=True)
    require_auth = _coerce_bool(api_section.get("require_auth", False), fallback=False)
    api_token = _resolve_env_vars(str(api_section.get("api_token", "")).strip()) or None
    api_token_env = str(api_section.get("api_token_env", "ANGELUS_API_TOKEN")).strip() or "ANGELUS_API_TOKEN"
    cors_allowed_origins = _normalize_string_list(
        api_section.get("cors_allowed_origins", []),
        field_name="[api].cors_allowed_origins",
    )

    return SwarmAppConfig(
        swarm_root=Path(swarm_root),
        api=ApiConfig(
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            sse_reconnect_interval_seconds=sse_reconnect_interval_seconds,
            auto_reconnect=auto_reconnect,
            require_auth=require_auth,
            api_token=api_token,
            api_token_env=api_token_env,
            cors_allowed_origins=cors_allowed_origins,
        ),
    )


def _coerce_positive_int(raw: Any, *, fallback: int) -> int:
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


def _coerce_bool(raw: Any, *, fallback: bool) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    if raw is None:
        return fallback
    value = str(raw).strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    return fallback


def _normalize_string_list(raw: Any, *, field_name: str) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, list):
        values = raw
    else:
        raise SwarmLoaderError(f"{field_name} must be a string array.")
    return [str(item).strip() for item in values if str(item).strip()]


def _parse_tool_capabilities(raw: Any, source: Path) -> Dict[str, List[str]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise SwarmLoaderError(f"[tool_capabilities] must be a TOML table in {source}")
    capabilities: Dict[str, List[str]] = {}
    for tool_name, raw_values in raw.items():
        capabilities[str(tool_name).strip()] = _normalize_string_list(
            raw_values,
            field_name=f"[tool_capabilities].{tool_name}",
        )
    return capabilities


def discover_swarm_packages(root: Path) -> List[Path]:
    """Return all child directories that look like swarm packages."""
    if not root.exists():
        return []
    if not root.is_dir():
        raise SwarmLoaderError(f"Swarm root is not a directory: {root}")

    packages: List[Path] = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and list(child.glob("*.toml")):
            packages.append(child)
    return packages


def load_swarm_manifest(package_path: Path) -> tuple[Path, SwarmManifest]:
    """Load and validate a swarm manifest from one package directory."""
    toml_files = sorted(package_path.glob("*.toml"))
    if not toml_files:
        raise SwarmLoaderError(f"No TOML manifest found in {package_path}")
    if len(toml_files) != 1:
        raise SwarmLoaderError(
            f"Expected exactly one TOML manifest in {package_path}, found {len(toml_files)}"
        )

    manifest_path = toml_files[0]
    with manifest_path.open("rb") as handle:
        raw = tomllib.load(handle)

    swarm_section = raw.get("swarm")
    if not isinstance(swarm_section, dict):
        raise SwarmLoaderError(f"[swarm] table is required in {manifest_path}")

    swarm_name = str(swarm_section.get("name", package_path.name)).strip() or package_path.name
    graph_file = str(swarm_section.get("graph_file", "")).strip()
    if not graph_file:
        raise SwarmLoaderError(f"[swarm].graph_file is required in {manifest_path}")

    raw_agent_files = swarm_section.get("agent_files", [])
    if not isinstance(raw_agent_files, list) or not raw_agent_files:
        raise SwarmLoaderError(f"[swarm].agent_files must be a non-empty array in {manifest_path}")
    agent_files = [str(item).strip() for item in raw_agent_files if str(item).strip()]
    if not agent_files:
        raise SwarmLoaderError(f"[swarm].agent_files contains no usable entries in {manifest_path}")

    tool_files = _normalize_path_list(swarm_section.get("tool_files", []), field_name="[swarm].tool_files")
    api_files = _normalize_path_list(swarm_section.get("api_files", []), field_name="[swarm].api_files")
    tool_capabilities = _parse_tool_capabilities(raw.get("tool_capabilities", {}), manifest_path)
    skill_files = _normalize_path_list(swarm_section.get("skill_files", []), field_name="[swarm].skill_files")

    default_backend = swarm_section.get("default_backend")
    if default_backend is not None:
        default_backend = str(default_backend).strip() or None

    workspace = _parse_workspace_config(raw.get("workspace", {}), manifest_path)
    global_variables = _parse_global_variables_config(raw.get("globals", {}), manifest_path)

    llm_section = raw.get("llm", {})
    if not isinstance(llm_section, dict):
        raise SwarmLoaderError(f"[llm] must be a TOML table in {manifest_path}")

    default_llm = _parse_llm_backend(llm_section.get("default"), fallback_name="default")
    llm_backends = _parse_llm_backend_list(llm_section.get("backends", []))

    if default_llm is None and not llm_backends:
        raise SwarmLoaderError(
            f"{manifest_path} must define at least one LLM backend in [llm.default] or [[llm.backends]]."
        )

    return manifest_path, SwarmManifest(
        swarm_name=swarm_name,
        graph_file=graph_file,
        agent_files=agent_files,
        tool_files=tool_files,
        api_files=api_files,
        tool_capabilities=tool_capabilities,
        skill_files=skill_files,
        default_backend=default_backend,
        default_llm=default_llm,
        llm_backends=llm_backends,
        workspace=workspace,
        global_variables=global_variables,
    )


def load_agent_blueprints(package_path: Path, manifest: SwarmManifest) -> List[AgentBlueprint]:
    """Load and validate all agent blueprints referenced by the manifest."""
    blueprints: List[AgentBlueprint] = []

    for file_name in manifest.agent_files:
        agent_path = _resolve_package_local_path(package_path, file_name)
        module = _load_module_from_path(agent_path)
        raw_specs = _extract_agent_specs(module)
        if not raw_specs:
            raise SwarmLoaderError(
                f"Agent file '{file_name}' in {package_path} must define AGENT, AGENT_SPEC, or AGENTS."
            )
        for raw_spec in raw_specs:
            blueprints.append(_coerce_agent_blueprint(raw_spec, agent_path))

    return blueprints


def _resolve_package_local_path(package_path: Path, value: str | Path) -> Path:
    path = Path(value)
    resolved = path.resolve() if path.is_absolute() else (package_path / path).resolve()
    try:
        resolved.relative_to(package_path.resolve())
    except ValueError as exc:
        raise SwarmLoaderError(f"Path '{value}' escapes swarm package '{package_path}'.") from exc
    return resolved


def _load_module_from_path(path: Path) -> ModuleType:
    if not path.exists():
        raise SwarmLoaderError(f"Python file not found: {path}")

    module_name = f"angelus_swarm_{path.parent.name}_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise SwarmLoaderError(f"Unable to load module from {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _extract_agent_specs(module: ModuleType) -> List[Dict[str, Any]]:
    if hasattr(module, "AGENTS"):
        raw = getattr(module, "AGENTS")
        if not isinstance(raw, list):
            raise SwarmLoaderError("AGENTS must be a list of mappings.")
        return [item for item in raw if isinstance(item, dict)]

    if hasattr(module, "AGENT_SPEC"):
        raw = getattr(module, "AGENT_SPEC")
        if not isinstance(raw, dict):
            raise SwarmLoaderError("AGENT_SPEC must be a mapping.")
        return [raw]

    if hasattr(module, "AGENT"):
        raw = getattr(module, "AGENT")
        if not isinstance(raw, dict):
            raise SwarmLoaderError("AGENT must be a mapping.")
        return [raw]

    return []


def _coerce_agent_blueprint(raw: Dict[str, Any], source: Path) -> AgentBlueprint:
    agent_id = str(raw.get("agent_id", "")).strip()
    if not agent_id:
        raise SwarmLoaderError(f"{source} is missing agent_id.")

    tools_raw = raw.get("tools", [])
    tools: List[str] = []
    if isinstance(tools_raw, list):
        tools = [str(item).strip() for item in tools_raw if str(item).strip()]
    elif isinstance(tools_raw, str):
        tools = [tools_raw.strip()]

    return AgentBlueprint(
        agent_id=agent_id,
        character_prompt=str(raw.get("character_prompt", "")).strip() or None,
        name=raw.get("name"),
        backend_name=raw.get("backend_name"),
        api_url=raw.get("api_url"),
        api_key=raw.get("api_key"),
        model=raw.get("model"),
        provider=str(raw.get("provider", "openai")),
        skill_name=raw.get("skill_name"),
        prompt_file=raw.get("prompt_file"),
        prompt_text=raw.get("prompt_text"),
        tools=tools,
        tool_execution_mode=str(raw.get("tool_execution_mode", "internal")).strip(),
    )


def _parse_workspace_config(raw: Any, source: Path) -> WorkspaceConfig:
    if raw is None:
        return WorkspaceConfig()
    if not isinstance(raw, dict):
        raise SwarmLoaderError(f"[workspace] must be a TOML table in {source}")

    default_mode = str(raw.get("default_mode", "workspace")).strip() or "workspace"
    if default_mode not in {"workspace", "full_access"}:
        raise SwarmLoaderError(
            f"[workspace] default_mode '{default_mode}' in {source} is invalid. "
            "Expected 'workspace' or 'full_access'."
        )
    default_root_value = raw.get("default_root")
    default_root = str(default_root_value).strip() if default_root_value is not None else None
    if default_root == "":
        default_root = None

    agents_raw = raw.get("agents", {})
    if agents_raw is None:
        agents_raw = {}
    if not isinstance(agents_raw, dict):
        raise SwarmLoaderError(f"[workspace].agents must be a TOML table in {source}")

    agents: Dict[str, WorkspaceAgentConfig] = {}
    for agent_id, agent_raw in agents_raw.items():
        if not isinstance(agent_raw, dict):
            raise SwarmLoaderError(f"[workspace].agents.{agent_id} must be a TOML table in {source}")
        mode_value = agent_raw.get("mode")
        root_value = agent_raw.get("root")
        workspace_mode = str(mode_value).strip() if mode_value is not None else None
        if workspace_mode == "":
            workspace_mode = None
        if workspace_mode is not None and workspace_mode not in {"workspace", "full_access"}:
            raise SwarmLoaderError(
                f"[workspace].agents.{agent_id}.mode '{workspace_mode}' in {source} is invalid. "
                "Expected 'workspace' or 'full_access'."
            )
        workspace_root = str(root_value).strip() if root_value is not None else None
        if workspace_root == "":
            workspace_root = None
        agents[str(agent_id)] = WorkspaceAgentConfig(
            workspace_mode=workspace_mode,
            workspace_root=workspace_root,
        )

    return WorkspaceConfig(
        default_mode=default_mode,
        default_root=default_root,
        agents=agents,
    )


def _parse_global_variables_config(raw: Any, source: Path) -> GlobalVariablesConfig:
    if raw is None:
        return GlobalVariablesConfig()
    if not isinstance(raw, dict):
        raise SwarmLoaderError(f"[globals] must be a TOML table in {source}")

    values: Dict[str, Any] = {}
    visibility: Dict[str, List[str]] = {}

    for key, value in raw.items():
        if key == "visibility":
            continue
        values[str(key).strip()] = value

    visibility_raw = raw.get("visibility", {})
    if visibility_raw is None:
        visibility_raw = {}
    if not isinstance(visibility_raw, dict):
        raise SwarmLoaderError(f"[globals].visibility must be a TOML table in {source}")

    for variable_name, agent_list in visibility_raw.items():
        visibility[str(variable_name).strip()] = _normalize_string_list(
            agent_list,
            field_name=f"[globals].visibility.{variable_name}",
        )

    return GlobalVariablesConfig(values=values, visibility=visibility)


def _resolve_env_vars(value: str) -> str:
    """Replace ${VAR_NAME} or $VAR_NAME with environment variable values."""
    pattern = re.compile(r"\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)")

    def replacer(match: re.Match[str]) -> str:
        var_name = match.group(1) or match.group(2)
        env_value = os.getenv(var_name, "")
        if env_value == "":
            raise SwarmLoaderError(
                f"Environment variable '{var_name}' is required but not set. "
                f"Please export it before starting the runtime."
            )
        return env_value

    return pattern.sub(replacer, value)


def _parse_llm_backend(raw: Any, *, fallback_name: str) -> Optional[LLMBackendConfig]:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise SwarmLoaderError("LLM backend definitions must be TOML tables.")
    if not raw:
        return None

    backend_name = str(raw.get("name", fallback_name)).strip() or fallback_name
    provider = str(raw.get("provider", "openai")).strip() or "openai"
    model = str(raw.get("model", "")).strip()
    api_key = _resolve_env_vars(str(raw.get("api_key", "")).strip())
    api_url = raw.get("api_url")
    if api_url is not None:
        api_url = _resolve_env_vars(str(api_url).strip()) or None
    timeout = float(raw.get("timeout", 60.0))
    max_retries = int(raw.get("max_retries", 0))
    extra = raw.get("extra", {})
    if extra is None:
        extra = {}
    if not isinstance(extra, dict):
        raise SwarmLoaderError("llm.backend.extra must be a table when provided.")

    if not model:
        raise SwarmLoaderError(f"LLM backend '{backend_name}' is missing model.")
    if not api_key:
        raise SwarmLoaderError(f"LLM backend '{backend_name}' is missing api_key.")

    return LLMBackendConfig(
        name=backend_name,
        provider=provider,
        model=model,
        api_key=api_key,
        api_url=api_url,
        timeout=timeout,
        max_retries=max_retries,
        extra=dict(extra),
    )


def _parse_llm_backend_list(raw: Any) -> List[LLMBackendConfig]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise SwarmLoaderError("[[llm.backends]] must be an array of tables.")

    backends: List[LLMBackendConfig] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise SwarmLoaderError(f"LLM backend at index {index} must be a table.")
        backend = _parse_llm_backend(item, fallback_name=f"backend_{index}")
        if backend is not None:
            backends.append(backend)
    return backends


def _normalize_path_list(raw: Any, *, field_name: str) -> List[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise SwarmLoaderError(f"{field_name} must be an array of strings.")

    values = [str(item).strip() for item in raw if str(item).strip()]
    return values


def load_skill_assets(package_path: Path, manifest: SwarmManifest) -> List[SkillAsset]:
    """Load all skill assets referenced by the manifest."""
    skills: List[SkillAsset] = []
    for file_name in manifest.skill_files:
        skill_path = _resolve_package_local_path(package_path, file_name)
        skills.append(load_skill_asset(skill_path))
    return skills
