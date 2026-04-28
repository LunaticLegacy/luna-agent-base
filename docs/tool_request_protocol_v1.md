# Tool Request Protocol v1.0

> **Status**: Frozen  
> **Scope**: Angelus Runtime — Agent-to-Tool Execution Contract  
> **Date**: 2026-04-26

---

## 1. 设计目标

当前架构中 ToolNode 与 AgentNode 混排于 ExecutionGraph，导致：
- 工具参数静态硬编码（`input_mapping`），无法响应运行时上下文；
- Agent 输出与工具执行之间缺乏清洗/校验层；
- 图语义与控制流语义纠缠，`set_exit` 与叶子节点行为不一致。

本协议目标：**将工具调度从 ExecutionGraph 和 Agent 内部同时抽离出来**，形成独立的 `ToolScheduler` 层，实现：
- ExecutionGraph 仅表达 Agent 控制流；
- Agent 知道工具、可请求工具、但不执行工具；
- Runtime 安全地并行调度工具、回传结果、支持 Agent 自修正；
- 工具事件完整可观测。

---

## 2. 冻结契约（12 条）

1. **Node 生命周期采用选项 A**  
   `node.completed` 必须等同一 AgentNode 内的 agent round、tool requests、tool execution、tool result 回传、agent 自修正全部完成后才发出。

2. **ToolNode 从新架构中废弃**  
   新执行图只表达 Agent 流。Tool 不再作为 graph node。旧 `ToolNode` 只作为 legacy compatibility 保留。

3. **Agent 知道工具，但不执行工具**  
   需要工具的 agent 能看到当前允许工具的 schema，并主动输出 `tool_requests`。实际执行权属于 runtime / ToolScheduler。

4. **并行调度由 runtime 决定**  
   删除 `parallel_group`。Agent 可声明 `resources`，但最终资源访问集合必须由 runtime 根据 tool schema 和参数重新推导。无依赖、无资源冲突的请求必须并行执行。

5. **资源冲突保守处理**  
   同一文件多写默认拒绝并返回 `ResourceConflict`，不要自动串行化。读读可并行，读写/写写冲突，无法判断资源冲突时保守串行或拒绝。

6. **策略优先级固定**  
   `Runtime policy > Agent runtime option > ToolRequest preference`。Agent 可以声明 `on_success` / `on_failure` 偏好，但不能覆盖 runtime 安全策略。

7. **v1 暂不实现 `content_ref` / `source_ref`**  
   v1 的 tool request `args` 必须自包含。引用机制放到 v2，避免第一版引入 JSONPath / 变量解析层。

8. **上下文管理 v1 用硬上限**  
   暂不做智能摘要。先实现 `max_context_messages` 或类似硬限制，保留 system messages，丢弃最旧的非 system messages。摘要压缩放到 v2。

9. **输出格式采用局部强制 JSON envelope**  
   只有需要工具的 agent 必须输出 JSON envelope，例如包含 `content`、`tool_requests`、`next_node_ids`。不需要工具的 writer / publisher 可继续输出自由文本。

10. **runtime 消息映射为 system role**  
    内部可以有 `runtime` 语义，但发给 LLM API 时映射为 `system`，并用明确标记包裹，例如 `[TOOL BATCH RESULT]...[/TOOL BATCH RESULT]`。

11. **系统工具不走普通 ToolScheduler**  
    `graph_editor`、`agent_manager` 这类系统控制能力走 `control_intent → SystemControlService`，由服务编译成有序、可校验、可审计的事务序列。不要让 organizer 直接拼底层 graph/agent tool request 链。

12. **trace 必须显示工具事件**  
    工具虽然不进图，但必须进入 trace：`tool.requested`、`tool.batch.started`、`tool.started`、`tool.completed`、`tool.failed`、`tool.batch.completed`。

---

## 3. 架构分层

```text
┌─────────────────────────────────────────┐
│           ExecutionGraph                │
│        (AgentNode 流 only)              │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│         GraphExecutor                   │
│  execute AgentNode → collect outputs    │
│  → detect tool_requests → call          │
│  ToolScheduler → append results →       │
│  maybe re-enter same AgentNode          │
│  → route to next AgentNode              │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│         ToolScheduler                   │
│  validate schema → infer resources      │
│  → build dependency DAG                 │
│  → execute safe parallel groups         │
│  → emit tool events                     │
│  → return ToolBatchResult               │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│         ToolRegistry                    │
│  tool definitions, schemas, capabilities│
│  resource inference rules               │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│      SystemControlService               │
│  control_intent parsing                 │
│  ordered transaction compilation        │
│  rollback / audit logging               │
└─────────────────────────────────────────┘
```

