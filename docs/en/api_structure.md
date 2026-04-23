# Current API Structure

This document summarizes the Flask API shape, response structure, and its relationship with the `core/` runtime.

## 1. Overall Positioning

The API is the backend runtime interface layer. Its responsibilities are:

- loading swarm packages
- exposing health and readiness checks
- listing loaded swarms
- triggering swarm runs
- triggering one round of a single agent

The API itself does not:

- parse swarm package files
- build agent / tool / graph objects
- execute LLM business logic

Those tasks are handled by `core/` and `web/app_factory.py`.

## 2. Service Entry

The current entry point is `app.py`.

At startup it:

- reads `config.toml`
- scans `agents/` for swarm packages
- creates the Flask app
- registers health and swarm routes

## 3. Routes

The public API is mounted under `/api`.

### `GET /api/health`

Basic liveness check.

Example:

```json
{
  "success": true,
  "status": "ok"
}
```

### `GET /api/ready`

Checks whether the runtime is ready.

Behavior:

- returns `503` if no swarm is loaded
- returns `503` if any execution graph is invalid
- otherwise returns ready

Example:

```json
{
  "success": true,
  "ready": true,
  "swarm_count": 1
}
```

### `GET /`

Service home information.

Returns:

- `service`
- `swarm_count`
- `load_error`

### `GET /api`

API home information. It is similar to `/`, but also includes `api_root`.

### `GET /api/swarms`

Lists all loaded swarms.

Each swarm summary includes:

- `swarm_name`
- `package_path`
- `manifest_path`
- `graph_file`
- `agent_count`
- `skill_count`
- `tool_count`
- `graph_attached`
- `graph_valid`
- `graph_errors`
- `graph_warnings`

### `GET /api/swarms/<swarm_name>`

Returns a single swarm detail payload.

Includes:

- `graph_file`
- `agent_files`
- `agent_count`
- `skill_count`
- `tool_count`
- `graph_attached`
- `graph_valid`
- `graph_errors`
- `graph_warnings`

### `POST /api/swarms/<swarm_name>/run`

Runs the selected swarm graph.

Request example:

```json
{
  "input": {
    "text": "write a summary"
  },
  "rounds": 0
}
```

Response example:

```json
{
  "success": true,
  "swarm": "deepseek_demo",
  "rounds": 4,
  "output": {},
  "trace": [],
  "metadata": {}
}
```

### `POST /api/swarms/<swarm_name>/agents/<agent_id>/round`

Directly drives one agent round.

Request example:

```json
{
  "message": "hello",
  "rounds": 0,
  "additional_prompt": "Be concise."
}
```

Returns:

- `result`
- `context`

### `GET /api/swarms/<swarm_name>/graph`

Returns the current execution graph snapshot.

Used by the frontend to draw the static graph before overlaying runtime state.

### `POST /api/swarms/<swarm_name>/runs`

Starts an async run session and returns a `run_id` immediately.

### `GET /api/swarms/runs/<run_id>`

Returns the current state snapshot of an async run session.

### `GET /api/swarms/runs/<run_id>/events`

Subscribes to the SSE event stream for a run session.
