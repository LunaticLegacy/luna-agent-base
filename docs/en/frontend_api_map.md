# Frontend API Map

This document explains how the Angular frontend consumes the backend API and how page state drives those requests.

## 1. Frontend Positioning

The frontend is responsible for:

- reading backend runtime status
- showing the swarm registry and swarm details
- triggering swarm execution
- triggering one agent round
- visualizing backend JSON, errors, and diagnostics

The frontend does not:

- parse swarm packages
- build runtime objects
- execute graph / agent / tool logic

Those responsibilities belong to the Flask backend and the `core/` runtime.

## 2. API Service Methods

The Angular API wrapper lives in `frontend/angelus/src/app/api.service.ts`.

### `index(baseUrl = '/api')`

Request:

- `GET /api`

Purpose:

- fetch API root information
- show `service`
- show `swarm_count`
- show `load_error`
- show `api_root`

### `health(baseUrl = '/api')`

Request:

- `GET /api/health`

Purpose:

- check whether the backend is alive

### `ready(baseUrl = '/api')`

Request:

- `GET /api/ready`

Purpose:

- check whether the backend runtime is ready

### `listSwarms(baseUrl = '/api')`

Request:

- `GET /api/swarms`

Purpose:

- fetch the loaded swarm list
- drive the registry panel

### `getSwarm(baseUrl, swarmName)`

Request:

- `GET /api/swarms/<swarmName>`

Purpose:

- fetch one swarm detail payload

### `runSwarm(baseUrl, swarmName, request)`

Request:

- `POST /api/swarms/<swarmName>/run`

Purpose:

- trigger the whole swarm graph

### `runAgentRound(baseUrl, swarmName, agentId, request)`

Request:

- `POST /api/swarms/<swarmName>/agents/<agentId>/round`

Purpose:

- directly drive one agent round

## 3. App State Flow

The main component lives in `frontend/angelus/src/app/app.ts`.

### Main signals

- `apiBaseUrl`
- `loading`
- `error`
- `apiIndex`
- `health`
- `ready`
- `swarms`
- `selectedSwarmName`
- `selectedSwarm`
- `selectedAgentId`
- `swarmRunOutput`
- `agentRunOutput`

### State flow

When the page loads, it runs `loadOverview()`.

User actions such as:

- selecting a swarm
- refreshing the overview
- running a swarm
- running an agent

update the signals and trigger template re-rendering.

## 4. Overview Loading

`loadOverview()` runs on startup and requests:

- `index('/api')`
- `health('/api')`
- `ready('/api')`
- `listSwarms('/api')`

If one request fails, the error is formatted and shown in the page error box.

## 5. Swarm Selection

The registry panel comes from the `swarms` signal.

When the user clicks a swarm:

- `selectSwarm(swarmName)` runs
- `selectedSwarmName` updates
- `reloadSelectedSwarm()` loads the details

The component also tries to choose a default agent, usually `planner` if it exists.

## 6. Swarm Detail Loading

`reloadSelectedSwarm()` calls `getSwarm(apiBaseUrl(), selectedSwarmName)`.

On success it updates:

- `selectedSwarm`
- `selectedAgentId`
- default agent message

## 7. Swarm Execution

`runSwarm()` uses:

- `swarmInput`
- `swarmRounds`

It parses the input text as JSON, calls the API, and writes the result to `swarmRunOutput`.

## 8. Agent Round Execution

`runSelectedAgent()` uses:

- `agentMessage`
- `agentRounds`
- `agentAdditionalPrompt`

It sends the request to the backend and writes the result to `agentRunOutput`.