---

## 4. AgentNode 生命周期（选项 A）

```text
node.started
  ├─ agent.round.started
  │    └─ llm.fetch() → agent outputs content + tool_requests?
  ├─ agent.round.completed (pending_tools = true / false)
  │
  ├─ [if pending_tools]
  │    ├─ tool.batch.started
  │    │    ├─ tool.started  × N (并行)
  │    │    └─ tool.completed / tool.failed  × N
  │    ├─ tool.batch.completed
  │    ├─ agent.tool_results.delivered
  │    └─ [maybe agent.round.started again]
  │
  └─ node.completed
```

约束：
- 一个 AgentNode 可包含多个 agent round，但受 `max_tool_rounds` 硬上限。
- `node.completed` 仅在最后一个 agent round 输出空 `tool_requests` 时发出。
- `next_node_ids` 仅在最终 round 生效；中间 round 即使有 `next_node_ids` 也忽略。

---

## 5. ToolRequest Schema

```json
{
  "tool_requests": [
    {
      "id": "check_frame_py",
      "tool": "python_syntax_check",
      "args": {
        "filename": "frame.py",
        "source": "import abc\n..."
      },
      "depends_on": [],
      "required": true,
      "on_success": "continue",
      "on_failure": "return_to_agent",
      "timeout_ms": 30000,
      "resources": [],
      "metadata": {
        "reason": "Validate generated Python before writing."
      }
    },
    {
      "id": "write_frame_py",
      "tool": "file_writer",
      "args": {
        "path": "outputs/frame.py",
        "content": "import abc\n...",
        "overwrite": true
      },
      "depends_on": ["check_frame_py"],
      "required": true,
      "on_success": "return_to_agent",
      "on_failure": "return_to_agent",
      "timeout_ms": 30000,
      "resources": [
        {
          "type": "file",
          "id": "outputs/frame.py",
          "mode": "write"
        }
      ],
      "metadata": {
        "reason": "Write the requested frame.py artifact."
      }
    }
  ]
}
```

### 字段语义

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | string | 是 | 本轮内唯一标识，用于依赖引用和结果回传 |
| `tool` | string | 是 | 工具名，必须在 ToolRegistry 中注册 |
| `args` | object | 是 | 工具参数，v1 必须自包含（无引用机制） |
| `depends_on` | string[] | 否 | 依赖的 request id 列表，这些 request 成功后本请求才能执行 |
| `required` | boolean | 否 | 默认 `true`。`true` 表示失败会阻断后续处理；`false` 表示失败仅记录警告 |
| `on_success` | string | 否 | 默认 `"continue"`。见 §7 策略表 |
| `on_failure` | string | 否 | 默认 `"return_to_agent"`。见 §7 策略表 |
| `timeout_ms` | int | 否 | 单工具超时，默认由 ToolRegistry 定义 |
| `resources` | object[] | 否 | Agent 声明的资源访问集合，runtime 必须复算 |
| `metadata` | object | 否 | 非执行信息，用于 trace / debug |

---

## 6. ToolResult & ToolBatchResult Schema

### ToolResult（单工具）

```json
{
  "request_id": "check_frame_py",
  "tool": "python_syntax_check",
  "status": "failed",
  "output": null,
  "error": {
    "type": "SyntaxError",
    "message": "invalid syntax at line 1",
    "recoverable": true,
    "retryable": false
  },
  "started_at": "2026-04-26T12:00:00Z",
  "finished_at": "2026-04-26T12:00:00Z",
  "duration_ms": 42
}
```

### ToolBatchResult（整批）

```json
{
  "type": "tool_batch_result",
  "node_id": 22,
  "agent_id": "code_writer",
  "tool_round": 1,
  "results": [
    {
      "request_id": "check_frame_py",
      "tool": "python_syntax_check",
      "status": "success",
      "output": {"valid": true},
      "error": null,
      "duration_ms": 42
    },
    {
      "request_id": "write_frame_py",
      "tool": "file_writer",
      "status": "success",
      "output": {"written": true, "path": "outputs/frame.py", "bytes": 2142},
      "error": null,
      "duration_ms": 11
    }
  ],
  "summary": {
    "status": "success",
    "failed_required": false,
    "skipped": []
  }
}
```

