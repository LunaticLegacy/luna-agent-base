# Backend Semantics

This document is a living semantic map for the backend and runtime modules.
It describes what the code does now, with function-level detail where it matters.

## Scope

Covered files:

- `app.py`
- `web/server.py`
- `core/core.py`
- `modules/llm_fetcher/__init__.py`
- `modules/llm_fetcher/llm_fetcher.py`
- `modules/llm_fetcher/llm_context.py`
- `modules/llm_fetcher/tool.py`
- `modules/llm_fetcher/agent.py`
- `modules/llm_fetcher/agent_io.py`
- `modules/llm_fetcher/thinking_graph.py`
- `modules/llm_fetcher/swarm/execution_graph.py`
- `modules/llm_fetcher/swarm/runtime_slot.py`
- `modules/llm_fetcher/swarm/swarm.py`
- `modules/llm_fetcher/tools/*.py`

## Architecture

The runtime is layered like this:

1. `app.py` starts the web server.
2. `web/server.py` exposes REST and SSE endpoints.
3. `core/core.py` manages swarm registry, runtime history, and audit bookkeeping.
4. `modules/llm_fetcher` provides the execution primitives:
   - LLM routing
   - agent turn execution
   - tools
   - execution graphs
   - thinking graphs
   - runtime slots
   - swarm orchestration
   - agent filesystem inspection

The current backend is process-local. Registry state, run history, and audit records live in memory.

## Semantic Update Rule

When backend code changes:

- reread the changed files
- update this document in the same turn
- reflect:
  - signatures
  - inputs and outputs
  - side effects
  - state mutations
  - persistence behavior
  - compatibility risks

## `app.py`

### Module role

`app.py` is the CLI entry point. It reads `config.toml`, builds the FastAPI app, applies optional auth/CORS, and starts Uvicorn.

### `parse_args() -> argparse.Namespace`

- Parses CLI flags:
  - `--config`
  - `--host`
  - `--port`
  - `--debug`
- Output:
  - raw argparse namespace
- Side effects:
  - none

### `load_config(path: Path) -> dict[str, Any]`

- Reads TOML from `path`.
- Raises `FileNotFoundError` if the file does not exist.
- Output:
  - parsed TOML mapping

### `_extract_bind(config: dict[str, Any]) -> tuple[str, int]`

- Reads `api.base_url`.
- Parses host and port from the URL.
- Default fallback:
  - host = `127.0.0.1`
  - port = `5000`
- Output:
  - `(host, port)`

### `_resolve_api_token(config: dict[str, Any]) -> str | None`

- Returns `None` unless `api.require_auth` is truthy.
- If auth is enabled, reads the token from the env var named by `api.api_token_env`.
- Default env var:
  - `ANGELUS_API_TOKEN`
- Output:
  - token string or `None`

### `build_app(config: dict[str, Any]) -> FastAPI`

- Builds the ASGI app by calling `web.create_app(config_path=None)`.
- Applies CORS middleware if `api.cors_allowed_origins` is non-empty.
- Applies bearer-token middleware if `_resolve_api_token()` returns a token.
- Stores:
  - `app.state.host`
  - `app.state.port`
  - `app.state.config`
- Output:
  - configured FastAPI app

### `main() -> None`

- Reads CLI args.
- Loads config.
- Builds the app.
- Runs Uvicorn.

## `web/server.py`

### Module role

This is the REST and SSE surface. It wraps a global `Core` instance and exposes swarm lifecycle and execution routes.

### Global state

#### `_core = Core()`

- Process-local singleton registry.
- Holds loaded swarms and in-memory run history.

### Models

#### `HealthResponse`

- Output body for `/health`.
- Shape:
  - `{status: "ok"}`

#### `SwarmInfo`

- Summary for one loaded swarm.
- Fields:
  - `name`
  - `agent_count`
  - `tool_count`

#### `SwarmListResponse`

- Response body for `/swarms`.
- Fields:
  - `swarms: list[SwarmInfo]`

#### `LoadSwarmRequest`

- Request body for `/swarms/load`.
- Fields:
  - `source: str`

#### `LoadSwarmResponse`

- Response body for `/swarms/load`.
- Fields:
  - `name`
  - `id`
  - `message`

#### `RunRequest`

- Request body for `/swarms/{name}/run`.
- Fields:
  - `input: str`
  - `context: Optional[dict[str, Any]]`

#### `RunResponse`

- Defined model for run results, but the route currently streams SSE instead of returning this model directly.

#### `GraphResponse`

- Response body for `/swarms/{name}/graph`.
- Fields:
  - `name`
  - `nodes`
  - `edges`

#### `RunRecord`

- One in-memory history row.
- Fields:
  - `timestamp`
  - `input`
  - `output`
  - `trace`

#### `HistoryResponse`

- Response body for `/swarms/{name}/history`.
- Fields:
  - `runs: list[RunRecord]`

### Helpers

#### `_resolve_api_key(expr: str) -> str`

- Expands `${ENV_VAR}` syntax into an environment lookup.
- Otherwise returns the string unchanged.
- Output:
  - resolved API key string

#### `_build_trace(ctx: Any) -> dict[str, Any]`

- If the context exposes a working `to_dict()`, uses it.
- Otherwise falls back to:
  - `executed`
  - `node_outputs`
- Output:
  - trace dictionary for debugging/UI

#### `_sse_event(event: str, data: Any) -> str`

- Serializes `data` as JSON.
- Formats a Server-Sent Events frame.
- Output:
  - `event: ...\ndata: ...\n\n`

#### `_resolve_fetcher_from_manifest(manifest: dict[str, Any]) -> LLMFetcher | None`

- Reads `llm.default` from a manifest.
- Current behavior only returns a fetcher if `api_url` exists.
- Important semantic gap:
  - a manifest with only `api_key` and `model` still resolves to `None`
- Output:
  - `LLMFetcher` or `None`

#### `_resolve_fetcher_from_env() -> LLMFetcher`

- Builds a minimal fetcher from environment variables:
  - `ANGELUS_API_KEY`
  - `OPENAI_API_KEY`
  - `MOONSHOT_API_KEY`
  - `DEEPSEEK_API_KEY`
  - `ANGELUS_PROVIDER`
  - `ANGELUS_API_URL`
  - `ANGELUS_MODEL`
- Output:
  - ready-to-use `LLMFetcher`

#### `_load_swarm_from_source(source: str) -> tuple[str, Any]`

Supported sources:

- `.json` snapshot file
- directory containing `swarm.toml`
- direct `.toml` manifest file

Behavior:

