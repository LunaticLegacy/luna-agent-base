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
  - The 1-argument form returns the lightweight graph shape used by the standalone swarm-detail page.

- `getHistory(baseUrl, swarmName) -> Promise<HistoryResponse>`
  - Loads `GET /swarms/{name}/history`.

- `runSwarmStream(swarmName, request, baseUrl = '') -> EventSource-like client`
  - Posts to `POST /swarms/{name}/run`.
  - Parses SSE chunks and forwards `start`, `result`, `stopped`, `error`, and `done` events.

- `stopSwarm(baseUrl, swarmName, stopType) -> Promise<...>`
  - Calls `POST /swarms/{name}/stop`.
  - `stopRun(...)` and `stopSwarmRuns(...)` are compatibility wrappers.

## `frontend/angelus/src/app/services/state.service.ts`

- `loadSettings()`
  - Reads local settings and normalizes the API base URL.
  - Uses empty-string base URLs by default, which maps to root-relative backend paths.
  - Migrates stale `/api`-style localStorage values to the new root-relative form.

- `baseUrl() -> string`
  - Returns the current API base URL, defaulting to `''`.

- `loadOverview()`
  - Loads health, readiness, and the swarm inventory.
  - Keeps the dashboard populated from derived data when the backend does not expose the old catalog routes.

- `reloadSelectedSwarm()`
  - Refreshes the selected swarm using the synthesized detail response.

- `loadAgents`, `loadTasks`, `loadTools`, `loadApis`, `loadSwarmStats`, `loadLogs`, `loadMetrics`, `loadKnowledge`, `loadMemory`
  - No longer depend on the removed catalog endpoints.
  - Populate from the current graph, run feed, or fallback metrics instead.

- `startRun()`
  - Starts a new run through the SSE streaming endpoint.
  - Maintains a local synthetic `RunSnapshot` so the existing UI can render progress and results.

- `stopRun()`
  - Stops the selected swarm through the new `/stop` endpoint and marks the local run snapshot as finished.

## Frontend Convention

- The frontend should not assume a `/api` prefix.
- If a reverse proxy is needed later, configure it explicitly in settings rather than baking it into the default.