### 错误字段语义

| 字段 | 类型 | 说明 |
|---|---|---|
| `type` | string | 错误分类，如 `SyntaxError`, `ResourceConflict`, `PermissionDenied`, `Timeout` |
| `message` | string | 人类可读描述 |
| `recoverable` | boolean | Agent 是否有可能通过修正输出来修复 |
| `retryable` | boolean | Runtime 是否可以通过重试工具调用来修复 |

---

## 7. 并行调度规则

### 7.1 调度输入

ToolScheduler 接收一轮 `tool_requests`，构造 DAG：
- **节点** = ToolRequest
- **边** = `depends_on` 依赖关系
- **资源锁** = runtime 推导的 `(resource_type, resource_id, access_mode)` 集合

### 7.2 资源推导

Agent 可声明 `resources`，但 runtime 必须根据 tool schema 和 `args` 重新推导。

```python
def infer_resources(tool_name: str, args: dict) -> List[ResourceAccess]:
    if tool_name in {"file_writer", "file_append", "file_delete"}:
        return [ResourceAccess(type="file", id=normalize_path(args["path"]), mode="write")]
    if tool_name == "file_reader":
        return [ResourceAccess(type="file", id=normalize_path(args["path"]), mode="read")]
    if tool_name == "graph_editor":
        return [ResourceAccess(type="graph", id="current", mode="mutate")]
    if tool_name == "agent_manager":
        return [ResourceAccess(type="agent", id=args.get("agent_id", "unknown"), mode="mutate")]
    return []
```

最终以 runtime 推导结果为准。

### 7.3 冲突矩阵

| A | B | 可并行 |
|---|---|---|
| read(X) | read(X) | ✅ 是 |
| read(X) | write(X) | ❌ 否 |
| write(X) | write(X) | ❌ 否 |
| write(X) | write(Y) | ✅ 是 |
| write(X) | append(X) | ❌ 否 |
| web_search(A) | web_search(B) | ✅ 是 |
| graph_mutate | graph_mutate | ❌ 否 |
| graph_mutate | graph_read | ❌ 否 |
| unknown | any | ❌ 保守串行 |

### 7.4 调度算法

```text
1. 构建 DAG（depends_on 为边）
2. 拓扑排序，得到执行层级
3. 同一层级内：
   a. 按资源冲突矩阵分组
   b. 无冲突的请求 → 并行执行（asyncio.gather）
   c. 有冲突的请求 → 按 request id 字典序串行
4. 同一文件多写 → 拒绝，返回 ResourceConflict
5. 某请求失败且 required=true → 检查 fail_fast 策略
6. 依赖某失败请求的请求 → 默认跳过（skipped）
```

---

## 8. 策略优先级与失败处理

### 8.1 优先级链

```text
Runtime policy        → 最高，安全策略不可被覆盖
Agent runtime option  → 中等，agent 蓝图配置
ToolRequest preference → 最低，单次请求声明
```

### 8.2 支持的动作

| 动作 | 语义 |
|---|---|
| `continue` | 工具成功后继续当前 node 流程 |
| `return_to_agent` | 把结果回传给同一个 agent，进入下一轮 |
| `abort_node` | 当前 AgentNode 失败，触发错误处理 |
| `skip_dependent` | 跳过依赖该 request 的工具（scheduler 自动处理） |
| `retry` | runtime 自动重试（受 max_retries 限制） |
| `route_after_tools` | 工具完成后允许进入 `next_node_ids` |

### 8.3 默认失败策略

```text
required tool failed      → return_to_agent
optional tool failed      → continue_with_warning
control tool failed       → abort_node
resource conflict         → return_to_agent
schema invalid            → return_to_agent
permission denied         → abort_node
max_tool_rounds exceeded  → abort_node
```

---

## 9. Agent 输出格式（OpenAI Function Calling）

### 9.1 需要工具的 Agent

Agent 通过 **OpenAI function-calling** 接口请求工具。Runtime 将绑定的工具 schema 注入到 LLM 请求中，LLM 返回 `tool_calls`，Runtime 解析并调度执行。