- JSON snapshot:
  - reads the snapshot
  - resolves a fetcher from env
  - calls `AgentSwarm.load(...)`
  - registers the swarm in `_core`
- TOML or directory:
  - loads manifest
  - creates swarm through `_core.create_swarm(...)`
  - optionally loads `graph.py`
  - applies global variables and tool capabilities

Output:

- `(name, swarm)`

### `create_app(config_path: Optional[Path] = None) -> FastAPI`

- Creates the FastAPI app.
- Registers routes.
- Current semantic gap:
  - `config_path` is accepted but not used inside the function

Routes and meanings:

- `GET /health`
  - returns a health status
- `GET /swarms`
  - lists registered swarms
- `POST /swarms/load`
  - loads and registers a swarm
- `DELETE /swarms/{name}`
  - unloads a swarm
- `POST /swarms/{name}/run`
  - streams run execution as SSE
- `POST /swarms/{name}/stop`
  - requests a soft or hard stop for the swarm runtime
- `GET /swarms/{name}/graph`
  - returns execution graph snapshot
- `GET /swarms/{name}/history`
  - returns recent run history

### Route semantics

#### `health() -> HealthResponse`

- Returns the fixed OK response.

#### `list_swarms() -> SwarmListResponse`

- Uses `_core.list_swarms()`.
- Output:
  - swarm summaries

#### `load_swarm(req: LoadSwarmRequest) -> LoadSwarmResponse`

- Loads a swarm from the given source.
- Registers it.
- Output:
  - metadata for the loaded swarm

#### `unload_swarm(name: str) -> JSONResponse`

- Removes the swarm from `_core`.
- Raises 404 if the swarm is missing.

#### `run_swarm(name: str, req: RunRequest) -> StreamingResponse`

- Looks up the swarm by name.
- Streams:
  - `start`
  - `result`
  - `stopped`
  - `done`
- Stores a run record in `_core`
- Output inference:
  - prefers a node ID containing `"output"`
  - otherwise falls back to the last value in `node_outputs`
- Semantic gap:
  - `req.context` is accepted by the model but not forwarded into `swarm.run(...)`

#### `stop_swarm(name: str, req: StopRequest) -> StopResponse`

- Looks up the swarm by name.
- Requests either:
  - soft stop, or
  - hard stop
- Returns the resolved stop state snapshot from the swarm's execution graph.

#### `get_graph(name: str) -> GraphResponse`

- Returns a lightweight graph snapshot from `_core.get_agent_graph_snapshot(...)`.

#### `get_history(name: str, limit: int = 20) -> HistoryResponse`

- Returns the latest `limit` records from `_core.get_history(...)`.

## `core/core.py`

### Module role

`Core` is the multi-swarm registry and audit layer. It does not execute graphs itself.

### Public aliases

#### `Node = Any`

- Compatibility alias.

#### `GraphExecutionGraph = ExecutionGraph`

- Compatibility alias.

### `GlobalVariablesConfig`

#### Fields

- `values: dict[str, Any]`
- `visibility: dict[str, list[str]]`

#### `visible_values_for_agent(agent_id: str) -> dict[str, Any]`

- Returns only values visible to the given agent.
- If a variable has no visibility list, it is visible to everyone.

### `RuntimeChangeRecord`

- Lightweight audit object.
- Fields:
  - `action`
  - `subject_kind`
  - `subject_id`
  - `detail`

### `Core`

#### `__init__()`

- Initializes:
  - `swarms`
  - `_history`
  - `_global_variables`
  - `_tool_capabilities`
  - `architecture_manager["runtime_changes"]`

#### `register_swarm(name: str, swarm: AgentSwarm) -> None`

- Stores an existing swarm.

#### `create_swarm(name: str, llm_fetcher: LLMFetcher, spec: SwarmSpec | None = None, max_concurrency: int | None = None) -> AgentSwarm`

- Creates a new swarm.
- Registers it.
- Output:
  - the new swarm

#### `get_swarm(name: str) -> AgentSwarm`

- Returns the registered swarm.
- Raises `KeyError` if missing.

#### `remove_swarm(name: str) -> None`

- Removes the swarm and its run history.

#### `list_swarms() -> list[dict[str, Any]]`

- Returns a summary list with:
  - `name`
  - `agent_count`
  - `tool_count`
  - `run_count`

#### `load_swarm_from_config(name: str, llm_fetcher: LLMFetcher, tools: list[Tool] | None = None) -> AgentSwarm`

- Creates a minimal swarm.
- Optionally registers extra tools.

#### `record_run(name: str, input_text: str, output: str, trace: dict[str, Any] | None = None) -> None`

- Appends an in-memory run record with timestamp.

#### `get_history(name: str, limit: int = 20) -> list[dict[str, Any]]`

- Returns the tail of the run history list.

#### `set_global_variables(config: Any) -> None`

- Accepts:
  - `GlobalVariablesConfig`
  - `dict`
  - objects exposing `values`, `globals`, and/or `visibility`
- Replaces the current global variable config.

#### `get_global_variables_for_agent(agent_id: str) -> dict[str, Any]`

- Returns the visible subset of global variables for one agent.

#### `set_tool_capabilities(tool_name: str, capabilities: list[str]) -> None`

- Stores a deduplicated capability set for one tool.

#### `get_tool_capabilities(tool_name: str) -> set[str]`

- Returns the registered capability set for one tool.

#### `record_runtime_change(**kwargs: Any) -> None`

- Creates a `RuntimeChangeRecord`.
- Appends it to `architecture_manager["runtime_changes"]`.

#### `get_cognitive_graph_export(swarm_name: str, query: str | None = None, max_nodes: int | None = None) -> str`

- Serializes the swarm's `ThinkingGraph` to JSON text.
- Optional `query` filters nodes by substring match on serialized content.
- Optional `max_nodes` truncates the node set.

#### `get_agent_graph_snapshot(name: str) -> dict[str, Any]`

- Returns a lightweight execution-graph snapshot.
- Includes:
  - `graph_name`
  - `graph_kind`
  - `node_count`
  - `edge_count`
  - node summaries
  - edge summaries

#### `__repr__() -> str`

- Returns a short registry summary.

## `modules/llm_fetcher/__init__.py`

### Module role

This is the public re-export layer for the runtime package.

### Semantics

- Re-exports the main runtime classes and helper factories.
- Makes both `modules.llm_fetcher` and top-level `llm_fetcher` usable as import surfaces.

### Export groups

- LLM:
  - `LLMFetcher`
  - `LLMContext`
  - `LLMBackendConfig`
  - `LLMError`
  - `LLMTimeoutError`
  - `LLMBackendError`
