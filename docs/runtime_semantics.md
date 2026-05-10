# Runtime Semantics

## Architecture

- `app.py` loads `config.toml`, builds the FastAPI app, and passes the configured swarm root into the web layer.
- `web/server.py` owns the HTTP surface and the global `Core` instance.
- `core/core.py` owns swarm registry state, package discovery, and the startup package inventory.
- `agents/<package>/swarm.toml` is the package manifest.

## `core/core.py`

### `GlobalVariablesConfig`

- `visible_values_for_agent(agent_id) -> Dict[str, Any]`
- Returns the subset of global variables visible to one agent.
- Variables with no visibility rule are visible to everyone.

### `RuntimeChangeRecord`

- Lightweight audit payload for runtime mutations.
- Stored inside `Core.architecture_manager["runtime_changes"]`.

### `AgentPackageRecord`

- Describes one discovered agent package.
- `valid=True` records packages that passed manifest/path checks.
- `swarm` is a fully built runtime swarm when the manifest exposes a usable `llm.default` block; invalid packages are kept as records with `swarm=None`.

### `Core`

- `__init__()`
  - Creates empty swarm, history, global-variable, and package-inventory registries.

- `register_swarm(name, swarm) -> None`
  - Registers an already-created swarm in memory.

- `create_swarm(name, llm_fetcher, spec=None, max_concurrency=None) -> AgentSwarm`
  - Builds a fresh `AgentSwarm` and stores it in `self.swarms`.

- `get_swarm(name) -> AgentSwarm`
  - Returns a registered swarm or raises `KeyError`.

- `remove_swarm(name) -> None`
  - Removes a swarm and its run history.

- `list_swarms() -> List[Dict[str, Any]]`
  - Returns swarm metadata for the runtime registry.

- `load_swarm_from_config(name, llm_fetcher, tools=None) -> AgentSwarm`
  - Convenience constructor for a minimal runtime swarm.

- `discover_agent_package_roots(swarm_root="agents") -> List[Path]`
  - Scans `swarm_root` for subdirectories containing `swarm.toml`.

- `initialize_agent_packages(swarm_root="agents") -> Dict[str, List[AgentPackageRecord]]`
  - Startup inventory pass.
  - Reads manifests, checks required package files, creates `workspace/` folders, and registers fully configured swarms for valid packages.
  - Splits results into `valid` and `invalid`.

- `load_swarm_from_source(source) -> AgentPackageRecord`
  - Explicit runtime load from a directory or `swarm.toml`.
  - Builds the full runtime swarm, including graph import and `build_graph(...)`.

- `record_run(name, input_text, output, trace=None) -> None`
  - Appends a history record for one swarm run.

- `get_history(name, limit=20) -> List[Dict[str, Any]]`
  - Returns the most recent run history items.
  - Each history record preserves the original JSON `input` payload and JSON-safe `output` / `trace` values.

- `set_global_variables(config) -> None`
  - Accepts a dataclass, dict, or object with `values`/`visibility`.

- `get_global_variables_for_agent(agent_id) -> Dict[str, Any]`
  - Returns only the globals visible to that agent.

- `set_tool_capabilities(tool_name, capabilities) -> None`
  - Stores the allowed capability set for one tool.

- `get_tool_capabilities(tool_name) -> Set[str]`
  - Returns the stored capability set.

- `record_runtime_change(**kwargs) -> None`
  - Appends a `RuntimeChangeRecord` to the runtime-change log.

- `get_cognitive_graph_export(swarm_name, query=None, max_nodes=None) -> str`
  - Serializes the swarm thinking graph, optionally filtered.

- `get_execution_graph_snapshot(name) -> Dict[str, Any]`
  - Returns a structural snapshot of the execution graph.

- `get_thinking_graph_snapshot(name) -> Dict[str, Any]`
  - Returns a JSON-safe snapshot of the swarm thinking graph.

- `get_agent_graph_snapshot(name) -> Dict[str, Any]`
  - Compatibility alias for `get_execution_graph_snapshot(name)`.

## `modules/llm_fetcher/thinking_graph.py`

- `ThinkingGraph.serialize() -> Dict[str, Any]`
  - Produces a JSON-safe snapshot containing nodes, edges, version metadata, and transaction log entries.

- `ThinkingGraph.to_dict() -> Dict[str, Any]`
  - Backward-compatible alias for `serialize()`.