无需输出 JSON envelope。Agent 直接表达意图，工具调用由 function-calling 机制处理。

### 9.2 不需要工具的 Agent

继续输出自由文本，运行时兼容处理。

### 9.3 现有 Agent 迁移

| Agent | 当前输出 | 是否使用 function calling | 原因 |
|---|---|---|---|
| `orchestrator` | 自由文本 | 是 | 需要调用工具进行编排 |
| `organizer` | 自由文本 | 是 | 需要调用工具进行组织 |
| `code_writer` | 纯文本代码 | **是** | 需要调用 `file_writer` |
| `writer` | Markdown 报告 | 否 | 不需要工具 |
| `researcher` | 自由文本 | 是 | 需要调用 `web_search` |
| `publisher` | 自由文本 | 否 | 不需要工具 |
| `reviewer` | 自由文本 | 是 | 需要调用工具进行验证 |

---

## 10. 上下文管理（v1 硬上限）

### 10.1 约束

- `Agent._context.messages` 不设无限增长。
- v1 采用硬上限：`max_context_messages`，默认 20。
- 保留所有 `system` / `runtime` messages。
- 超出上限时，丢弃最旧的 `user` / `assistant` messages（FIFO）。
- v2 再引入智能摘要压缩。

### 10.2 Runtime 消息格式

内部语义 role = `runtime`，但发送给 OpenAI API 时映射为 `system`：

```text
[TOOL BATCH RESULT - Round 1]
{
  "results": [...],
  "summary": {...}
}
[/TOOL BATCH RESULT]
```

`Agent.append_context("runtime", content)` 存储。  
`LLMFetcher` 发送前转换为 `role="system"`。

---

## 11. 系统工具处理（control_intent）

`graph_editor`、`agent_manager` 等系统控制工具**不走普通 ToolScheduler**。

### 11.1 流程

```text
organizer 输出 control_intent
  → SystemControlService 接收
  → schema 校验
  → 权限校验（capability policy）
  → 不变量校验（图结构完整性）
  → dry-run（可选）
  → 编译为有序 tool sequence
  → 执行
  → 写 audit log 到 runtime_info
  → 返回 control_result
```

### 11.2 与 ToolScheduler 的区别

| | ToolScheduler | SystemControlService |
|---|---|---|
| 输入 | `tool_requests` | `control_intent` |
| 编排 | DAG 并行 | 预定义有序事务 |
| 权限 | capability check | capability + policy + invariant |
| 回滚 | 无 | 支持 dry-run / 逆向操作 |
| trace | `tool.*` 事件 | `control.*` 事件 |

### 11.3 当前 deepseek_demo 迁移

nodes 5–16（spawn → insert → destroy → remove）应迁移为：
- organizer 输出 `control_intent: {type: "spawn_transient_researcher", ...}`
- `SystemControlService` 编译为有序的 `agent_manager.create` → `graph_editor.add_node` → ... → `graph_editor.remove_node` 序列

---

## 12. Trace 事件规范

工具虽然不进图，但必须完整进入 trace。

### 12.1 事件类型

| 事件 | 时机 | 数据 |
|---|---|---|
| `tool.requested` | agent round 输出非空 tool_requests | `request_ids`, `tool_names` |
| `tool.batch.started` | scheduler 开始执行一批 | `batch_size`, `parallel_groups` |
| `tool.started` | 单个工具开始执行 | `request_id`, `tool`, `args`（脱敏后） |
| `tool.completed` | 单个工具成功完成 | `request_id`, `output`, `duration_ms` |
| `tool.failed` | 单个工具失败 | `request_id`, `error`, `duration_ms` |
| `tool.batch.completed` | 整批执行完毕 | `summary`, `results` |
| `agent.tool_results.delivered` | 结果回传给 agent | `tool_round`, `result_count` |
| `agent.round.started` | agent 新一轮开始 | `round_index`, `input_length` |
| `agent.round.completed` | agent 一轮结束 | `pending_tools`, `output_length` |

### 12.2 Trace 示例（frame.py 场景）

