# Backend Live Execution

This document explains the backend "C plan" for live execution.

The goal is to split one swarm execution into three layers:

- static graph snapshot
- async run session
- SSE event stream

## 1. Overall Flow

```mermaid
flowchart TD
    A[POST /api/swarms/<swarm>/runs] --> B[RunRegistry creates run_id]
    B --> C[background thread asyncio.run(graph.run)]
    C --> D[GraphExecutor emits run/node/branch events]
    D --> E[RunRecord caches current state and events]
    E --> F[GET /api/runs/<run_id> query state]
    E --> G[GET /api/runs/<run_id>/events subscribe SSE]
```

## 2. New Endpoints

### `GET /api/swarms/<swarm_name>/graph`

Returns the static snapshot of the current graph.

Use it to:

- draw the full graph first
- overlay runtime state later

### `POST /api/swarms/<swarm_name>/runs`

Starts an async run session.

Behavior:

- reads `input` and `rounds`
- creates a `run_id`
- returns `202 Accepted` immediately
- continues execution in the background

### `GET /api/runs/<run_id>`

Queries the current status of a run session.

Useful for:

- polling
- debugging
- backend status panels

### `GET /api/runs/<run_id>/events`

Subscribes to the SSE stream.

The frontend can use it to update:

- the currently active node
- branch status
- the trace panel
- error messages

The connection starts by sending a `run.snapshot` event, then continues with later events.

## 3. Event Types

Current events:

- `run.started`
- `node.started`
- `node.completed`
- `node.failed`
- `branch.started`
- `branch.completed`
- `branch.failed`
- `run.completed`
- `run.failed`

## 4. Run States

Run session states:

- `queued`
- `running`
- `completed`
- `failed`

## 5. State Snapshot

`GET /api/runs/<run_id>` returns:

- `current_node_id`
- `current_node_name`
- `current_node_type`
- `rounds`
- `state`
- `final_state`
- `event_count`

## 6. Sync vs Async

The old synchronous API is still available:

- `POST /api/swarms/<swarm_name>/run`

It still returns the final result directly, which is convenient for simple debugging and compatibility.

The new async API is for live visualization and progress tracking.

