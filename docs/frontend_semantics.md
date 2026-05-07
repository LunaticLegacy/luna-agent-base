# Frontend Semantics

## Architecture

- `frontend/angelus` is an Angular application that talks to the FastAPI backend.
- `api.service.ts` is the HTTP adapter.
- `state.service.ts` owns client-side runtime state, fallback derivations, and UI-facing actions.

## `frontend/angelus/src/app/api.service.ts`

- `joinUrl(baseUrl, path) -> string`
  - Normalizes API paths.
  - If `baseUrl` is empty, returns root-relative paths such as `/health`.
  - Legacy `/api` base URLs are normalized away, including trailing-slash and full-URL variants.

- `index(baseUrl = '') -> Promise<ApiIndexResponse>`
  - Synthesizes a root index from `/health` and `/swarms`.

- `health(baseUrl = '') -> Promise<HealthResponse>`
  - Calls the backend health endpoint.

- `ready(baseUrl = '') -> Promise<ReadyResponse>`
  - Derives readiness from `/health` plus the current swarm inventory.

- `listSwarms(baseUrl = '') -> Promise<SwarmListResponse>`
  - Loads `/swarms` and enriches each entry with graph-derived metadata.

- `loadSwarm(baseUrl, request) -> Promise<{ success, action, swarm }>`
  - Sends `POST /swarms/load` and then refreshes the loaded swarm detail.

- `getSwarm(baseUrl, swarmName) -> Promise<SwarmDetailResponse>`
  - Synthesizes a full swarm detail view from `/swarms`, `/graph`, and `/history`.

- `getGraph(baseUrl, swarmName)` and `getGraph(swarmName)`
  - Overloaded accessors.
  - The 2-argument form returns the GraphSnapshot shape used by the existing graph viewer.
  - The 1-argument form returns the lightweight graph shape used by compatibility call sites.

- `getHistory(baseUrl, swarmName) -> Promise<HistoryResponse>`
  - Loads `GET /swarms/{name}/history`.

- `runSwarmStream(swarmName, request, baseUrl = '') -> EventSource-like client`
  - Posts to `POST /swarms/{name}/run`.
  - Parses SSE chunks and forwards `start`, `result`, `stopped`, `error`, and `done` events.

- `stopSwarm(baseUrl, swarmName, stopType) -> Promise<...>`
  - Calls `POST /swarms/{name}/stop`.
  - `stopRun(...)` and `stopSwarmRuns(...)` are compatibility wrappers.

## `frontend/angelus/src/app/services/state.service.ts`

### Agent Control One-to-One Mapping

- `loadSwarmFromSource(source)`
  - Sends `POST /swarms/load` through the API adapter.
  - Treats the returned swarm as the newly loaded runtime target.

- `unloadCurrentSwarm(force = false)`
  - Sends `DELETE /swarms/{name}`.
  - Removes the selected swarm from the runtime registry.

- `startRun()`
  - Sends `POST /swarms/{name}/run` through the SSE streaming adapter.
  - Uses the backend run stream as the source of truth for control flow.

- `stopRun()`
  - Sends `POST /swarms/{name}/stop`.
  - Mirrors the backend stop result back into the local run snapshot.

- `runAgentRound()`
  - Uses `POST /swarms/{name}/run` with an agent-scoped input payload.
  - The frontend only wraps the request body; the backend still owns execution.

### Client State And Compatibility

- `loadSettings()`
  - Reads local settings and normalizes the API base URL.
  - Uses empty-string base URLs by default, which maps to root-relative backend paths.
  - Migrates stale `/api`-style localStorage values to the new root-relative form.

- `baseUrl() -> string`
  - Returns the current API base URL, defaulting to `''`.

- `reloadCurrentSwarm()`
  - Rehydrates the selected swarm from already available runtime data.
  - This is a client-side convenience wrapper, not a distinct backend route.

- `watchGraphEvents()`
  - Uses client-side polling to keep the selected graph fresh.
  - Does not require a backend SSE endpoint such as `/graph/events/from/{revision}`.

- `executionGraph` in the swarm-management page
  - Synthesizes a linear execution graph from `selectedExecutionTrace().events`.
  - Reuses the shared graph viewer to render the execution flow in the trace tab.

### Frontend-Derived Views

- `loadOverview()`
  - Loads health, readiness, and the swarm inventory.
  - Keeps the dashboard populated from derived data when the backend does not expose the old catalog routes.

- `loadAgents`, `loadBackgroundTasks` (`loadTasks` compatibility alias), `loadTools`, `loadApis`, `loadSwarmStats`, `loadLogs`, `loadMetrics`, `loadKnowledge`, `loadMemory`
  - No longer depend on the removed catalog endpoints.
  - Populate from the current graph, run feed, or fallback metrics instead.
  - `loadBackgroundTasks()` is the frontend's RuntimeSlot-aligned background-task view: it renders runtime work items from the currently selected swarm, but still derives them from the available run/history feed until the backend exposes a dedicated slot-list API.
  - `BackgroundTaskItem` is the preferred frontend type name; `TaskItem` remains as a compatibility alias only.

- `reloadSelectedSwarm()`
  - Refreshes the selected swarm using the synthesized detail response.
  - This is a derived read-model operation, not an agent-control mutation.

### UI Semantics

- `GraphViewerComponent`
  - Renders a `GraphSnapshot` with zoom, pan, fit-to-view, and active-node highlighting.
  - Pure presentation logic; it does not fetch or mutate backend state.

- `ThoughtGraphViewerComponent`
  - Renders a `ThoughtGraphSnapshot` with relation-aware styling and node taxonomy.
  - Pure visualization logic for thought-graph data.

- Shared layout components such as `PanelCardComponent`, `StatCardGridComponent`, `TabBarComponent`, `ModalComponent`, `EmptyStateComponent`, `SidebarComponent`, and `TopbarComponent`
  - Provide visual structure, navigation, and chrome.
  - They are UI-only and should not be read as runtime semantics.

- Page shells such as `overview.page.ts`, `tasks.page.ts`, and `swarm-management.page.ts`
  - Compose the shared UI components into dashboard layouts.
  - Their buttons, tabs, cards, and drawers are presentation affordances around the backend-backed actions above.
  - The `tasks.page.ts` surface is labeled as `后台任务` in the UI and should be read as a RuntimeSlot-style background-task viewer, not as a separate backend task entity.

## Frontend Convention

- The frontend should not assume a `/api` prefix.
- If a reverse proxy is needed later, configure it explicitly in settings rather than baking it into the default.
- Graph change tracking is an internal client concern unless the backend later exposes a dedicated event stream.
- Execution graphs are currently a frontend visualization derived from trace events rather than a separate backend endpoint.
- In the agent-control path, frontend semantics should map one-to-one to backend routes; anything else belongs in derived-view or compatibility sections.
- UI semantics describe presentation and interaction patterns only; they do not add new backend capabilities.
- When the UI says `后台任务`, treat that as the frontend's RuntimeSlot vocabulary. Preserve compatibility names in code only if needed by older call sites.
