# Backend API and Dispatch Map

This document describes the backend API entry points, how requests enter Flask, how they are dispatched to `Core` / `ExecutionGraph` / `Agent` / `Tool`, and the response shapes.

## 1. Backend Responsibilities

The backend is responsible for:

- reading root configuration and swarm packages
- building the runtime registry
- exposing health, readiness, and swarm orchestration APIs
- dispatching HTTP requests to runtime objects
- returning structured JSON responses

The backend does not:

- hard-code business flows inside route handlers
- parse prompt / skill / tool details in Flask
- embed graph execution logic directly inside HTTP handlers

## 2. API Root

The public prefix is `/api`.

### `GET /api`

API home, used by the frontend and debugging tools.

Returns:

- `success`
- `service`
- `swarm_count`
- `load_error`
- `api_root`

### `GET /`

Service home. Similar to `/api`, but without `api_root`.

## 3. Health / Ready

### `GET /api/health`

Liveness check.

Behavior:

- returns `200` as long as Flask is running
- does not check swarm loading or graph completeness

### `GET /api/ready`

Readiness check.

Dispatch order:

1. check `load_error`
2. check whether at least one swarm is loaded
3. validate each loaded graph
4. return `503` if any swarm is invalid

## 4. Swarm List / Detail

### `GET /api/swarms`

Lists loaded swarms.

Behavior:

- reads `app.extensions["angelus_runtime"]`
- iterates all loaded swarms
- validates each graph
- returns a summary list

### `GET /api/swarms/<swarm_name>`

Returns a single swarm detail payload.

Behavior:

- looks up the swarm in the runtime registry
- returns `404` if it is not found
- returns graph validity and warnings if found

## 5. Swarm Run

### `POST /api/swarms/<swarm_name>/run`

Runs the selected swarm graph.

Behavior:

1. resolve the swarm
2. obtain its `ExecutionGraph`
3. read `input` and `rounds`
4. call `await graph.run(swarm.core, payload, rounds=rounds)`

Execution is dispatched to:

- `AgentNode` -> `core.get_agent(...)` -> `agent.round_call(...)`
- `ToolNode` -> `core.get_tool(...)` -> `tool.execute(...)`
- branch nodes -> graph branching and join logic

## 6. Agent Round

### `POST /api/swarms/<swarm_name>/agents/<agent_id>/round`

Runs one agent round directly.

Behavior:

1. resolve the swarm and agent
2. ensure `message` is not empty
3. call `await agent.round_call(...)`
4. normalize the result and context with `to_jsonable`