- Agent / tools:
  - `Agent`
  - `Tool`
  - `ToolRegistry`
- Thinking / execution:
  - `ThinkingGraph`
  - `ThinkingNodeType`
  - `ThinkingEdgeType`
  - `ExecutionGraph`
  - `AgentSwarm`
  - `SwarmSpec`
  - `RuntimeSlotManager`
- IO:
  - `AgentFileIOManager`
  - `AgentFileSnapshot`
  - `AgentFileLocations`
  - `AgentWorkspacePolicy`

## `modules/llm_fetcher/llm_fetcher.py`

### Module role

This module routes chat requests across one or more backends and normalizes errors, retries, and streaming output.

### `LLMContext`

- Minimal chat message container.
- Fields:
  - `role`
  - `content`

### `LLMBackendConfig`

- Configuration for one backend.
- Fields:
  - `name`
  - `provider`
  - `model`
  - `api_key`
  - `api_url`
  - `timeout`
  - `max_retries`
  - `extra`

### `LLMError`

- Base runtime error for the fetcher layer.

### `LLMTimeoutError`

- Raised when a backend times out.

### `LLMBackendError`

- Raised when all candidate backends fail.

### `LLMFetcher`

#### `__init__(...)`

Supports two construction styles:

1. Legacy single-backend mode:
   - `api_url`, `api_key`, `model`
2. Multi-backend mode:
   - `backends=[...]`

Semantics:

- Registers backends.
- Builds OpenAI clients for `provider == "openai"`.
- Picks a default backend.
- Stores an optional limiter.

#### `_register_backend(backend: LLMBackendConfig) -> None`

- Registers one backend.
- Raises on duplicate backend names.
- If the provider is `openai`, creates a client immediately.

#### `_resolve_backends(backend_name, fallback_order) -> list[LLMBackendConfig]`

- Produces the candidate backend order for one request.
- If `backend_name` is set, only that backend is used.
- Otherwise the default backend is tried first, then fallbacks.

#### `_build_messages(msg, prev_messages=None, system_prompt=None) -> list[dict[str, str]]`

- Builds chat messages in provider format.
- Order:
  1. system prompt
  2. previous messages
  3. current user message

#### `_create_completion(...) -> Any`

- Dispatches to the selected provider.
- OpenAI path:
  - uses prebuilt `OpenAI` client
  - sets `tool_choice="auto"` when tools are supplied
- LiteLLM path:
  - calls `litellm.completion`
- Output:
  - raw SDK completion object or stream iterator

#### `_normalize_exception(backend, exc) -> LLMError`

- Maps provider exceptions into local runtime errors.
- Timeout-like exceptions become `LLMTimeoutError`.

#### `_timeout_retry_count(backend) -> int`

- Returns at least `1`.
- Used to cap retry attempts for timeout failures.

#### `_extract_content(delta) -> str | None`

- Pulls `content` from a streaming delta object or dict.

#### `_extract_reasoning(delta) -> str | None`

- Pulls `reasoning_content` or `reasoning` from a streaming delta object or dict.

#### `_iter_stream_text(response, output_reasoning=False) -> Iterable[str]`

- Normalizes streaming chunks into text fragments.
- If `output_reasoning` is true:
  - inserts `<<<THINKING>>>`
  - emits reasoning text
  - inserts `<<<THINK_END>>>` before regular content
- Output:
  - standardized text stream

#### `fetch(...) -> Any`

- Executes a non-streaming request.
- Tries backends in order until one succeeds.
- Applies retry logic for timeout failures.
- Uses limiter acquire/release if a limiter exists.
- Output:
  - raw completion response
- Failure:
  - raises `LLMBackendError` when all backends fail

#### `fetch_stream(...) -> AsyncGenerator[str, None]`

- Executes a streaming request.
- Tries backends in order.
- If a backend fails before yielding any text, it may be retried on timeout.
- If a backend fails after yielding text, the normalized error is raised immediately.
- Output:
  - standardized text fragments

### `chat_test() -> None`

- Manual smoke test for streaming output.
- Uses a hard-coded backend configuration.
- Not part of normal runtime flow.

## `modules/llm_fetcher/llm_context.py`

### Module role

This module stores and compresses per-agent chat history.

### `LLMContext`

- One message.
- Fields:
  - `role`
  - `content`
  - `tool_call_id`

#### `to_dict() -> dict[str, str]`

- Serializes the message to a dict.
- Includes `tool_call_id` only if present.

### `LLMContextPair`

- A paired input/output record.
- Fields:
  - `context_in`
  - `context_out`

#### `to_dict() -> dict[str, LLMContext]`

- Returns the pair as a dict.

### `LLMContextCompressed`

- Compressed representation of multiple context pairs.
- Fields:
  - `abstract_msg`
  - `source`

#### `to_dict() -> dict[str, Union[str, list[LLMContextPair]]]`

- Serializes the compressed view.

### `LLMContextHandler`

Per-agent context manager.

#### `__init__(llm_handler: LLMFetcher)`

- Stores the fetcher.
- Initializes:
  - `context_dict`
  - `now_context_id`

#### `add_context(context_pair: LLMContextPair)`

- Appends one input/output pair.
- Side effect:
  - increments the context ID counter

#### `get_now_context() -> list[dict[str, str]]`

- Returns the current context in provider message format.
- Pair entries become user/assistant message pairs.
- Compressed entries become a single assistant message.

#### `get_now_context_as_single_str() -> str`

- Formats the current context as readable text.

#### `compress_context(id_list: Optional[list[int]] = None) -> bool`

- Summarizes the current context using the LLM.
- Replaces the stored context with a single compressed entry.
- Current behavior:
  - `id_list` is accepted but not actually used for selective compression

#### `get_context_by_id(id_list: list[int]) -> list[LLMInfo]`

- Returns selected entries by numeric ID.

#### `generate_memory(id_list: list[int]) -> str | None`

- Summarizes selected context into a short memory string.
- Output:
  - memory text or `None`

## `modules/llm_fetcher/tool.py`

### `Tool`

- Represents one callable tool.
- Fields:
  - `name`
  - `description`
  - `parameters`
  - `handler`

#### `execute(**kwargs) -> Any`

- Calls the handler.
- If the handler is async, awaits it.
- If the handler is sync, runs it in a thread executor.

### `ToolRegistry`

- Stores tools by name.
- Produces OpenAI-compatible tool schemas.

#### `__init__()`

- Creates an empty registry.

#### `register(tool: Tool) -> Tool`

- Adds a tool.
- Raises on duplicate names.

#### `unregister(name: str) -> Tool`

- Removes a tool.
- Raises if missing.

