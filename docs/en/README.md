# Angelus Lunae

<div align="center">

<br />

# Angelus Lunae

### A multi-agent orchestration runtime with live graph editing, temporary agent creation, and runtime mutation tracking

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Angular](https://img.shields.io/badge/Angular-frontend-DD0031?logo=angular&logoColor=white)](https://angular.dev)
[![Runtime](https://img.shields.io/badge/Runtime-swarm%20orchestration-4B5563)](#docs-index)

[📖 Docs Index](#docs-index) · [🧭 API Structure](./api_structure.md) · [🧠 Metadata Reference](./metadata_reference.md) · [📦 Agent Layout](./agent_structure.md)

<br />

<img src="../Luna Angel.png" width="72%" alt="Angelus title artwork" />

<br />

</div>

---

## Why Angelus?

> *"Complex collaboration should not only run. It should be visible, editable, and traceable."*

Angelus is not a plain agent scheduler. It is a runtime skeleton for swarm-style orchestration.
It keeps content generation separate from orchestration, static graph structure separate from runtime graph mutation, and agent behavior separate from graph edits.

It is a good fit if you want to keep pushing in these directions:

- Pluggable swarm packages
- Dynamic orchestration
- Runtime traceability
- Live execution flow
- Frontend/backend split

## Five-Minute Setup

### Install

```bash
python -m venv .lvenv
source .lvenv/bin/activate
pip install -r requirements.txt
```

### Configure

The root `config.toml` now serves two purposes:

- it tells the runtime where to discover swarm packages
- it persists API settings and exposes them through `/api/settings`

```toml
[app]
swarm_root = "agents"

[api]
base_url = "/api"
timeout_seconds = 30
sse_reconnect_interval_seconds = 5
auto_reconnect = true
```

### Start the backend

```bash
python app.py
```

The backend runs at `http://127.0.0.1:5000` and all APIs are mounted under `/api`.

### Open the console

Start the Angular frontend under `frontend/angelus/` and point its API base URL at `/api`.

## Docs Index

This page is the consolidated English documentation entry point for Angelus.

## Overview

- [API Structure](./api_structure.md)
  - High-level description of the FastAPI, routes, error handling, and runtime binding
- [Metadata Reference](./metadata_reference.md)
  - Metadata conventions for graph nodes, runtime state, agents, tools, and skills

## Backend

- [Backend Docs](../backend/README.md)
  - Current implementation notes for backend entrypoints, runtime, runs, catalog/content, and errors

## Frontend

- [Frontend Docs](../frontend/README.md)
  - Current implementation notes for each frontend board, split by page

## Structure

- [Agent Structure](./agent_structure.md)
  - Directory layout and swarm package conventions
- [Dynamic Graph Editing Protocol](./dynamic_graph_protocol.md)
  - Dynamic graph mutation mechanism, known issues, and fix priorities

## Events and Protocol

- [Event Stream Protocol](../event_stream_protocol.md)
  - SSE event types, common structure, `llm_input` field semantics, `state_snapshot` notes

## Suggested Reading Order

- If you want to see the API shape first, start with `api_structure.md`
- If you want to understand backend execution, start with `../backend/README.md`
- If you want to understand frontend consumption, start with `../frontend/README.md`
- If you want to understand graph metadata, start with `metadata_reference.md`
- If you want to understand swarm packaging, start with `agent_structure.md`

## Core Features

### Swarm package model

Each swarm package is a standalone directory containing:

- `swarm.toml`
- one Agent graph
- one or more agent definitions
- one or more skills
- one or more tools

### Dynamic graph orchestration

- edit the graph at runtime
- add / remove edges
- change entry / exit nodes
- inject a temporary agent into the live graph
- remove that temporary agent afterward

### Runtime recording

Every agent / tool / graph mutation is written to:

- `agents/<swarm_name>/runtime_info/current.json`
- `agents/<swarm_name>/runtime_info/events.jsonl`

This makes runtime state replayable, auditable, and debuggable.

### Web API

The backend provides:

- health checks
- swarm listing and details
- graph snapshots
- synchronous execution
- async run sessions
- SSE event streams
- single-agent round calls

### Angular console

The frontend is still a prototype console, but it can already:

- inspect swarm state
- trigger runs
- call one agent directly
- show API status and errors

## Architecture Overview

```mermaid
flowchart TD
    A[app.py] --> B[web/app_factory.py]
    B --> C[read config.toml]
    C --> D[discover agents/* packages]
    D --> E[core/swarm_loader.py]
    E --> F[Core runtime]
    F --> G[ExecutionGraph]
    F --> H[Agents]
    F --> I[Tools]
    F --> J[Skills]
    G --> K[GraphExecutor]
    K --> L[Agent round]
    K --> M[Tool execution]
    M --> N[Graph edits]
    M --> O[Agent create / destroy]
    N --> P[runtime_info]
    O --> P
    P --> Q[agents/<swarm>/runtime_info/]
    B --> R[FastAPI]
    R --> S[Angular console]
```

## Project Structure

```text
angelus/
├── app.py                 # backend entry point
├── config.toml            # root configuration
├── core/                  # runtime kernel
├── modules/               # infrastructure modules
├── tools/                 # default runtime tools
├── web/                   # FastAPI
├── agents/                # loadable swarm packages
│   └── deepseek_demo/     # current demo package
├── frontend/              # Angular console
├── docs/                  # documentation
└── outputs/               # output artifacts
```

## Demo Package

The main demo package lives in `agents/deepseek_demo/` and shows a full adaptive execution chain:

1. `orchestrator` analyzes the user request and produces a structured research plan
2. `organizer_preflight` inspects the request and decides whether to keep the branch tree wide or narrow it
3. `planner` transforms the orchestrator framework into a compact mission brief
4. `research_dispatcher` (organizer) fans out three parallel research branches:
   - `architecture_researcher_runtime` — graph topology and branching patterns
   - `evidence_researcher_runtime` — implementation evidence and runtime behavior
   - `risk_researcher_runtime` — failure modes and operational risks
   - Each branch uses `agent_manager_tool` to spawn a temporary researcher and `graph_editor_tool` to insert it into the live graph
5. `organizer_checkpoint` gathers branch outputs and decides whether another planning pass is needed
6. `writer` synthesizes the branch outputs into a single report
7. `reviewer` reviews the draft and emits a verdict (approve → publisher, revise → writer, re_research → organizer_preflight)
8. `publisher` emits the final user-readable answer
9. `file_writer` writes `outputs/deepseek_demo_final.txt`

The demo is designed to separate:

- content flow
- control flow
- adaptive architecture decisions
- graph mutation
- temporary agent lifecycle
- runtime persistence

### Example Task

If you want to test the current demo, you can use this task:

> Write a clear technical note about "a mutable multi-agent runtime".  
> Requirements:  
> 1. let the orchestrator analyze the request and generate a research plan;  
> 2. let the organizer decide whether to widen or narrow the research branches;  
> 3. let the planner produce a compact mission brief;  
> 4. let the dispatcher fan out three parallel research branches (architecture, evidence, risk);  
> 5. let each branch spawn a temporary researcher, gather findings, and clean up after completion;  
> 6. let the checkpoint organizer decide if the results are sufficient;  
> 7. let the writer synthesize a report and the reviewer approve it;  
> 8. output a publish-ready note and write it to `outputs/deepseek_demo_final.txt`.

This task exercises:

- adaptive orchestration
- graph editing and temporary node insertion
- agent creation and deletion
- parallel branch execution with join semantics
- separation of content and control
- runtime_info persistence
- final output writing

## Roadmap

- [x] swarm package loading
- [x] runtime graph execution
- [x] live run sessions
- [x] SSE event streams
- [x] graph editing tools
- [x] agent create / destroy tools
- [x] runtime_info persistence
- [ ] richer frontend graph rendering
- [ ] clearer execution timelines
- [ ] stricter skill contract validation
- [ ] persistent runtime sessions
- [ ] more analysis-oriented default tools

## Documentation

- [Docs Index](#docs-index)
- [API Structure](./api_structure.md)
- [Backend Docs](../backend/README.md)
- [Frontend Docs](../frontend/README.md)

## License

Angelus Lunae is released under the Apache 2.0 license.

- [LICENSE](../LICENSE)
- [LICENSE.zh-CN.md](../LICENSE.zh-CN.md)
