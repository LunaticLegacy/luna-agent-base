# Next Plan

This file captures the next round of work so the project can continue without relying on the full conversation context.

## Current State

- **Frontend**: Multi-page routing refactor is complete. 10 standalone route pages + layout shell + lazy loading are all functional.
  - `app.ts` / `app.html` / `app.sass`: layout shell (sidebar + topbar + `<router-outlet>`)
  - `app.routes.ts`: 10 lazy-loaded routes
  - `StateService`: global singleton with all signals, API calls, and feed management
  - P0 data loading now prefers real backend responses for Agents / Tasks / Tools, with fallback derivation only when no API data is available yet
  - 3 shared components: `StatCard`, `MiniChart`, `StatusBadge`
- **Backend**: Flask API provides Swarm/Graph/Run/AgentRound endpoints.
- **Gap**: P0 backend APIs for Agents, Tasks, and Tools are now implemented; Knowledge, Memory, Events (query), Logs, and Metrics are still mock-derived.

## Backend API Gap Analysis

### Existing APIs (no changes needed)

| Endpoint | Method | Returns |
|----------|--------|---------|
| `GET /api` | index | `service`, `swarm_count` |
| `GET /api/health` | health check | `status` |
| `GET /api/ready` | readiness | `ready`, `swarm_count`, `invalid_swarms` |
| `GET /api/swarms` | swarm list | `SwarmSummary[]` |
| `GET /api/swarms/{name}` | swarm detail | `SwarmDetails` (incl. `agent_files[]`, `graph`) |
| `GET /api/swarms/{name}/graph` | graph topology | `GraphSnapshot` |
| `POST /api/swarms/{name}/run` | sync run | `rounds`, `output`, `trace`, `metadata` |
| `POST /api/swarms/{name}/runs` | background run | `run_id`, `status: "started"` |
| `GET /api/runs/{run_id}` | run status | `RunSnapshot` |
| `GET /api/runs/{run_id}/events` | SSE stream | `event: .../data: ...` |
| `POST /api/swarms/{name}/agents/{id}/round` | agent round | `result`, `context` |

### Missing APIs (needed to replace mock data)

#### P0 — Core Data APIs (blocks real data on 3 main pages)

**1. Agent List**
```
GET /api/swarms/{swarm_name}/agents
```
Response:
```json
{
  "success": true,
  "agents": [
    {
      "id": "planner",
      "name": "PlannerAgent",
      "status": "online",
      "type": "planner",
      "capabilities": ["planning", "decomposition"],
      "tags": ["core", "system"],
      "tasks_executed": 128,
      "success_rate": 96.5,
      "avg_response_time_ms": 420,
      "token_usage_total": 2400000,
      "last_activity": "2026-04-22T12:34:56Z"
    }
  ]
}
```
- **Used by**: `agents.page.ts` (table, filters, detail drawer, stat cards)

**2. Task List & Query**
```
GET /api/tasks?swarm={name}&status=&priority=&executor=&from=&to=&page=1&limit=20&q={search}
```
Response:
```json
{
  "success": true,
  "total": 156,
  "page": 1,
  "limit": 20,
  "items": [
    {
      "id": "task-001",
      "name": "数据清洗与预处理",
      "status": "running",
      "priority": "high",
      "executor": "DataAgent",
      "duration_ms": 134000,
      "created_at": "2026-04-22T10:30:00Z",
      "description": "...",
      "input": { ... },
      "output": { ... },
      "logs": [
        { "time": "2026-04-22T10:30:05Z", "level": "info", "message": "Started" }
      ]
    }
  ],
  "stats": {
    "pending": 3,
    "running": 2,
    "success": 145,
    "failed": 6,
    "avg_duration_ms": 45000
  }
}
```
- **Used by**: `tasks.page.ts` (table, filters, pagination, detail drawer, stat cards)