#### `get(name: str) -> Tool`

- Returns the registered tool.

#### `execute(name: str, arguments: dict[str, Any]) -> Any`

- Executes the named tool with the provided arguments.

#### `schemas -> list[dict[str, Any]]`

- Returns OpenAI-style tool metadata.

#### `get_prompt_hint() -> str`

- Returns a prompt block that teaches the model how to emit JSON tool calls.
- Returns an empty string when no tools are registered.

## `modules/llm_fetcher/agent.py`

### Module role

This module implements the turn-level agent loop and custom JSON tool-call protocol.

### Type aliases

- `MessageDict`
- `Messages`
- `ToolArgs`
- `AssistantMessageDict`
- `ToolList`
- `OptionalToolList`

These aliases are convenience types for message and tool structures.

### `Agent`

#### `__init__(llm_handler, system_prompt, tools=None)`

- Stores the base system prompt.
- Creates:
  - `memory_list`
  - `LLMContextHandler`
  - `ToolRegistry`
- Registers built-in tools such as `round_end`.
- Registers any provided extra tools.

#### `_register_builtin_tools() -> None`

- Registers tools returned by `create_builtin_tools()`.

#### `system_prompt -> str`

- Returns the base prompt plus the tool hint block, if any tools exist.

#### `update_system_prompt(new_prompt: str) -> None`

- Replaces the base system prompt.

#### `add_tool(tool: Tool) -> None`

- Adds one tool to the registry.

#### `remove_tool(tool_name: str) -> None`

- Removes one tool from the registry.

#### `round_call(msg, stream=False, verbose_info=False, max_turns=3) -> str`

This is the agent's main runtime loop.

Semantics:

- Builds the round message list from:
  - current system prompt
  - prior stored context
  - current user message
- Calls the LLM one or more times.
- Parses assistant content as custom JSON tool-call payloads.
- Executes any requested tools.
- Repeats until:
  - the assistant stops requesting tools
  - `round_end` is called
  - `max_turns` is reached
- After the tool loop, it performs a fallback summary call to force a final response.
- Stores the user/assistant pair into the context handler.

Important current behavior:

- If `stream=True`, fallback generation uses `fetch_stream(...)` and prints chunks.
- If the fallback response is empty, it preserves the last turn content.

#### `_strip_code_fence(text: str) -> str`

- Removes one surrounding fenced code block, if present.

#### `_parse_json_tool_calls(content: str) -> list[dict[str, Any]]`

- Parses the assistant output into tool-call objects.
- Accepts:
  - a dict with `tool_calls`
  - a single tool-call dict
  - a list of tool-call dicts
- Falls back to extracting embedded JSON fragments from free-form text.

#### `_is_valid_tool_call(payload: Any) -> bool`

- Validates the shape of one JSON tool-call object.

#### `_extract_json_fragment(text: str) -> Any | None`

- Searches the text for the first embedded JSON object or array.

#### `_build_round_messages(msg: str) -> Messages`

- Builds the round prompt messages:
  - system prompt
  - prior context
  - current user message

#### `_format_assistant_message(content: str) -> dict[str, Any]`

- Wraps assistant content as a message dict.

#### `_format_tool_result_message(tool_name: str, result: Any) -> str`

- Serializes a tool result as JSON for the next model turn.

#### `_execute_single_tool(tool_call: dict[str, Any], verbose: bool) -> str`

- Executes one tool call.
- Special-cases `round_end`.
- Catches tool errors and returns an error string instead of raising.

## `modules/llm_fetcher/agent_io.py`

### Module role

This module reads agent package structure and runtime files from the filesystem.

### `AgentWorkspacePolicy`

- Workspace rule for one agent.
- Fields:
  - `mode`
  - `root`
  - `raw_root`

### `AgentFileLocations`

- Resolved file paths for one agent.
- Fields:
  - `package_root`
  - `manifest_path`
  - `agent_file`
  - `prompt_file`
  - `skill_files`
  - `runtime_root`
  - `state_file`
  - `context_file`
  - `memory_file`
  - `log_file`

### `AgentFileSnapshot`

- Full snapshot of one agent package and its runtime files.
- Includes:
  - manifest-derived metadata
  - prompt text
  - workspace policy
  - runtime files

### `AgentFileIOManager`

#### `__init__(swarm_root="agents", manifest_name="swarm.toml", runtime_dir_name="runtime", agent_runtime_dir_name="agents")`

- Stores the root search path and naming conventions.

#### `discover_packages() -> list[Path]`

- Returns package directories under the swarm root that contain a manifest.

#### `list_agent_ids() -> list[str]`

- Scans all packages and returns unique agent IDs.

#### `read_agent_snapshot(agent_id, package_name=None, include_runtime_files=True) -> AgentFileSnapshot`

- Loads one agent's package metadata and runtime files.
- Output:
  - complete snapshot object

#### `read_agent_state(agent_id, package_name=None) -> dict[str, Any] | None`

- Returns the decoded `state.json`, if present.

#### `read_agent_context(agent_id, package_name=None) -> list[dict[str, Any]]`

- Returns the decoded `context.jsonl`.

#### `read_agent_prompt(agent_id, package_name=None) -> str`

- Returns the resolved prompt text.

#### `read_agent_log_tail(agent_id, package_name=None, max_lines=200) -> str | None`

- Returns the tail of the log file, if present.

#### `get_agent_record(agent_id, package_name=None) -> dict[str, Any]`

- Finds the manifest record for one agent.
- If the same agent ID appears in multiple packages and `package_name` is omitted, raises an ambiguity error.

#### `_load_manifest(package_root: Path) -> dict[str, Any]`

- Reads the package `swarm.toml`.

#### `_iter_agent_specs(package_root, manifest) -> Iterable[dict[str, Any]]`

- Resolves agent files from the manifest and loads all declared specs.

#### `_iter_loaded_agent_records(package_root, manifest) -> Iterable[dict[str, Any]]`

- Builds normalized per-agent record dictionaries from manifest and loaded specs.

#### `_load_agent_specs(agent_file: Path) -> list[dict[str, Any]]`

- Loads agent specs from source parsing first.
- Falls back to import-based extraction if needed.

#### `_extract_agent_specs_from_source(agent_file: Path) -> list[dict[str, Any]]`

- Parses Python source with `ast`.
- Looks for top-level `AGENT`, `AGENT_SPEC`, or `AGENTS` assignments.

#### `_extract_agent_specs_from_module(module, agent_file) -> list[dict[str, Any]]`

- Reads `AGENTS`, `AGENT_SPEC`, or `AGENT` from an imported module object.

