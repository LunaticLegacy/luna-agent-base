# 事件流协议说明

本文档定义 Angelus 执行引擎产生的事件流格式、事件类型和字段语义。适用于 SSE 消费端、前端实时面板、运行审计和调试工具。

## 1. 协议目标

事件流协议负责把一次 graph run 的完整生命周期暴露为可观察、可订阅、可持久化的结构化事件序列。消费方包括：

- 前端 SSE 实时面板
- 运行审计与回放系统
- 外部日志/监控集成

## 2. 通用事件结构

所有事件共享同一顶层结构，定义在 `core/results.py` 的 `ExecutionEvent`：

```json
{
  "run_id": "<uuid>",
  "event_type": "node.completed",
  "timestamp": 1716789012.345,
  "swarm_name": "deepseek_demo",
  "node_id": 3,
  "node_name": "planner",
  "node_type": "AgentNode",
  "branch": null,
  "rounds": 2,
  "status": "ok",
  "data": {}
}
```

字段说明：

| 字段 | 类型 | 说明 |
|------|------|------|
| `run_id` | string | 本次运行的唯一标识 |
| `event_type` | string | 事件类型，见第 3 节 |
| `timestamp` | float | Unix 时间戳（秒） |
| `swarm_name` | string \| null | 所属 swarm |
| `node_id` | int \| null | 关联节点 ID |
| `node_name` | string \| null | 关联节点名称 |
| `node_type` | string \| null | 节点类型，如 `AgentNode`、`ToolNode` |
| `branch` | string \| null | 分支索引（并行分支场景） |
| `rounds` | int \| null | 当前轮次计数 |
| `status` | string \| null | 事件状态提示，如 `ok`、`failed`、`running` |
| `data` | object | 事件载荷，因类型而异 |

## 3. 事件类型清单

### 3.1 运行级事件

#### `run.started`

图执行开始时发出。

`data` 字段：

```json
{
  "entry_node_id": 1,
  "entry_node_name": "orchestrator",
  "state_snapshot": { ... }
}
```

#### `run.completed`

图执行正常结束时发出。

`data` 字段：

```json
{
  "state_snapshot": { ... }
}
```

#### `run.failed`

图执行因异常而终止时发出。

`data` 字段：

```json
{
  "error": "RuntimeError: ...",
  "state_snapshot": { ... },
  "failure": { ... },
  "regulation": { ... }
}
```

- `failure`：结构化失败事件，包含 `failure_scope`、`failure_kind`、`node_id` 等
- `regulation`：可选的故障规制结果，可能为 `null`

#### `run.stopped`

执行被外部请求停止时发出。

`data` 字段：

```json
{
  "stop_type": "soft",
  "reason": "soft stop requested after node completion",
  "state_snapshot": { ... }
}
```

- `stop_type`：`soft`（允许当前节点完成后停止）或 `hard`（立即终止）

### 3.2 节点级事件

#### `node.started`

节点开始执行时发出。

`data` 字段：

```json
{
  "input_payload": "...",
  "state_snapshot": { ... }
}
```

- `input_payload`：进入该节点时的执行状态 payload

#### `node.completed`

节点正常完成时发出。这是最重要的事件类型之一。

`data` 字段：

```json
{
  "state_snapshot": { ... },
  "llm_input": { ... },
  "input_payload": "...",
  "output_payload": "..."
}
```

关键字段：

- `state_snapshot`：执行状态的轻量快照
- `llm_input`：**仅对 `AgentNode` 存在**。描述该节点实际发送给 LLM 的完整输入，见第 4 节
- `input_payload` / `output_payload`：部分路径下会携带（如 branch 合并场景），但非所有 `node.completed` 都有

#### `node.failed`

节点执行失败时发出。

`data` 字段：

```json
{
  "error": "Exception: ...",
  "state_snapshot": { ... },
  "failure": { ... },
  "regulation": { ... }
}
```

#### `node.skipped`

节点因前置条件不满足或故障隔离而被跳过时发出。

`data` 字段：

```json
{
  "reason": "quarantined",
  "fallback_node_id": 5,
  "state_snapshot": { ... }
}
```

### 3.3 分支级事件

#### `branch.started`

并行分支开始执行时发出。

`data` 字段：

```json
{
  "source_node_id": 4,
  "branch_index": 0,
  "attempt": 1,
  "state_snapshot": { ... }
}
```

#### `branch.completed`

分支成功完成时发出。

`data` 字段：

```json
{
  "state_snapshot": { ... },
  "input_payload": "...",
  "output_payload": "..."
}
```

#### `branch.failed`

分支执行失败时发出。

`data` 字段：

```json
{
  "source_node_id": 4,
  "branch_index": 0,
  "error": "Exception: ...",
  "state_snapshot": { ... },
  "failure": { ... },
  "regulation": { ... }
}
```

#### `branch.retry`

分支失败后将重试时发出。

`data` 字段：