```json
[
  {"event_type": "node.started", "node_name": "code_writer", "node_id": 22},
  {"event_type": "agent.round.started", "node_id": 22, "round": 1},
  {"event_type": "agent.round.completed", "node_id": 22, "round": 1, "pending_tools": true},
  {"event_type": "tool.requested", "node_id": 22, "request_ids": ["check_frame_py", "write_frame_py"]},
  {"event_type": "tool.batch.started", "node_id": 22, "batch_size": 2},
  {"event_type": "tool.started", "request_id": "check_frame_py", "tool": "python_syntax_check"},
  {"event_type": "tool.completed", "request_id": "check_frame_py", "duration_ms": 42},
  {"event_type": "tool.started", "request_id": "write_frame_py", "tool": "file_writer"},
  {"event_type": "tool.completed", "request_id": "write_frame_py", "duration_ms": 11},
  {"event_type": "tool.batch.completed", "node_id": 22, "summary": {"status": "success"}},
  {"event_type": "agent.tool_results.delivered", "node_id": 22, "tool_round": 1},
  {"event_type": "agent.round.started", "node_id": 22, "round": 2},
  {"event_type": "agent.round.completed", "node_id": 22, "round": 2, "pending_tools": false},
  {"event_type": "node.completed", "node_name": "code_writer", "node_id": 22}
]
```

---

## 13. 和当前代码的对接点

### 13.1 需要修改的文件

| 文件 | 改动内容 |
|---|---|
| `core/results.py` | 新增 `ToolRequest`, `ToolResult`, `ToolBatchResult` dataclass；扩展 `AgentRoundResult` 加 `tool_requests` |
| `core/agent.py` | 新增 `tool_execution_mode`（`disabled` / `internal` / `external`）；改造 `round_call()` 支持 external 模式（输出 tool_requests，不内部执行） |
| `core/executor_parts/engine.py` | AgentNode 执行路径加入 tool loop：agent round → tool scheduler → result 回传 → agent re-entry |
| `core/executor_parts/payloads.py` | 新增 `extract_tool_requests_from_agent_output()` 解析逻辑 |
| `core/executor_parts/`（新增） | `tool_scheduler.py` — 调度器核心实现 |
| `tools/` 或 `core/` | 各工具新增 `infer_resources()` 方法，暴露资源访问推导规则 |
| `core/policy.py` | `AgentNode` 新增 `runtime_options` 字段；`ToolNode` 标记 deprecated |
| `modules/llm_fetcher/llm_fetcher.py` | `runtime` role → `system` role 映射 |
| `web/runstore/` | trace 事件类型扩展 |

### 13.2 向后兼容

- 旧 swarm 若仍含 `ToolNode`，engine 走 legacy 路径处理。
- `Agent` 默认 `tool_execution_mode = "internal"`，不影响现有 ReAct 行为。
- 新 swarm 在 blueprint 中显式声明 `tool_execution_mode = "external"` 启用新协议。

---

## 14. v2 预留特性

以下特性不在 v1 实现，但协议设计保留扩展空间：

- `content_ref` / `source_ref`：agent 输出字段引用，避免大 payload 复制
- `context_trim_strategy`：智能摘要压缩，替代硬上限
- `tool streaming`：长耗时工具（如视频生成）的流式结果回传
- `tool checkpoint / resume`：工具执行中断后的恢复机制
- `cross-agent tool sharing`：工具结果缓存，避免重复调用

---

## 15. 附录：frame.py 理想流程（v1）

### 15.1 用户请求

```text
为我做一个 agent 系统框架... 将该文件命名为 frame.py。
```

### 15.2 执行流

```text
orchestrator (1)
→ organizer_preflight (2) — 路由到 code_writer
→ code_writer (22)
    Round 1:
      输出 JSON envelope:
        content: "import abc\n..."
        tool_requests:
          - id: check_frame_py
            tool: python_syntax_check
            args: {source: "import abc\n..."}
            required: true
            on_failure: return_to_agent
          - id: write_frame_py
            tool: file_writer
            args: {path: "outputs/frame.py", content: "import abc\n...", overwrite: true}
            depends_on: [check_frame_py]
            required: true
            resources: [{type: "file", id: "outputs/frame.py", mode: "write"}]
        next_node_ids: [20]

    ToolScheduler:
      先执行 check_frame_py（无依赖）
      成功后执行 write_frame_py（有依赖）
      两个请求无资源冲突，但存在依赖，故串行

    Round 2:
      agent 收到 tool_batch_result（两个均 success）
      输出 JSON envelope:
        content: ""
        tool_requests: []
        next_node_ids: [20]

    node.completed 发出

→ publisher (20)
→ exit
```