#### `_coerce_agent_payload(payload, agent_file) -> list[dict[str, Any]]`

- Normalizes dict-or-list payloads into a list of agent spec dicts.

#### `_normalize_agent_spec(spec, agent_file) -> dict[str, Any]`

- Ensures every agent spec has an `agent_id`.
- Falls back to the file stem when missing.

#### `_load_agent_module(agent_file: Path) -> ModuleType`

- Imports the Python agent file as a module.

#### `_resolve_locations(record) -> AgentFileLocations`

- Computes package, manifest, prompt, skill, and runtime file paths.

#### `_resolve_workspace(record) -> AgentWorkspacePolicy`

- Resolves workspace mode and root from manifest data.
- Supports per-agent overrides.

#### `_resolve_runtime_root(package_root, agent_id) -> Path`

- Computes the runtime directory for one agent.

#### `_resolve_skill_files(package_root, manifest, agent_spec) -> list[Path]`

- Collects skill file paths from manifest and `skill_name` conventions.

#### `_resolve_prompt_file(package_root, agent_spec, skill_files) -> Path | None`

- Picks an explicit prompt file or a suitable skill markdown file.

#### `_resolve_prompt_text(record, locations) -> tuple[str, Path | None]`

- Resolves prompt text from:
  1. explicit `prompt_text`
  2. prompt file
  3. `character_prompt` plus skill file contents

#### `_read_json_if_exists(path) -> dict[str, Any] | None`

- Reads JSON if the file exists and the result is a dict.

#### `_read_jsonl_if_exists(path) -> list[dict[str, Any]]`

- Reads JSONL into a list of dict-like rows.

#### `_read_json_or_text_if_exists(path) -> Any | None`

- Returns parsed JSON if possible.
- Falls back to raw text otherwise.

#### `_read_log_tail_if_exists(path, max_lines=200) -> str | None`

- Returns the tail of a log file.

## `modules/llm_fetcher/thinking_graph.py`

### Module role

This module implements the shared cognitive graph: nodes, edges, schema checks, mutation history, and integrity validation.

### Types

#### `ThinkingNodeType`

- Semantic node categories such as:
  - `GOAL`
  - `QUESTION`
  - `CLAIM`
  - `HYPOTHESIS`
  - `EVIDENCE`
  - `ASSUMPTION`
  - `PLAN`
  - `STEP`
  - `ACTION`
  - `OBSERVATION`
  - `CRITIQUE`
  - `DECISION`
  - `SUMMARY`
  - `MEMORY`
  - `ARTIFACT`
  - `ERROR`

#### `ThinkingEdgeType`

- Semantic edge categories such as:
  - `SUPPORTS`
  - `OPPOSES`
  - `LEADS_TO`
  - `DERIVES_FROM`
  - `REQUIRES`
  - `ANSWERS`
  - `REFINES`
  - `CONTRADICTS`
  - `BLOCKS`
  - `PRODUCES`
  - `OBSERVES`

#### `ThinkingGraphObject`

- Base dataclass for graph objects.
- Fields:
  - `id`
  - `created_by`
  - `description`

#### `ThinkingGraphNode`

- Extends `ThinkingGraphObject`.
- Adds:
  - `node_type`
  - `info`
  - `tags`
  - `confidence`
  - `payload`

#### `ThinkingGraphEdge`

- Extends `ThinkingGraphObject`.
- Adds:
  - `edge_type`
  - `source_id`
  - `target_id`
  - `strength`

#### `ThinkingGraphTransactionRecord`

- Records one mutation.
- Fields:
  - `transaction_id`
  - `operation`
  - `object_kind`
  - `object_id`
  - `before`
  - `after`
  - `version_before`
  - `version_after`
  - `created_by`
  - `timestamp`
  - `metadata`

### `ALLOWED_EDGE_SCHEMA`

- Maps each edge type to the allowed `(source_node_type, target_node_type)` pairs.
- Used for validation in add/modify/integrity checks.

### `ThinkingGraph`

#### `__init__()`

- Validates the edge schema.
- Initializes:
  - `edge_dict`
  - `node_dict`
  - `_next_object_id`
  - `_version`
  - `_transaction_id`
  - `_transaction_log`
  - `_lock`

#### `_alloc_id() -> int`

- Returns the next object ID and increments the counter.

#### `version -> int`

- Returns the current graph version.

#### `transaction_log -> list[ThinkingGraphTransactionRecord]`

- Returns a copy of the transaction log.

#### `to_dict() -> dict[str, Any]`

- Serializes nodes, edges, version, counts, and transaction metadata.

#### `get_full_graph() -> dict[str, Any]`

- Async locked wrapper around `to_dict()`.

#### `_snapshot_object(obj) -> dict[str, Any] | None`

- Serializes dataclass, dict, or generic values for transaction logging.

#### `_next_transaction_id() -> int`

- Allocates the next transaction ID.

#### `_record_transaction(...) -> ThinkingGraphTransactionRecord`

- Appends one transaction record to the log.

#### `clear_transaction_log() -> None`

- Clears the log.

#### `get_transaction_log() -> list[ThinkingGraphTransactionRecord]`

- Returns a copy of the log.

#### `validate_edge_schema() -> None`

- Checks that the schema covers all edge types and only valid node pairs.

#### `add_node(...) -> int`

- Validates node input.
- Adds a node under lock.
- Increments version.
- Records a transaction.
- Output:
  - new node ID

#### `_validate_node_input(...) -> None`

- Validates:
  - node type
  - non-empty info
  - non-empty creator
  - tag list shape
  - finite confidence
  - payload dict shape

#### `add_edge(...) -> int`

- Validates input.
- Ensures source and target nodes exist.
- Checks edge schema against source and target node types.
- Adds the edge under lock.
- Increments version.
- Records a transaction.
- Output:
  - new edge ID

#### `modify_node(...) -> ThinkingGraphNode`

- Rebuilds a node with updated fields.
- Revalidates the merged data.
- Replaces the stored node.
- Increments version.
- Records changed fields in transaction metadata.

#### `modify_edge(...) -> ThinkingGraphEdge`

- Rebuilds an edge with updated fields.
- Revalidates the merged data and schema.
- Replaces the stored edge.
- Increments version.
- Records changed fields in transaction metadata.

#### `_validate_edge_input(...) -> None`

- Validates:
  - edge type
  - source/target integer IDs
  - no self-loop
  - non-empty creator
  - finite strength

#### `_is_edge_allowed(...) -> bool`

- Checks whether a `(source_type, target_type)` pair is allowed for one edge type.

#### `validate_incremental_context(center_id, max_hops=1) -> None`

