# Next Plan

This file records the next round of work so we can continue without depending on the full conversation context.

## Current Situation

We have three related issues that need to be organized into one implementation plan:

1. The frontend Settings page shows many controls, but only the API base URL currently affects runtime behavior.
2. The save button on Settings feels ineffective because it does not persist anything to disk or the backend.
3. Task failures such as backend timeout need to be surfaced clearly as part of the runtime story, not treated as an opaque error.

The current `config.toml` only contains:

- `[app].swarm_root = "agents"`

So the backend configuration surface is currently minimal, while the frontend presents a larger set of options than the backend actually supports.

## What Is Real Today

### Frontend settings that currently exist in the UI

- `后端 API 地址`
- `API 超时 (秒)`
- `SSE 重连间隔 (秒)`
- `自动重连 SSE 流`
- `深色模式`
- `紧凑布局`
- `显示调试信息`
- `语言`

### Frontend settings that currently take effect

- `后端 API 地址`

This is the only setting that currently changes runtime behavior, because `saveSettings()` only calls `state.setApiBaseUrl(this.apiUrl())`.

### Frontend settings that are still UI-only

- `API 超时 (秒)`
- `SSE 重连间隔 (秒)`
- `自动重连 SSE 流`
- `深色模式`
- `紧凑布局`
- `显示调试信息`
- `语言`

### Backend configuration that currently exists

- `swarm_root`

That is the only explicit top-level configuration field currently in `config.toml`.

## Implementation Goals

1. Make the Settings page honest about what is configurable today.
2. Decide which settings should be runtime-only, locally persisted, or backend-backed.
3. Make the save action visibly meaningful.
4. Make timeout failures easier to understand in task history and logs.
5. Keep the documentation in sync with the actual behavior.

## Task Breakdown

### 1. Classify the Settings surface

Split the current settings into three groups:

- runtime-only UI preferences
- local frontend preferences
- backend-backed configuration

Expected outcome:

- We know which controls should stay visual only.
- We know which controls should be wired to local persistence.
- We know which controls need backend support before they can claim to be “saved.”

### 2. Define the source of truth for each setting

For each setting, decide where its truth lives:

- Frontend runtime state
- Browser storage
- Backend configuration file or API

Recommended default:

- API base URL can stay as a frontend runtime preference for now.
- Visual preferences should be local to the browser.
- Any setting that affects backend execution should not pretend to be saved unless the backend can actually consume it.

### 3. Make `保存更改` meaningful

The current save button only updates `apiBaseUrl` in memory.

We should decide one of these directions:

1. Local-only persistence
   - Save values into browser storage and restore them on startup.
2. Backend persistence
   - Add a configuration save endpoint and write into a real config file or runtime config store.
3. Hybrid model
   - Persist UI preferences locally and backend settings through the server.

Expected outcome:

- The button produces a visible state change that survives navigation or reload when appropriate.
- The save flow has a clear success/failure path.

### 4. Connect timeout-related settings to real behavior

The visible timeout and retry settings should not remain decorative.

Work items:

- Determine whether `apiTimeout` should control HTTP request timeout in the frontend.
- Determine whether `reconnectInterval` and `autoReconnect` should control SSE reconnection logic.
- Decide whether these settings are frontend-only or need backend participation.

Expected outcome:

- A task timeout failure can be interpreted consistently as:
  - model/provider timeout
  - frontend request timeout
  - tool timeout
  - backend execution timeout

### 5. Improve task failure visibility

The timeout case from the task view should be handled as a first-class runtime outcome.

Work items:

- Ensure the task history records the failure reason clearly.
- Distinguish timeout from generic failure in UI copy.
- Preserve backend/provider/model context where available.
- Make sure the failure is visible in task detail, event history, and logs.

Expected outcome:

- A timed-out task is easy to identify.
- The UI does not collapse all failures into the same vague label.

### 6. Align documentation with the actual implementation

Update the docs after the behavior is settled.

Targets:

- `docs/frontend/settings.md`
- `docs/backend/runtime.md`
- `docs/backend/runs.md`
- `docs/agent_structure.md`

Expected outcome:

- The docs describe which settings are real and which are placeholders.
- The docs explain what `saveSettings()` actually does.
- The docs explain the timeout/failure path in a way that helps future debugging.

## Suggested Execution Order

1. Classify each Settings control and mark the current source of truth.
2. Decide the persistence strategy for Settings.
3. Wire `保存更改` to the chosen persistence path.
4. Make timeout handling explicit in task history and logs.
5. Update the docs and add regression coverage.

## Acceptance Criteria

- The Settings page no longer implies that all visible controls are already backed by real configuration.
- `保存更改` has a real effect that matches the chosen persistence model.
- The current `config.toml` scope is respected, or expanded intentionally if backend-backed settings are added.
- Timeout failures are easy to distinguish from generic task failures.
- Documentation matches the final implementation.