### 15.3 产出物

- `outputs/frame.py`：已去除 Markdown 围栏、已通过语法检查的合法 Python 文件。
- `trace.json`：完整记录 agent round、tool execution、result delivery。

---

## 16. Agent 并行执行（Agent Concurrency）

v1 支持通过 `route_policy="all"` 触发**多分支并行执行**。ExecutionGraph 保持为 AgentNode 流，但单个节点的出边可以同时激活多个下游分支。

### 16.1 触发条件

当 AgentNode 的 `metadata.route_policy == "all"` 且 `_resolve_next_targets` 返回多个目标时，executor 并行启动所有分支：

```text
research_dispatcher (node 4)
  ├─► architecture_researcher_runtime (node 31) ── parallel
  ├─► evidence_researcher_runtime (node 32) ────── parallel
  └─► risk_researcher_runtime (node 33) ────────── parallel
       │
       └─► 全部完成后 ──► organizer_checkpoint (node 17)
```

### 16.2 分支隔离

每个分支获得独立的执行状态：

```python
branch_state = state.clone()  # deep copy payload, metadata, branch_results
```

- `payload`、`metadata`、`branch_results` 均为深拷贝，分支间无共享可变状态。
- `trace` 为新的 list（条目本身是安全的 shallow copy）。

### 16.3 Agent 实例策略：并行分支自动升级

并行分支中，**`instance_policy="singleton"` 自动按 `per_call` 处理**。

原因：`Agent` 内部无锁，`_context.messages` 和 `cognitive_graph` 均为可变状态。若多个分支共享同一个 singleton 实例，会产生 race condition。

实现：
- `AgentInstancePool.acquire()` 接收上下文参数 `parallel_context=True`。
- 当 `parallel_context=True` 且 `instance_policy="singleton"` 时，行为回退到 `per_call`（调用 `clone_for_runtime()`）。
- 重试分支同样走 `per_call`，保证每次尝试都是干净的 Agent 实例。

### 16.4 失败重试策略

**原则：单个分支失败不阻断其他分支；失败分支独立重试。**

执行模型：

```text
并行启动分支 A, B, C
├─ 分支 A：成功 ✅
├─ 分支 B：node X 失败 → 等待 backoff → 整分支重试 → 成功 ✅
└─ 分支 C：成功 ✅

全部完成后 → join
```

**重试粒度：整分支重试（full branch retry）**

- 从分支入口节点重新开始。
- 使用 fresh `state.clone()`。
- 获得全新的 `per_call` Agent 实例。
- 不保留分支内前次尝试的任何中间状态。

**理由：**
- 实现简单，无需分支级 checkpoint/resume。
- Agent 上下文干净，不受失败尝试污染。
- 语义清晰：分支是独立执行单元，重试 = 重新跑一次。

**重试配置（`config.toml`）：**

```toml
[runtime.branch_retry]
max_retries = 2
backoff_ms = 1000
backoff_multiplier = 2.0
retry_policy = "full_branch"
```

**重试耗尽仍失败：**
- 该分支标记为 `failed`，但其他分支继续执行。
- Join 节点接收包含成功与失败分支的完整 `branch_results`。
- Join 节点（或下游 agent）决定如何处理部分失败（例如：忽略失败分支、请求补充研究、或整体 abort）。
- 整个 run 不因单分支失败而终止。

### 16.5 Join 语义

```text
1. 所有分支（含重试后）到达完成态（success 或 failed）
2. 收集 branch_results
3. 构造 branch_merge_payload
4. 跳转到 join_node_id（若配置）
```

`branch_merge_payload` 包含每个分支的最终状态：

```json
{
  "type": "branch_merge",
  "source_node_id": 4,
  "branches": [
    {"branch_index": 0, "status": "success", "payload": "...", "rounds": 5},
    {"branch_index": 1, "status": "success", "payload": "...", "rounds": 7},
    {"branch_index": 2, "status": "failed", "error": "Timeout", "rounds": 3, "retries_exhausted": true}
  ]
}
```

### 16.6 认知图隔离

并行分支的认知图（`cognitive_graph`）在分支内独立演化，**join 时不直接合并**。

原因：不同分支可能生成相同 `node_id` 的认知节点，直接合并会导致冲突。