- Performs a local consistency check around a node.
- Checks:
  - node validity
  - edge validity
  - edge schema compliance
  - local semantic conflicts
- Useful after incremental updates.

#### `validate_graph_integrity() -> None`

- Performs a full graph scan.
- Verifies:
  - object ID consistency
  - uniqueness
  - node validity
  - edge validity
  - edge endpoints
  - edge schema compliance

## `modules/llm_fetcher/swarm/execution_graph.py`

### Module role

This module is the actual execution engine. It manages topology, scheduling, node execution, routing, persistence, and checkpoint/restart.

### `Edge`

- Graph edge.
- Fields:
  - `source_id`
  - `target_id`
  - `label`

### `GraphContext`

#### `__init__(graph)`

- Stores the graph reference.
- Initializes:
  - `node_inputs`
  - `node_outputs`
  - `executed`
  - `metadata`

#### `get_output(node_id) -> Any`

- Returns the recorded output for a node.

#### `get_inputs(node_id) -> list[Any]`

- Returns the recorded inputs for a node.

### `ExecutionNode`

Abstract base node.

#### `__init__(node_id, node_type)`

- Stores node identity and type.

#### `run(ctx, inputs) -> Any`

- Abstract node execution method.

### `AgentNode`

#### `__init__(node_id, agent)`

- Wraps an `Agent`.

#### `run(ctx, inputs) -> str`

- Converts inputs into a text prompt.
- Calls `agent.round_call(...)`.
- Output:
  - agent text response

### `ToolNode`

#### `__init__(node_id, tool)`

- Wraps a `Tool`.

#### `run(ctx, inputs) -> Any`

- Converts inputs into tool arguments.
- Calls `tool.execute(...)`.
- On exception, returns an error dict instead of raising.

### `RouterNode`

#### `__init__(node_id, routes, agent=None, default_route=None)`

- Stores routing table.
- Optional agent can be used to select a route.

#### `run(ctx, inputs) -> dict[str, Any]`

- If an agent exists and there are multiple routes:
  - asks the agent to pick a route label
- Otherwise:
  - returns the default route

### `InputNode`

#### `run(ctx, inputs) -> Any`

- Returns the first input value or `None`.

### `OutputNode`

#### `__init__(node_id, collector=None)`

- Stores an optional collector callable.

#### `run(ctx, inputs) -> Any`

- Calls the collector on the input list.

### `JoinNode`

#### `__init__(node_id, strategy="all")`

- Stores a merge strategy.

#### `run(ctx, inputs) -> dict[str, Any]`

- `first` strategy returns the first input.
- `all` strategy returns all inputs plus count.

### `ExecutionGraph`

#### `__init__(llm_fetcher=None, max_concurrency=None)`

- Initializes:
  - `_nodes`
  - `_edges`
  - `_lock`
  - `_node_counter`
  - `_llm_fetcher`
  - `_tool_pool`
  - `_semaphore`
  - `_node_timeouts`
  - `_version`
  - `_stop_state`
  - `_active_run_tasks`
  - `_active_run_task`
  - `_active_run_ctx`

#### `_bump_version(action, **detail) -> None`

- Increments the graph version after structural changes.
- The current implementation only increments the counter.

#### `version -> int`

- Returns the current graph version.

#### `stop_state -> dict[str, Any]`

- Returns a read-only snapshot of the current stop state.

#### `request_soft_stop(reason=None) -> None`

- Requests a cooperative stop.
- Current nodes finish, but downstream scheduling stops.

#### `request_hard_stop(reason=None) -> None`

- Requests an immediate stop.
- Cancels active worker tasks and the active graph run task.

#### `clear_stop_requests() -> None`

- Resets the stop state to the idle default.

#### `_alloc_id(prefix="node") -> str`

- Allocates a unique node ID.

#### `_upstream_of(node_id) -> set[str]`

- Returns the set of upstream node IDs.

#### `_downstream_of(node_id) -> list[Edge]`

- Returns downstream edges for a node.

#### `_find_entry_nodes() -> list[str]`

- Returns nodes with no upstream dependencies.

#### `register_tool(tool) -> None`

- Adds a tool to the global tool pool.

#### `unregister_tool(tool_name) -> Tool`

- Removes a tool from the pool.

#### `get_tool(tool_name) -> Tool`

- Returns a tool from the pool.

#### `tool_pool -> dict[str, Tool]`

- Returns a copy of the global pool.

#### `add_agent_node(node_id, agent) -> str`

- Inserts an `AgentNode`.
- Returns the node ID.

#### `add_tool_node(tool, node_id=None) -> str`

- Inserts a `ToolNode`.
- Returns the node ID.

#### `add_router_node(routes, agent=None, default_route=None, node_id=None) -> str`

- Inserts a `RouterNode`.

#### `add_input_node(node_id=None) -> str`

- Inserts an `InputNode`.

#### `add_output_node(collector=None, node_id=None) -> str`

- Inserts an `OutputNode`.

#### `add_join_node(strategy="all", node_id=None) -> str`

- Inserts a `JoinNode`.

#### `remove_node(node_id) -> None`

- Removes a node and all edges connected to it.
- Also removes any node timeout entry.

#### `get_node(node_id) -> ExecutionNode`

- Returns a node by ID.

#### `nodes -> dict[str, ExecutionNode]`

- Returns a copy of the node mapping.

#### `edges -> list[Edge]`

- Returns a copy of the edge list.

#### `connect(source_id, target_id, label=None) -> None`

- Adds a directed edge.
- Raises if either endpoint is missing.

#### `disconnect(source_id, target_id, label=None) -> None`

- Removes matching edges.

#### `update_agent_prompt(node_id, system_prompt) -> None`

- Mutates the underlying agent's prompt.

#### `add_tool_to_agent(node_id, tool_name) -> None`

- Adds a pooled tool to an agent node.

#### `remove_tool_from_agent(node_id, tool_name) -> None`

- Removes a tool from an agent node.

#### `set_node_timeout(node_id, timeout) -> None`

- Stores a per-node timeout.

#### `run(initial_input=None, entry_node_id=None) -> GraphContext`

This is the graph scheduler.

Semantics:

- Builds a fresh `GraphContext`.
- Chooses an entry node:
  - explicit `entry_node_id`, or
  - the first node with no upstream dependencies
- Seeds the entry input if `initial_input` is provided.
- Starts nodes once all upstream dependencies are satisfied.
- Uses an event-driven loop:
  - completion of one node can trigger downstream nodes
- Supports:
  - concurrency limits
  - node-level timeout handling
  - conditional routing via edge labels