**3. Tool List**
```
GET /api/tools?type=&status=&q={search}
```
Response:
```json
{
  "success": true,
  "tools": [
    {
      "id": "web_search",
      "name": "网页搜索",
      "type": "API",
      "status": "online",
      "description": "使用搜索引擎查询实时信息",
      "calls": 1245,
      "avg_ms": 320,
      "last_call": "2026-04-22T12:32:00Z",
      "success_rate": 98.2,
      "error_rate": 1.8,
      "created_at": "2024-01-15T00:00:00Z",
      "schema": { "query": "string", "limit": "number" }
    }
  ],
  "stats": {
    "total": 12,
    "available": 10,
    "api": 5,
    "local": 7,
    "today_calls": 47
  }
}
```
- **Used by**: `tools.page.ts` (table, filters, detail panel, stat cards)

---

#### P1 — Operational Data APIs (blocks real data on 4 pages)

**4. Swarm Runtime Stats**
```
GET /api/swarms/{swarm_name}/stats
```
Response:
```json
{
  "success": true,
  "success_rate": 98.5,
  "throughput": 124,
  "token_usage": 2400000,
  "task_distribution": {
    "pending": 2,
    "running": 1,
    "completed": 45,
    "failed": 3
  },
  "resource_usage": {
    "cpu_percent": [12, 15, 14, 18, ...],
    "memory_mb": [256, 260, 258, 265, ...]
  }
}
```
- **Used by**: `swarm-management.page.ts` (donut chart, trend bars, stat cards)

**5. Event Query**
```
GET /api/events?level=&source=&from=&to=&page=1&limit=50&q={search}
```
Response:
```json
{
  "success": true,
  "total": 128,
  "items": [
    {
      "id": "evt-001",
      "time": "2026-04-22T12:34:56Z",
      "level": "info",
      "source": "system",
      "event": "Swarm 初始化完成",
      "detail": "deepseek_demo swarm loaded successfully",
      "data": { "swarm": "deepseek_demo" }
    }
  ],
  "stats": {
    "today": 128,
    "errors": 3,
    "warnings": 12,
    "infos": 113
  }
}
```
- **Used by**: `events.page.ts` (event table, filters, stat cards)
- **Note**: Real-time stream already exists via SSE `/api/runs/{run_id}/events`. This is for historical/queryable events.

**6. Log Query**
```
GET /api/logs?level=&service=&from=&to=&page=1&limit=100&q={search}
```
Response:
```json
{
  "success": true,
  "total": 1247,
  "items": [
    {
      "id": "log-001",
      "time": "2026-04-22T12:34:56Z",
      "level": "INFO",
      "service": "backend",
      "message": "Application startup complete"
    }
  ],
  "stats": {
    "error": 3,
    "warn": 23,
    "info": 892,
    "debug": 329
  }
}
```
- **Used by**: `logs.page.ts` (log lines, level filters, stat cards)

---

#### P2 — Knowledge & Memory APIs (blocks real data on 2 pages)

**7. Knowledge Base CRUD**
```
GET    /api/knowledge?type=&source=&tag=&q=&page=1&limit=20
GET    /api/knowledge/{id}
POST   /api/knowledge
PUT    /api/knowledge/{id}
DELETE /api/knowledge/{id}
```
Response (list):
```json
{
  "success": true,
  "total": 86,
  "items": [
    {
      "id": "kb-001",
      "title": "Swarm 编排最佳实践",
      "type": "document",
      "source": "官方文档",
      "tags": ["swarm", "orchestration"],
      "status": "active",
      "citations": 42,
      "created_at": "2026-01-10T00:00:00Z",
      "content": "...",
      "meta": {
        "author": "Angelus Team",
        "version": "1.2",
        "updated_at": "2026-03-15T00:00:00Z",
        "size": "12KB"
      },
      "related": ["kb-002", "kb-005"]
    }
  ],
  "stats": {
    "total": 86,
    "documents": 34,
    "vectors": 45,
    "rules": 7
  }
}
```
- **Used by**: `knowledge.page.ts` (table, filters, preview drawer, stat cards)