```json
{
  "max_retries": 2,
  "backoff_ms": 1000,
  "error": "Exception: ...",
  "state_snapshot": { ... }
}
```

## 4. `llm_input` 字段

`node.completed` 事件在节点类型为 `AgentNode` 时会携带 `llm_input`，完整记录该节点实际发给 LLM 的输入内容。这是调试 agent 行为、复现问题和审计的核心数据来源。

结构：

```json
{
  "system": "You are a planner agent...\n\nAdditional context...",
  "user": "write a summary about...",
  "prev_messages": [
    {"role": "assistant", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "web_search",
        "description": "...",
        "parameters": { ... }
      }
    }
  ]
}
```

字段说明：

| 字段 | 类型 | 说明 |
|------|------|------|
| `system` | string \| null | 完整的 system prompt，通常由 character prompt + cognitive context + additional prompt 拼接而成 |
| `user` | string | 当前轮次的用户输入（即 `state.payload`） |
| `prev_messages` | array[{role, content}] | 送入 LLM 的历史消息列表。包含 active window 的完整消息和 compressed blocks 的摘要 |
| `tools` | array \| null | 绑定的工具 schema 列表（OpenAI function calling 格式）。若 agent 无工具则为 `null` |

### 4.1 与上下文压缩的关系

`prev_messages` 的内容直接反映 `ManagedAgentContext.build_messages()` 的输出：

- **Active window**：最近 6 条完整消息保留原样
- **Compressed blocks**：更早的消息被压缩成摘要块，每条摘要以轻量 `system` hint 形式注入
- **Archive**：被压缩的原始消息可通过 `recall_context` 工具按需召回，不会自动出现在 `prev_messages` 中

这意味着 `llm_input.prev_messages` 不一定包含完整历史，但它精确反映了**实际进入 LLM 的上下文**。需要完整历史时，应结合 agent 私有 workspace 中的存档数据。

## 5. `state_snapshot` 字段

所有运行态事件都携带 `state_snapshot`，它是 `ExecutionState.snapshot()` 的轻量序列化结果。

结构：

```json
{
  "payload": "...",
  "rounds": 3,
  "metadata": { ... },
  "trace_summary": {
    "length": 5,
    "last_node_id": 7,
    "last_node_name": "writer",
    "last_status": "ok"
  },
  "branch_results": { ... }
}
```

### 5.1 关于 trace 的说明

**`state_snapshot` 不再包含完整 `trace`**。早期版本中 `trace` 数组会随节点增长线性膨胀，导致每个事件的序列化/解析成本随运行进度呈 O(n²) 恶化。

当前实现改为只保留 `trace_summary`：

- `length`：trace 总长度
- `last_node_id`：最后执行的节点 ID
- `last_node_name`：最后执行的节点名称
- `last_status`：最后执行状态

如果需要完整 trace，应通过以下途径获取：

- 前端在运行过程中自行累积事件
- 调用 `GET /api/runs/<run_id>` 读取 `RunRecord` 的完整事件列表
- 调用 `GET /api/swarms/<swarm>/execution-traces/latest`

## 6. SSE 传输格式

`GET /api/runs/<run_id>/events` 返回 `text/event-stream`。

### 6.1 帧格式

每条 SSE 帧：

```text
event: node.completed
data: {"run_id":"...","event_type":"node.completed",...}

```

事件名中的空格会被替换为点号，例如 `run.started` 保持原样。

### 6.2 起始快照

连接建立后，服务端会先推送一条：

```text
event: run.snapshot
data: {"run_id":"...","status":"running",...}
```

这是 `RunRecord.snapshot()` 的 JSON，用于让新连接的客户端立刻获得当前运行全貌。

### 6.3 Keepalive

若一段时间无新事件，流会发送：

```text
: keepalive
```

防止代理或浏览器静默断开长连接。

### 6.4 重连与追平

`RunRecord.stream_events()` 支持 `after` 参数，可指定从某条事件之后开始流送。当前路由层暂未暴露该参数，因此 SSE 连接总是从头开始推送已缓存的全部事件，再进入实时推送模式。

## 7. 事件消费建议

### 7.1 前端实时面板

- 监听 `run.snapshot` 获取初始状态
- 用 `node.started` / `node.completed` 高亮当前活跃节点
- 用 `node.completed.data.llm_input` 在事件详情模态框中展示 LLM 实际输入
- 用 `node.failed` / `run.failed` 展示错误和规制信息
- 不依赖 `state_snapshot.trace_summary` 做完整轨迹绘制，应在客户端累积事件

### 7.2 审计与回放

- 按 `run_id` + `timestamp` 排序即可还原执行时序
- `llm_input` 是审计 agent 行为的关键证据
- `state_snapshot` 适合快速定位运行状态，不适合作为完整历史来源

### 7.3 监控与告警

- `node.failed` 和 `run.failed` 是核心告警来源
- `branch.retry` 可作为重试频率监控指标
- `run.stopped` 区分 `soft` / `hard` 有助于判断停止原因
