# Workflow Hardening Plan

This document records the current backend workflow risks and the concrete repair
plan before implementation. It is intentionally implementation-facing: each
section maps the current code path to the fix that should be applied.

## Scope

The hardening thread covers these runtime surfaces:

- HTTP API exposure and CORS behavior
- swarm package loading and Python module execution
- tool capability boundaries
- execution graph mutation
- file write permissions
- private workspace persistence
- thought graph prompt injection
- report publishing contracts
- runtime audit data
- test discovery and regression coverage

## Implementation Status

Implemented in the current hardening pass:

- run-scoped private workspace paths for graph runs
- `final_answer` / `final_report` promotion for publisher output
- tool result replay into the next LLM call
- package-relative workspace root resolution
- relative file writes resolved inside workspace roots
- non-edge routing rejection, with a narrow transient-node exception for `graph_editor`
- package loading restricted to configured `swarm_root`
- graph file, agent file, skill file, prompt file, and skill content file path boundary checks
- tool module loading restricted to the swarm package or project `tools/`
- sensitive path denial for `file_writer`, including `.git` and virtualenv directories
- runtime-info secret redaction and prompt/content truncation
- optional dependency package imports made lazy for test discovery
- hardcoded swarm API keys moved back to environment-variable references
- token auth for mutating/high-risk HTTP routes
- configurable CORS allowlist enforcement
- central tool capability policy
- full clone-validate-commit graph editing
- disabling automatic tool requirement installation during normal runtime loading

Still planned:

- frontend settings UI for auth/CORS fields, if those should be editable from the browser
- splitting graph persistence into separate runtime-only and persistent-write capabilities

## Current Code Logic

### HTTP API

`app.py` starts the Flask app on `127.0.0.1` by default. `web/app_factory.py`
registers all API blueprints and installs `web/security.py`.

`web/security.py` protects high-risk API methods under `/api/*`:

- `POST`
- `PUT`
- `PATCH`
- `DELETE`

When `[api].require_auth = true` or a token is configured, high-risk requests
must include either `Authorization: Bearer <token>` or
`X-Angelus-Token: <token>`. Read-only `GET` routes and health/readiness remain
public by default. CORS is allowlist-based through
`[api].cors_allowed_origins`; the server no longer unconditionally returns
`Access-Control-Allow-Origin: *`.

The routes under `web/routes/swarms.py` expose high-impact actions:

- load a swarm package
- reload or unload a swarm
- start a synchronous or background run
- stream run events
- call one agent round directly

The settings routes in `web/routes/settings.py` can update API settings in
`config.toml`. Security fields are preserved when older frontend payloads only
send display/runtime settings.

### Swarm Loading

`web/runtime.py` resolves swarm packages only under configured `swarm_root`.
Existing absolute directories outside that root are rejected.

Manifest paths are constrained to trusted roots:

- graph, agent, skill, prompt, and skill-content files must stay inside the swarm package
- package-local tool modules must stay inside the package
- shared project tools must resolve under the project `tools/` directory

`core/swarm_spec.py` loads agent Python files with `importlib`, which executes
the file during loading. This is expected for trusted local packages, but it is
also a code execution boundary.

### Tool Execution

`core/toodefl.py` passes `ToolContext` into tools. The context includes:

- agent id
- execution node id
- workspace mode/root
- runtime metadata
- core reference
- graph reference
- granted tool capabilities

Capabilities come from `[tool_capabilities]` in `swarm.toml`. High-risk tools
call `require_tool_capability()` before doing privileged work.

The high-risk tools are:

- `tools/agent_manager_tool.py`
- `tools/graph_editor_tool.py`
- `tools/file_writer_tool.py`

`agent_manager` can create and destroy runtime agents. `graph_editor` can mutate
the live execution graph and persist it back to the source graph file.
`file_writer` can write files. `web_search` can reach the network. The required
capabilities are:

- `file_writer`: `file_write`
- `graph_editor`: `graph_mutation`
- `agent_manager`: `agent_lifecycle`
- `web_search`: `network_access`
- configuration file writes through `file_writer`: `config_write`

### Execution State

`core/executor.py` carries content through `ExecutionState.payload` and stores
auxiliary state in `ExecutionState.metadata`.

Recent report-preservation logic now stores report text in:

- `draft_report`
- `approved_report`
- `final_report`
- `latest_report`

Routing is still controlled by structured output fields such as:

- `next_node_id`
- `next_node_ids`
- `branch`
- `branches`

General structured output fields are still copied into metadata unless they are
on the executor's skip list.

### Private Workspace

Each agent has a run-scoped private directory under:

```text
.angelus_private/runs/<run_id>/<agent_id>/
```