**8. Memory System CRUD**
```
GET    /api/memory?type=&source=&q=&page=1&limit=20
GET    /api/memory/{id}
POST   /api/memory
DELETE /api/memory/{id}
```
Response (list):
```json
{
  "success": true,
  "total": 342,
  "items": [
    {
      "id": "mem-001",
      "summary": "PlannerAgent 成功分解复杂任务",
      "content": "PlannerAgent 在面对包含 7 个子任务的复杂工作流时...",
      "timestamp": "2026-04-22T11:30:00Z",
      "type": "semantic",
      "source": "PlannerAgent",
      "sentiment": 0.72,
      "importance": 92,
      "related_ids": ["mem-002", "mem-005"]
    }
  ],
  "stats": {
    "total": 342,
    "active": 298,
    "avg_importance": 72,
    "long_term": 156,
    "working": 86
  }
}
```
- **Used by**: `memory.page.ts` (memory list, detail panel, importance bars, stat cards)

---

#### P3 — System Metrics API (nice-to-have)

**9. System Metrics Time-Series**
```
GET /api/metrics?window=1h&resolution=1m
```
Response:
```json
{
  "success": true,
  "window": "1h",
  "resolution": "1m",
  "series": {
    "cpu_percent": [12, 15, 14, ...],
    "memory_mb": [256, 260, 258, ...],
    "request_latency_ms": [45, 52, 48, ...],
    "throughput_rps": [12, 15, 14, ...],
    "token_usage": [1200, 1350, 1100, ...],
    "error_rate": [0.01, 0.02, 0.01, ...]
  }
}
```
- **Used by**: `overview.page.ts` (bottom 6 sparkline cards)

---

## Short-Term Fallback Strategy (Front-End Derivation)

If backend APIs are not ready, the frontend can derive plausible data from existing endpoints:

| Page | Derivation Source | What can be real |
|------|-------------------|------------------|
| **Agents** | `selectedSwarm.agent_files[]` | Agent IDs and names. Status/capabilities/tasks remain mock. |
| **Tasks** | `activeRun()` + `responseFeed[]` | Current and recently completed runs. Historical tasks remain mock. |
| **Knowledge** | `graph.nodes[].metadata` | Node metadata as knowledge snippets. Full KB remains mock. |
| **Memory** | `run.trace` + `run.metadata` | Execution traces as episodic memory. Long-term memory remains mock. |
| **Tools** | `selectedSwarm.tool_count` + `graph.nodes` (ToolNode) | Tool names and types. Usage stats remain mock. |
| **Events** | `liveEvents[]` (SSE) | Real-time events only. Historical events remain mock. |
| **Logs** | `responseFeed[]` + error history | API call logs. System logs remain mock. |

---

## Recommended Execution Order

1. ~~Implement P0 APIs (`/agents`, `/tasks`, `/tools`)~~
2. ~~Wire P0 APIs into `StateService`~~
3. Update page components if you want explicit page-level query support for server-side pagination and filtering.
4. **Implement P1 APIs** (`/stats`, `/events`, `/logs`) — operational visibility.
5. **Implement P2 APIs** (`/knowledge`, `/memory`) — only if these concepts are part of the product roadmap.
6. **Implement P3 API** (`/metrics`) — lowest priority, purely cosmetic.

---

## Notes for the Next Session

- Check `frontend/angelus/src/app/services/state.service.ts` when adding new API methods.
- Follow the existing pattern: `async loadXxx()` method → `this.loading.set(true)` → `apiService.xxx()` → update signal → `this.loading.set(false)`.
- All new page data should go through `StateService` so it is shared across routes.
- Keep mock data as fallback (`?? MOCK_DATA`) until the backend endpoint is confirmed working.
- The `RunSnapshot` already contains `trace` and `metadata` — these can be mined for Tasks/Memory/Events before dedicated APIs exist.