- `ThinkingGraph.from_dict(data) -> ThinkingGraph`
  - Restores a thinking graph from serialized data.
  - Rebuilds node/edge dictionaries, version counters, and the transaction log.

- `ThinkingGraph.deserialize(data) -> ThinkingGraph`
  - Alias for `from_dict(data)`.

## `modules/llm_fetcher/swarm/execution_graph.py`

- `ExecutionGraph.run(initial_input=None, entry_node_id=None, event_hook=None) -> GraphContext`
  - Executes the DAG and returns the final context.
  - `event_hook` is an optional callback that receives structured runtime events as `(event_name, payload)` pairs.
  - Emits node-level progress events when an event hook is present:
    - `run.started`
    - `node.started`
    - `node.completed`
    - `node.failed`
    - `branch.started`
    - `run.completed`
    - `run.failed`
  - The payloads are best-effort runtime snapshots and are intended for SSE forwarding, not persistence.

## `modules/llm_fetcher/swarm/swarm.py`

- `AgentSwarm.run(initial_input=None, entry_node_id=None, event_hook=None) -> GraphContext`
  - Thin orchestration wrapper around `ExecutionGraph.run(...)`.
  - Preserves the optional event hook so web clients can observe progress without coupling to the graph internals.

- `_resolve_fetcher_from_manifest(manifest, fallback_name) -> Optional[LLMFetcher]`
  - Builds an `LLMFetcher` from `[llm.default]` only when both `api_url` and `model` are present.
  - `llm.default.name` is optional; if omitted, the backend id falls back to the package/swarm name.

- `_resolve_api_key(expr) -> str`
  - Resolves `${ENV_VAR}` expressions from the environment.

## `web/server.py`

- `_resolve_swarm_root(config_path) -> str | Path`
  - Reads `[app].swarm_root` from `config.toml` when available.

- `_load_swarm_from_source(source) -> tuple[str, Any]`
  - Handles JSON snapshot loads directly.
  - Delegates TOML/directory loading to `Core.load_swarm_from_source(...)`.

- `_resolve_fetcher_from_manifest(manifest) -> Optional[LLMFetcher]`
  - Legacy helper for manifest-based backend construction.
  - Uses a fallback backend name when `llm.default.name` is absent.

- `_resolve_fetcher_from_env() -> LLMFetcher`
  - Builds a minimal backend from environment variables.

- `create_app(config_path=None) -> FastAPI`
  - Creates the API app.
  - Initializes the global `Core` package inventory before routes are served.
  - Exposes swarm load, unload, run, stop, execution graph, thinking graph, and history routes.

- `load_swarm`, `unload_swarm`, `run_swarm`, `stop_swarm`, `get_execution_graph`, `get_thinking_graph`, `get_graph`, `get_thought_graph`, `get_history`
  - Route handlers that operate on the global `Core` registry.
  - `run_swarm` records run history and streams SSE events.
  - The run stream emits both legacy compatibility events and node-level progress events:
    - Legacy: `start`, `result`, `stopped`, `error`, `done`
    - Progress: `run.started`, `node.started`, `node.completed`, `node.failed`, `branch.started`, `run.snapshot`, `run.completed`, `run.failed`
  - `POST /swarms/{name}/run` accepts a JSON `input` payload and optional `rounds` / `meta_mode` compatibility fields from the frontend.

## `app.py`

- `parse_args() -> argparse.Namespace`
  - Parses `--config`, `--host`, `--port`, and `--debug`.

- `load_config(path) -> Dict[str, Any]`
  - Reads `config.toml`.

- `_extract_bind(config) -> tuple[str, int]`
  - Derives host/port from `api.base_url`.

- `_resolve_api_token(config) -> str | None`
  - Reads the bearer token from the configured environment variable.

- `build_app(config, config_path=None) -> FastAPI`
  - Builds the final ASGI app and passes `config_path` through to the web layer.

- `main() -> None`
  - Loads config, builds the app, and starts Uvicorn.

## Package Convention

- Every agent package should keep its default workspace at `<package>/workspace/`.
- `llm.default.name` is no longer required in `swarm.toml`.
- `llm.default.api_url` and `llm.default.model` are required for a package to be considered valid at startup.
- Existing packages can still use a package-level `name`, but backend naming is now derived when needed.
- `GET /swarms/{name}/graph` remains as a compatibility alias for `execution_graph`, while `GET /swarms/{name}/thinking_graph` and `GET /swarms/{name}/thought-graph` expose the serialized thinking graph.