- Stop behavior:
  - soft stop lets the current node finish, then prevents downstream scheduling
  - hard stop cancels active work and raises `asyncio.CancelledError`
- Output:
  - the completed `GraphContext`

#### `_run_node_with_timeout(nid, ctx) -> Any`

- Runs one node.
- Applies node-specific timeout if configured.

#### `_extract_route(result) -> str | None`

- Reads a `route` value from dict outputs.

#### `add_node(node) -> None`

- Compatibility API.
- Inserts an existing node object.

#### `add_edge(from_node_id, to_node_id, label=None, condition=None, priority=0) -> None`

- Compatibility API.
- Adds an edge between existing nodes.
- Also updates `next_node_ids` if the source node exposes that attribute.

#### `set_entry(node_id) -> None`

- No-op compatibility method.
- Entry nodes are auto-detected.

#### `set_exit(node_id) -> None`

- No-op compatibility method.
- Exit nodes are auto-detected.

#### `snapshot() -> dict[str, Any]`

- Serializes the static graph configuration.
- Includes:
  - node type info
  - edges
  - node timeouts
  - tool names
  - version

#### `restore(data, llm_fetcher=None, tool_pool=None, agent_map=None) -> ExecutionGraph`

- Restores graph topology from a snapshot dict.
- Re-links live `Agent` and `Tool` objects when provided.
- Skips nodes whose live dependencies are missing.

#### `checkpoint(ctx) -> dict[str, Any]`

- Extends `snapshot()` with runtime progress.
- Includes:
  - executed nodes
  - node outputs
  - node inputs

#### `resume(checkpoint) -> GraphContext`

- Rebuilds a `GraphContext` from a checkpoint dict.
- Does not execute anything by itself.

#### `to_dict() -> dict[str, Any]`

- Returns a lightweight introspection snapshot.
- Not round-trippable.
- Includes `stop_state` for runtime visibility.

## `modules/llm_fetcher/swarm/runtime_slot.py`

### Module role

This module manages background task slots and integrates slot lifecycle with `ThinkingGraph`.

### `SlotStatus`

- Enum values:
  - `PENDING`
  - `RUNNING`
  - `COMPLETED`
  - `FAILED`
  - `TIMEOUT`
  - `CANCELLED`

### `RuntimeSlot`

- Stores one background task's state.
- Fields:
  - `slot_id`
  - `name`
  - `task_coro`
  - `status`
  - `result`
  - `error`
  - `timeout`
  - `stop_requested`
  - timestamps
  - `poll_count`
  - `metadata`
  - thinking-graph node IDs

#### `to_dict() -> dict[str, Any]`

- Returns a safe summary view.
- Truncates large results.

### `RuntimeSlotManager`

#### `__init__(thinking_graph=None, default_timeout=300.0, max_concurrent=4)`

- Creates the slot registry.
- Stores an optional thinking graph for audit integration.

#### `submit(tool, arguments, name=None, timeout=None, metadata=None) -> str`

- Creates a slot for one tool invocation.
- Starts execution immediately in the background.
- If a thinking graph is attached:
  - records an `ACTION` node
- Output:
  - new slot ID

#### `_run_slot(slot) -> None`

- Runs the slot coroutine under semaphore and timeout control.
- On success:
  - stores result
  - marks completed
  - writes an `OBSERVATION` node if thinking graph is attached
  - connects action to observation with `PRODUCES`
- On timeout:
  - marks `TIMEOUT`
  - records an `ERROR` node and `BLOCKS` edge
- On cancellation:
  - marks `CANCELLED`
  - re-raises cancellation
- On other exceptions:
  - marks `FAILED`
  - records an error node

#### `request_soft_stop(slot_id) -> bool`

- Requests a cooperative stop for one running slot.
- Cancels the task and waits for it to unwind before returning.

#### `request_hard_stop(slot_id) -> bool`

- Requests an immediate stop for one running slot.
- Cancels the task and returns without waiting.

#### `cancel(slot_id) -> bool`

- Alias for hard stop.

#### `soft_stop(slot_id) -> bool`

- Alias for soft stop.

#### `hard_stop(slot_id) -> bool`

- Alias for hard stop.

#### `_record_error(slot, kind) -> None`

- Adds an `ERROR` node and a blocking edge in the thinking graph.

#### `poll(slot_id) -> RuntimeSlot`

- Returns the current slot snapshot.
- Updates `last_polled_at` and `poll_count`.

#### `list_slots(status_filter=None) -> list[RuntimeSlot]`

- Lists all slots, optionally filtered by status.

#### `collect(slot_id) -> Any`

- Returns the final result for a finished slot.
- Removes the slot from memory.
- Raises if the slot is still pending/running.

#### `cancel(slot_id) -> bool`

- Requests cancellation of a running slot.
- Output:
  - `True` if cancellation was requested, else `False`

#### `to_dict() -> dict[str, Any]`

- Returns a snapshot of:
  - slot count
  - active task count
  - per-slot summaries

#### `__repr__() -> str`

- Returns a short slot-manager summary string.

## `modules/llm_fetcher/swarm/swarm.py`

### Module role

This module is the swarm orchestration layer. It binds graphs, agents, tools, and shared cognitive state into one runtime object.

### `SwarmSpec`

- Metadata container for one swarm.
- Fields:
  - `name`
  - `description`
  - `version`
  - `metadata`

### `AgentSwarm`

#### `__init__(llm_fetcher, name="default", spec=None, max_concurrency=None)`

- Creates a fresh swarm.
- Initializes:
  - `ExecutionGraph`
  - `ThinkingGraph`
  - `ToolRegistry`
  - agent registry
  - runtime counters

#### `from_existing(...) -> AgentSwarm`

- Reuses live graph, agents, tool registry, and optional thinking graph.
- Intended for restoration or object handoff.
- If `llm_fetcher` is omitted:
  - infers it from existing agents or the graph

#### `_merge_existing_agents(execution_graph, agents) -> dict[str, Agent]`

- Collects agents from `AgentNode` objects.
- Merges any explicit overrides.

#### `_infer_llm_fetcher(agents, execution_graph) -> LLMFetcher | None`

- Searches existing agents first.
- Falls back to the graph's internal fetcher.

#### `name -> str`

- Returns the swarm name.

#### `spec -> SwarmSpec`

- Returns the swarm spec.

#### `agents -> dict[str, Agent]`

- Returns a shallow copy of the agent registry.

#### `tool_schemas -> list[dict[str, Any]]`

- Returns the tool registry's OpenAI-compatible schemas.

#### `add_tool(tool) -> AgentSwarm`