`core/agent.py` can persist private thought snapshots there. `core/core.py`
injects a private workspace summary into each agent prompt.

Manual, direct agent calls that do not belong to a graph run use:

```text
.angelus_private/manual/<agent_id>/
```

`Core.reset_runtime_state()` clears in-memory agent context and the shared
thought graph. Because normal graph runs use run-scoped private directories, a
fresh run no longer reads previous run artifacts by default.

### Thought Graph

`core/cognitive.py` models shared reasoning as a cognitive/thought graph. The
runtime can create schedulable subgraph descriptors and inject:

- main shared graph summary
- active subgraph slice
- private workspace summary

Agent-produced `<cognitive_graph>` blocks are merged from the agent private graph
into the shared graph.

### Runtime Info

`core/runtime_info.py` writes runtime events to:

- `runtime_info/current.json`
- `runtime_info/events.jsonl`

Tool metadata may include prompt text, graph mutation detail, agent lifecycle
data, and other task context.

## Confirmed Problems

### 1. Private Workspace Can Reintroduce Context Pollution

Old private workspace files can be injected into a later run because they are
not run-scoped and not cleared during `reset_runtime_state()`.

Fix:

- [x] make private workspace paths run-scoped
- [x] pass `run_id` into graph execution and agent prompt construction
- store transient private thought data under:

```text
.angelus_private/runs/<run_id>/<agent_id>/
```

- keep durable private memory under a separate explicit path, for example:

```text
.angelus_private/memory/<agent_id>/
```

- [x] do not inject durable memory unless the run explicitly opts in

### 2. High-Risk API Routes Are Unprotected

The API can load swarms, modify settings, start runs, reload packages, and call
agents directly without authentication.

Fix:

- [x] add a simple API token gate for mutating and high-risk routes
- [x] keep health/readiness public
- [x] make token configurable through environment and/or `config.toml`
- [x] reject unsafe methods without a valid token when auth is enabled
- [x] narrow CORS to configured origins instead of `*`

### 3. Swarm Loading Accepts Arbitrary Existing Directories

`RuntimeRegistry.resolve_package_path()` accepts any existing local directory.
Loading that directory executes Python files referenced by the manifest.

Fix:

- [x] restrict package loading to the configured `swarm_root`
- [x] reject absolute paths outside `swarm_root`
- keep a development override behind an explicit unsafe flag if needed
- document that swarm packages are trusted code

### 4. Tool Capability Is Not Centrally Enforced

Any agent with a bound high-risk tool can mutate graph/runtime state or write
files according to that tool's internal behavior.

Fix:

- [x] extend `ToolContext` with capability data
- [x] add central capability enforcement through `require_tool_capability()`
- [x] classify tools by capability:
  - `file_write`
  - `graph_mutation`
  - `agent_lifecycle`
  - `network_access`
  - `thought_graph_write`
- [x] deny high-risk capabilities by default
- [x] allow capabilities from `swarm.toml`
- [x] prevent tools from granting stronger permissions than the agent already has

### 5. Runtime Agent Creation Can Escalate Workspace Access

`agent_manager` can read `workspace_mode` and `workspace_root` from model/tool
payloads when creating agents.

Fix:

- [x] spawned agents inherit the caller's maximum permission
- [x] a tool call may only narrow permissions, not widen them
- [x] manifest policy remains the source of truth
- [x] reject runtime `full_access` escalation from LLM-produced payloads

### 6. Graph Mutation Is Not Transactional

`graph_editor` mutates the live graph, validates, then persists. If validation or
persistence fails after partial mutation, the graph may remain changed.

Fix:

- [x] clone the graph before mutation
- [x] apply edits to the clone
- [x] validate the clone
- [x] persist only after validation succeeds
- [x] commit the clone back to runtime atomically
- [x] restore the previous graph if persistence fails

### 7. File Writes Need More Guardrails

`file_writer` enforces workspace boundaries in `workspace` mode, but
`full_access` is broad.

Fix:

- keep workspace mode as default
- [x] add denylist protection even in `full_access`
- [x] block writes to sensitive paths unless explicitly allowed:
  - `.git/`
  - virtualenv directories
  - shell startup files
  - root-level config files unless the caller has `config_write`
- write through atomic temp-file replacement where practical
- record file write audit events

### 8. Publisher Output Contract Is Inconsistent

Some publisher prompts use `final_answer` for the full report and `content` for a
status string. The executor and `file_writer` mostly route `content` or `input`.

Fix:

- standardize report output fields:
  - `final_report`: full final report
  - `content`: only used as fallback content
  - `status`: status text
- [x] update executor to promote `final_answer` to `final_report`
- [x] update `file_writer` tool arguments before publish nodes so it writes the
  report field, not the status field
