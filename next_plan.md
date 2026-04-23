# Next Plan

This file records the next round of work so we can continue without depending on the full conversation context.

## Current Situation

We need a mixed settings model:

- `config.toml` should persist API configuration.
- `localStorage` should persist frontend-only preferences.
- The Settings page should use a real settings API instead of pretending everything is already backed by storage.

Right now the Settings page shows more options than the backend actually supports, and the save button only updates frontend runtime state.

## What Is Real Today

### Frontend settings shown in the UI

- `后端 API 地址`
- `API 超时 (秒)`
- `SSE 重连间隔 (秒)`
- `自动重连 SSE 流`
- `深色模式`
- `紧凑布局`
- `显示调试信息`
- `语言`

### Current behavior

- `后端 API 地址` currently affects runtime behavior in the frontend.
- The other API-related controls are visible but not yet backed by real config persistence.
- The display controls are visible but not yet fully tied to browser persistence in a consistent way.

### Current backend config

`config.toml` currently only exposes:

- `[app].swarm_root = "agents"`

So the backend config surface is too small for the settings UI that the frontend is presenting.

## Target Split

### Save to `config.toml`

API configuration should be persisted to the backend config file:

- `api_base_url`
- `api_timeout`
- `sse_reconnect_interval`
- `auto_reconnect`

### Save to `localStorage`

Frontend preferences should be kept in the browser:

- `dark_mode`
- `compact_mode`
- `show_debug`
- `language`

### Keep runtime-only in memory

Some values can still be used in memory at runtime, but should not be treated as durable settings unless they are explicitly saved:

- the active API base URL while the app is running
- live SSE connection state
- temporary UI loading state

## Implementation Goals

1. Make the Settings page reflect the real storage model.
2. Add a settings API that can read and write the API config portion.
3. Persist API settings into `config.toml`.
4. Persist frontend preferences in `localStorage`.
5. Make the save button clearly meaningful.
6. Keep timeout and reconnect behavior connected to the values the user edits.
7. Update the docs so they match the actual behavior.

## Task Breakdown

### 1. Define the settings contract

Split the current settings into two logical groups:

- API configuration
- frontend preferences

For each field, decide:

- whether it belongs in `config.toml`
- whether it belongs in `localStorage`
- whether it should be visible but disabled until support exists

Expected outcome:

- We have one authoritative storage location per field.
- The UI no longer implies that every control is already backed by durable storage.

### 2. Add a backend settings API

Introduce a small settings API that can expose and update the API config portion.

Suggested endpoints:

- `GET /api/settings`
- `PUT /api/settings`

Suggested response shape:

```json
{
  "success": true,
  "settings": {
    "api": {
      "base_url": "/api",
      "timeout_seconds": 30,
      "sse_reconnect_interval_seconds": 5,
      "auto_reconnect": true
    },
    "ui": {
      "dark_mode": true,
      "compact_mode": false,
      "show_debug": false,
      "language": "zh"
    }
  }
}
```

Expected outcome:

- Frontend can fetch settings on startup.
- Save operations can update the backend API config portion.
- `config.toml` becomes the source of truth for API settings.

### 3. Persist API configuration into `config.toml`

Add a dedicated backend config section for API settings.

Recommended shape:

```toml
[app]
swarm_root = "agents"

[api]
base_url = "/api"
timeout_seconds = 30
sse_reconnect_interval_seconds = 5
auto_reconnect = true
```

Expected outcome:

- API configuration survives restart.
- Settings changes are visible to all clients using the same backend.
- The backend can enforce and validate API-related settings centrally.

### 4. Persist frontend preferences locally

Use `localStorage` for browser-only preferences.

Suggested keys:

- `angelus_darkMode`
- `angelus_compactMode`
- `angelus_showDebug`
- `angelus_language`

Expected outcome:

- A browser refresh preserves the user’s visual preferences.
- These preferences do not need backend support.
- The backend config file stays focused on system settings.

### 5. Connect the UI to the storage model

Update Settings page behavior so that:

- API settings load from the backend settings API
- UI preferences load from `localStorage`
- Clicking `保存更改` writes both categories to the correct destination

Expected outcome:

- The save button has a real effect.
- The user can tell which settings survive restart and which only survive in the browser.

### 6. Wire timeout and reconnect behavior to real runtime logic

