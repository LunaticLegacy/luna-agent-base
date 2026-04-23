# Next Plan

This file captures the next round of work so the project can continue without relying on the full conversation context.

## Current State

- Frontend pages are split into 10 route-level boards and now have per-page documentation under `docs/frontend/`.
- Backend documentation is now split by module under `docs/backend/`.
- The backend now exposes the major runtime, catalog/content, run, and health APIs that the frontend expects.
- `RunRecord.snapshot()` now emits canonical `/api/swarms/runs/...` URLs, and the frontend resolves run URLs through the canonical path first.
- A route smoke test now covers the swarm detail, graph, sync run, background run, and SSE endpoints.
- The P1 wiring pass is complete for the scoped items: swarm management, knowledge CRUD, memory create/delete, task refresh, agent round-run, and event/log export/filtering are connected.
- Memory edit/update remains unavailable because the backend does not expose a memory update endpoint.
- The remaining work is mostly about consistency, settings persistence, and removing the last misleading placeholder controls.

## Main Problems Still Present

### 1. A few UI surfaces still need follow-up polish

- `memory.page.ts`
  - create and delete are wired
  - edit/update is still unavailable because the backend does not expose a memory update endpoint
- `settings.page.ts`
  - only `apiBaseUrl` is actually applied
  - other settings are UI-only and are not persisted
- Some tabs and metrics across the boards are still locally derived or static where the backend has no direct source.

### 2. Filters are often only local UI filters

- `tasks`, `agents`, `knowledge`, `events`, and `logs` all show filter controls.
- Some of those filters are still local-only and never round-trip to the backend query params.
- The backend already supports queryable endpoints for most of these boards, so the UI should either:
  - wire the controls to the real query params, or
  - remove the controls until they are truly supported.

### 3. Backend route compatibility is correct but still brittle

- `web/app_factory.py` still registers a small set of app-level swarm routes in parallel with the blueprint routes.
- This works today, but it creates two possible sources of truth for the same paths.
- That is not a current outage, but it is a maintenance risk.

## Next Work Plan

### P2 - Make settings and search state actually persistent

1. Persist `SettingsPage`.
   - Store `apiBaseUrl` in localStorage.
   - Persist the toggles that should survive refresh.
   - Apply only the settings that have a real runtime effect.

2. Decide which page filters are local-only and which should query the backend.
   - If the backend already supports the filter, bind the UI to it.
   - If not, remove the control or label it clearly as local preview filtering.

### P3 - Reduce ambiguity and technical debt

1. Consolidate route ownership where possible.
   - Prefer one canonical source for each public endpoint.
   - Keep aliases only when there is a strong compatibility reason.

2. Add lightweight integration checks for the frontend boards.
   - Overview
   - Swarm management
   - Agents
   - Tasks
   - Knowledge
   - Memory
   - Events
   - Logs
   - Settings

3. Keep the docs aligned with implementation.
   - `docs/frontend/`
   - `docs/backend/`
   - `README.md`
   - `docs/index.md`
   - `docs/en/index.md`

4. Reduce import-time dependency surprises in local smoke tests.
   - `web` currently imports modules that expect `asyncpg`, `redis`, `litellm`, and `openai` to exist at import time.
   - If we want a cleaner integration test path, add explicit optional-dependency guards or make those imports lazy.

## Suggested Execution Order

1. Finish the route smoke and compatibility cleanup around the canonical run URLs.
2. Persist settings and decide which filters should round-trip to the backend.
3. Clean up the remaining placeholder controls on tasks, agents, logs, events, and settings.
4. Add lightweight UI integration checks for the main boards.

## Done Criteria

- Frontend actions should either call the backend or be clearly disabled.
- Run snapshots should expose only real URLs.
- Filters should either query the backend or be explicitly local-only.
- Settings should persist across refresh.
- There should be no obvious “button that looks real but does nothing” in the main boards.