方案：
- 每个分支的认知图隔离存储（如 `state.metadata["branch_cognitive_graphs"][branch_index]`）。
- Join 节点或下游 agent 按需选择性引用，不做自动合并。
- v2 再引入命名空间隔离的合并策略。

### 16.7 Trace 事件扩展

并行分支产生的事件可能交错，runstore 必须支持乱序写入：

| 事件 | 说明 |
|---|---|
| `branch.started` | 单个分支启动 |
| `branch.retry.scheduled` | 分支失败，计划重试 |
| `branch.retry.started` | 分支重试开始 |
| `branch.completed` | 分支成功完成 |
| `branch.failed` | 分支最终失败（重试耗尽） |
| `branch_merge.completed` | 所有分支完成，进入 join |

---

## 17. 全局并发限制（Global Concurrency Limits）

为防止并行分支 + 并行工具导致资源耗尽，v1 引入全局并发限制。

### 17.1 限制维度

| 维度 | 限制对象 | 目的 |
|---|---|---|
| LLM 调用 | `LLMFetcher.fetch()` | API rate limit、成本控制、上下文压力 |
| 工具调用 | `ToolScheduler.execute_batch()` 中的单个工具执行 | I/O 资源、CPU 资源 |
| 分支并行 | `engine.py` 中单个 fan-out 的并行分支数 | 内存控制、防止爆炸式分支 |

### 17.2 配置项（`config.toml`）

```toml
[runtime.concurrency]
max_parallel_llm_calls = 5      # 全局同时 LLM 调用上限
max_parallel_tool_calls = 10    # 全局同时工具调用上限
max_parallel_branches = 3       # 单个 fan-out 的最大并行分支数
```

### 17.3 ConcurrencyLimiter 设计

```python
# core/runtime/limiter.py
class ConcurrencyLimiter:
    def __init__(self, config: dict):
        self.llm_semaphore = asyncio.Semaphore(config.get("max_parallel_llm_calls", 5))
        self.tool_semaphore = asyncio.Semaphore(config.get("max_parallel_tool_calls", 10))
        self.max_parallel_branches = config.get("max_parallel_branches", 3)

    async def acquire_llm(self):
        await self.llm_semaphore.acquire()

    def release_llm(self):
        self.llm_semaphore.release()

    async def acquire_tool(self):
        await self.tool_semaphore.acquire()

    def release_tool(self):
        self.tool_semaphore.release()

    def get_branch_batch_size(self, total_branches: int) -> int:
        return min(total_branches, self.max_parallel_branches)
```

### 17.4 各层接入点

**LLMFetcher（`modules/llm_fetcher/llm_fetcher.py`）：**

```python
async def fetch(self, ...):
    await self.limiter.acquire_llm()
    try:
        return await self._create_completion(...)
    finally:
        self.limiter.release_llm()
```

**ToolScheduler（`core/executor_parts/tool_scheduler.py`）：**

```python
async def execute_batch(self, tool_requests, ...):
    # 对并行组内的每个工具请求 acquire_tool / release_tool
```

**Engine（`core/executor_parts/engine.py`）：**

```python
# 如果分支数超过 max_parallel_branches，分批 gather
batch_size = limiter.get_branch_batch_size(len(next_targets))
for batch in batched(next_targets, batch_size):
    results = await asyncio.gather(*[run_branch(...) for ... in batch])
```

---

## 18. 补充对接点

在 §13 基础上补充以下改动：

| 文件 | 改动 |
|---|---|
| `config.toml` | 新增 `[runtime.concurrency]` 和 `[runtime.branch_retry]` |
| `core/config.py` | 解析并发与重试配置 |
| `core/runtime/limiter.py` | **新增** 全局并发限制器 |
| `core/runtime/registry.py` | `AgentInstancePool.acquire()` 支持 `parallel_context` 参数 |
| `core/executor_parts/engine.py` | `route_policy=="all"` 改为 `asyncio.gather` + 重试逻辑 + 分批 |
| `modules/llm_fetcher/llm_fetcher.py` | `fetch()` 前后加 LLM semaphore |
| `docs/tool_request_protocol_v1.md` | 本文档（已更新） |

---

*文档版本: v1.1-frozen*  
*新增：Agent 并行执行（§16）、全局并发限制（§17）*  
*后续代码实现必须以此文档为契约。*