The API settings should not remain decorative.

Work items:

- Make `api_timeout` influence actual HTTP request timeout handling.
- Make `sse_reconnect_interval` control reconnect timing.
- Make `auto_reconnect` decide whether SSE reconnection is enabled.

Expected outcome:

- Timeout failures and reconnection behavior match the saved API configuration.
- The settings UI is tied to actual runtime behavior instead of static labels.

### 7. Improve task failure visibility

Task failures like backend timeout should remain visible as a real runtime outcome.

Work items:

- Ensure timeout is distinguishable from generic failure.
- Preserve provider/model context when available.
- Show the failure reason clearly in task history and logs.

Expected outcome:

- A timed-out task is easy to identify.
- The UI does not collapse different failure types into one vague message.

### 8. Update documentation

After the behavior is implemented, update the docs so they match reality.

Targets:

- `docs/frontend/settings.md`
- `docs/backend/runtime.md`
- `docs/backend/runs.md`
- `docs/agent_structure.md`
- `docs/backend/app-and-routes.md` if the new settings API is added there

Expected outcome:

- The docs explain which settings go to `config.toml`.
- The docs explain which settings go to `localStorage`.
- The docs explain what the save button actually does.

## Suggested Execution Order

1. Define the settings contract and field ownership.

## Next Topic: Agent Workspace Access

We also need an agent workspace model that separates safe local file access from broader repository access.

### Goal

Add an explicit filesystem access mode for each agent so runtime tools can enforce boundaries instead of assuming every agent can see the whole workspace.

### Proposed access modes

- `workspace`
- `full_access`

### Semantics

- `workspace`
  - The agent may only read/write within its assigned workspace root.
  - This should be the default mode.
  - It is the safer choice for most agents and all externally-influenced tasks.

- `full_access`
  - The agent may access the broader project workspace.
  - This should be reserved for trusted system agents.
  - It should be opt-in and clearly visible in the manifest.

### Where it should live

- `core/swarm_spec.py`
  - Add workspace/access fields to `AgentBlueprint`.
- `core/toodefl.py`
  - Add filesystem scope information to `ToolContext`.
- `core/core.py`
  - Thread the access mode into runtime agent/tool creation.
- `tools/file_writer_tool.py`
  - Enforce path boundaries before writing.
- Future file-reading tools
  - Apply the same checks there.

### Suggested manifest shape

```toml
[[agents]]
agent_id = "reviewer"
backend_name = "deepseek"
workspace_mode = "workspace"
workspace_root = "agents/docs_verifier/workspace/reviewer"
tools = ["file_writer"]
```

Or, for a trusted runtime agent:

```toml
[[agents]]
agent_id = "publisher"
backend_name = "deepseek"
workspace_mode = "full_access"
tools = ["file_writer"]
```

### Expected outcome

- Agents stop relying on implicit filesystem assumptions.
- File tools become safer and easier to audit.
- We can later add file reader or shell-like tools without redesigning the permission model.

## Related Future Work: Context Graph System

The proposal in `plan/pending/context_graph_system.md` is valuable, but it should remain a later-stage optimization rather than a prerequisite for workspace access.

### Why it is valuable

- It gives us graph-shaped memory instead of a flat message list.
- It helps preserve relationships between facts, evidence, and claims.
- It aligns well with the existing cognitive graph direction already in the runtime.

### Why it should not block workspace work

- It is mostly about reasoning/memory quality.
- Workspace access is a concrete safety and tooling boundary.
- The workspace model can be added first without needing the full context graph rewrite.

### Recommended priority

1. Land workspace / full access permissions.
2. Make file tools respect those permissions.
3. Keep the context graph system as a second-phase memory improvement.
2. Add the backend settings API and config persistence for API settings.
3. Add `localStorage` persistence for frontend preferences.
4. Wire the Settings page to the real storage model.
5. Connect timeout and reconnect behavior to the saved API config.
6. Update docs and add regression coverage.

## Acceptance Criteria

- API settings are saved into `config.toml`.
- Frontend preferences are saved into `localStorage`.
- The Settings page no longer presents decorative controls as if they were already durable config.
- `保存更改` has a real effect for both storage paths.
- Timeout and reconnection behavior follow the saved API configuration.
- Documentation matches the final implementation.