- Registers a global tool.
- Also registers it in the execution graph's tool pool.

#### `add_tools(tools) -> AgentSwarm`

- Registers multiple tools.

#### `remove_tool(tool_name) -> Tool`

- Removes a global tool.
- Also removes it from the execution graph's tool pool.

#### `add_agent(...) -> AgentSwarm`

- Creates an `Agent`.
- Injects:
  - global tools
  - optional thinking-graph tools
  - optional execution-graph tools
  - per-agent extras
- Registers the agent and inserts an `AgentNode`.

#### `remove_agent(node_id) -> None`

- Removes the agent and the corresponding graph node.

#### `get_agent(node_id) -> Agent`

- Returns the registered agent.

#### `update_agent_prompt(node_id, system_prompt) -> AgentSwarm`

- Delegates prompt mutation to the execution graph.

#### `add_tool_to_agent(node_id, tool_name) -> AgentSwarm`

- Delegates tool injection to the execution graph.

#### `remove_tool_from_agent(node_id, tool_name) -> AgentSwarm`

- Delegates tool removal to the execution graph.

#### `add_input(node_id="input") -> AgentSwarm`

- Inserts an input node.

#### `add_output(node_id="output", collector=None) -> AgentSwarm`

- Inserts an output node.

#### `add_router(node_id, routes, agent=None, default_route=None) -> AgentSwarm`

- Inserts a router node.

#### `add_join(node_id, strategy="all") -> AgentSwarm`

- Inserts a join node.

#### `add_tool_node(tool_name, node_id=None) -> AgentSwarm`

- Inserts a tool node from the global pool.

#### `connect(source_id, target_id, label=None) -> AgentSwarm`

- Adds a graph edge.

#### `disconnect(source_id, target_id, label=None) -> AgentSwarm`

- Removes a graph edge.

#### `set_timeout(node_id, seconds) -> AgentSwarm`

- Sets a node timeout in the execution graph.

#### `request_soft_stop(reason=None) -> AgentSwarm`

- Delegates a cooperative stop request to the execution graph.

#### `request_hard_stop(reason=None) -> AgentSwarm`

- Delegates an immediate stop request to the execution graph.

#### `clear_stop_requests() -> AgentSwarm`

- Clears any pending stop requests on the execution graph.

#### `run(initial_input=None, entry_node_id=None) -> GraphContext`

- Runs the swarm's execution graph.
- Increments run count.
- Stores the last context.
- Output:
  - completed `GraphContext`

#### `last_context -> GraphContext | None`

- Returns the last run context.

#### `save(path) -> None`

- Writes a JSON snapshot to disk.
- Snapshot includes:
  - spec
  - execution graph snapshot
  - thinking graph snapshot
  - agent configs
  - run count

#### `load(path, llm_fetcher, tool_pool=None) -> AgentSwarm`

- Restores a swarm from a JSON snapshot.
- Rebuilds live agents and graph nodes.
- If the snapshot is a checkpoint:
  - also restores runtime context

#### `checkpoint(ctx=None, path=None) -> dict[str, Any]`

- Serializes runtime progress and static state together.
- If `ctx` is omitted:
  - uses `last_context`

#### `resume(checkpoint) -> GraphContext`

- Restores runtime state from a checkpoint dict.

#### `to_dict() -> dict[str, Any]`

- Returns a lightweight debugging snapshot.

#### `__repr__() -> str`

- Returns a short swarm summary string.

## `modules/llm_fetcher/tools/*.py`

### `builtin_tools.py`

#### `create_builtin_tools() -> list[Tool]`

- Returns built-in agent lifecycle tools.
- Current built-in tool:
  - `round_end`
- `round_end` simply returns `"Round ended."`

### `thinking_graph_tools.py`

#### `create_thinking_graph_tools(graph: ThinkingGraph) -> list[Tool]`

- Wraps thinking-graph operations as tools.
- Exposes:
  - add node
  - add edge
  - validate local context
  - query node info
  - query schema rules
  - dump full graph summary

### `execution_graph_tools.py`

#### `create_execution_graph_tools(graph: ExecutionGraph) -> list[Tool]`

- Wraps execution-graph mutation operations as tools.
- Exposes:
  - add agent node
  - remove node
  - connect/disconnect nodes
  - update agent prompt
  - add/remove tool on agent
  - add tool node
  - set node timeout
  - graph info

### `runtime_slot_tools.py`

#### `create_runtime_slot_tools(manager: RuntimeSlotManager) -> list[Tool]`

- Wraps slot polling and collection operations as tools.
- Exposes:
  - slot poll
  - slot list
  - slot collect
  - slot cancel
  - slot soft stop
- Semantics:
  - `slot_cancel` maps to hard stop
  - `slot_soft_stop` maps to cooperative soft stop
- Note:
  - `slot_submit` is described in the comments but is not yet exposed as a real tool

### `shell_tools.py`

#### `create_shell_tools() -> list[Tool]`

- Returns a shell execution tool.
- Tool:
  - `shell`
- Behavior:
  - runs a shell command
  - captures stdout/stderr/exit code
  - blocks a few obviously destructive command strings

### `obscura_tools.py`

#### `_obscura_fetch_cli(**kwargs) -> dict[str, Any]`

- Executes `obscura fetch` via shell.
- Returns:
  - url
  - mode
  - exit code
  - stdout
  - stderr
  - ok flag

#### `_obscura_scrape_cli(**kwargs) -> dict[str, Any]`

- Executes `obscura scrape` via shell.
- Parses JSON output when possible.

#### `ObscuraCDPClient`

- Placeholder for a future CDP client.
- Currently only stores host and port.

#### `create_obscura_tools() -> list[Tool]`

- Returns:
  - `web_fetch`
  - `web_scrape`

### `tools/__init__.py`

- Lightweight package initializer.
- Uses lazy attribute loading to avoid circular imports.
- Semantically, it only re-exports tool factory functions.

## Current Backend Gaps

These are real semantic gaps in the current code:

1. `RunRequest.context` is accepted but not passed into `swarm.run(...)`.
2. `_resolve_fetcher_from_manifest()` only resolves a fetcher when `api_url` exists.
3. `create_app(config_path=...)` accepts `config_path` but does not use it.
4. `run_swarm()` infers the output heuristically rather than from an explicit API contract.
5. `Core` and run history are process-local and will reset on restart.
6. `runtime_slot_tools.py` exposes polling and collection, but not a real submit tool yet.
7. `LLMContextHandler.compress_context()` accepts `id_list` but currently compresses the full context.

## Maintenance Rule

If you change any of the modules above, update this document immediately so the semantics stay aligned with the code.