- update publisher prompts to use the same schema

### 9. Metadata Control Fields Can Leak Across Nodes

Structured output fields are copied into shared `state.metadata`, and tools can
read fallback values from metadata. Old `spawn`, `graph_edit`, or node ids can
affect later nodes.

Fix:

- namespace metadata:
  - `metadata["report"]`
  - `metadata["control"]`
  - `metadata["tool_state"]`
  - `metadata["thought"]`
- make control metadata short-lived
- clear control fields after the tool/action that consumes them
- avoid global fallback to old metadata for high-risk fields

### 10. Runtime Info Can Persist Sensitive Prompt Data

Tool metadata may include full prompts and task content, and runtime_info stores
it in JSONL.

Fix:

- [x] add sanitization before runtime_info writes
- [x] truncate prompt/content fields
- [x] redact configured secret patterns
- [x] avoid storing full `spawned_agent_prompt` by default

### 11. Test Discovery Imports Optional Runtime Modules

`python -m unittest discover` imports optional module packages and fails if
`asyncpg` or `redis` are not installed.

Fix:

- restrict test discovery to `tests/`
- [x] make optional modules lazy-import dependencies
- [x] document the canonical test command

## Implementation Phases

### Phase 1: Stop Context Pollution

Files:

- `core/agent.py`
- `core/core.py`
- `core/executor.py`
- `web/runs.py`
- `tests/test_thought_graph.py`

Tasks:

- [x] pass `run_id` into private workspace context
- [x] move transient private artifacts under `.angelus_private/runs/<run_id>/`
- [x] prevent non-opt-in durable memory injection
- [x] add regression test proving run B does not see run A private notes

### Phase 2: Secure API Entry Points

Files:

- `web/app_factory.py`
- `web/routes/swarms.py`
- `web/routes/settings.py`
- `web/runtime.py`
- `core/swarm_spec.py`
- `docs/backend/app-and-routes.md`

Tasks:

- [ ] add token auth for mutating routes
- [ ] configure allowed CORS origins
- [x] restrict `load_swarm` path resolution to `swarm_root`
- [ ] add tests for authorized and unauthorized mutation attempts

### Phase 3: Add Tool Capability Policy

Files:

- `core/toodefl.py`
- `core/swarm_spec.py`
- `core/swarm_loader.py`
- `core/core.py`
- `tools/agent_manager_tool.py`
- `tools/graph_editor_tool.py`
- `tools/file_writer_tool.py`

Tasks:

- define capability taxonomy
- parse allowed capabilities from `swarm.toml`
- pass capabilities through `ToolContext`
- enforce capabilities at tool entry
- prevent runtime permission escalation

### Phase 4: Make Graph Mutation Transactional

Files:

- `tools/graph_editor_tool.py`
- `core/policy.py`
- `core/core.py`
- `tests/test_executor_publish_chain.py` or a new graph-editor test module

Tasks:

- mutate cloned graphs
- validate before commit
- persist after validation
- rollback on failure
- add regression tests for failed edits

### Phase 5: Normalize Publishing

Files:

- `core/executor.py`
- `tools/file_writer_tool.py`
- `agents/deepseek_demo/skills/publisher.prompt.md`
- `agents/docs_verifier/skills/publisher.prompt.md`
- `tests/test_executor_publish_chain.py`

Tasks:

- [x] support `final_report` and `final_answer`
- [x] keep `content` as fallback only
- [x] ensure publish file nodes write full reports
- [x] add `docs_verifier` style regression test

### Phase 6: Sanitize Runtime Info

Files:

- `core/runtime_info.py`
- `tools/agent_manager_tool.py`
- `tools/graph_editor_tool.py`

Tasks:

- [x] redact secrets
- [x] truncate prompt/content fields
- [x] avoid logging full generated prompts by default
- [x] add tests for sanitized event output

### Phase 7: Stabilize Test Workflow

Files:

- optional module `__init__.py` files
- `README.md`
- `docs/backend/runtime.md`

Tasks:

- [x] define canonical test command
- [x] prevent optional dependency imports during discovery
- [ ] document optional dependency behavior

## Acceptance Criteria

The hardening work is complete when:

- a fresh run cannot see private workspace artifacts from a previous run unless
  explicitly resumed
- mutating API routes require authorization
- CORS is not globally open by default
- swarm loading cannot execute packages outside `swarm_root`
- high-risk tools are capability-gated
- spawned agents cannot escalate workspace or tool permissions
- graph mutations are clone-validate-commit operations
- publish nodes write complete reports, not status strings
- runtime_info does not persist full prompts or secrets
- the canonical test command passes without optional service dependencies
