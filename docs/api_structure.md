# 当前 API 结构说明

本文档总结当前项目的 FastAPI 形态、返回结构，以及它和 `core/` 运行时之间的关系。

## 1. API 总体定位

当前 API 是一个后端运行时接口层，职责是：

- 加载 swarm 包
- 暴露健康检查和 readiness 检查
- 列出已加载的 swarm
- 触发 swarm 运行
- 触发单个 agent 的单轮调用

API 本身不负责：

- 解析 swarm 包文件
- 构建 agent / tool / graph 对象
- 执行 LLM 业务逻辑

这些都由 `core/` 和 `web/app_factory.py` 协作完成。

## 2. 服务入口

当前服务入口是 `app.py`。

启动时会：

- 读取 `config.toml`
- 扫描 `agents/` 下的 swarm 包
- 创建 FastAPI app
- 注册 health 和 swarm 路由

## 3. 当前路由

当前项目对外 API 统一使用 `/api` 前缀。

### 3.1 `GET /api/runtime/health`

基础存活检查。

返回示例：

```json
{
  "success": true,
  "status": "ok"
}
```

### 3.2 `GET /api/runtime/ready`

检查当前运行时是否可用。

行为：

- 如果没有加载任何 swarm，返回 `503`
- 如果某个 swarm 的 Agent 图不可用，也返回 `503`
- 否则返回可用状态

返回示例：

```json
{
  "success": true,
  "ready": true,
  "swarm_count": 1
}
```

### 3.3 `GET /`

服务首页信息。

返回内容包含：

- `service`
- `swarm_count`
- `load_error`

### 3.4 `GET /api`

API 首页信息。它和 `/` 的内容基本一致，但用于统一前后端的 API 根路径。

### 3.5 `GET /api/swarms`

列出所有已加载的 swarm。

每个 swarm 的摘要信息包括：

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

### 3.6 `GET /api/swarms/<swarm_name>`

查看单个 swarm 的详情。

返回内容包括：

- `graph_file`
- `agent_files`
- `agent_count`
- `skill_count`
- `tool_count`
- `graph_attached`
- `graph_valid`
- `graph_errors`
- `graph_warnings`

### 3.7 `POST /api/swarms/<swarm_name>/runs/execute`

执行指定 swarm 的工作图。

请求体示例：

```json
{
  "input": {
    "text": "write a summary"
  },
  "rounds": 0
}
```

返回示例：

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

说明：

- `input` 会作为图的初始 payload
- `rounds` 会作为初始轮次计数
- `output` 是图最终 payload
- `trace` 是执行轨迹
- `metadata` 是执行状态附加信息

### 3.8 `POST /api/swarms/<swarm_name>/agents/<agent_id>/round`

直接驱动某个 agent 执行一轮。

请求体示例：

```json
{
  "message": "hello",
  "rounds": 0,
  "additional_prompt": "Be concise."
}
```

返回内容包括：

- `result`
- `context`

其中：

- `result` 是这轮 agent 调用结果
- `context` 是该 agent 的隔离上下文快照

### 3.9 `GET /api/swarms/<swarm_name>/agent-graph`

返回当前 swarm 的 Agent 图快照。

返回内容包括：

- `graph_name`
- `graph_kind`
- `entry_node_id`
- `exit_node_id`
- `node_count`
- `edge_count`
- `nodes`
- `edges`

### 3.10 `GET /api/swarms/<swarm_name>/execution-graph`

返回当前 swarm 的完整执行图快照。

### 3.11 `GET /api/swarms/<swarm_name>/execution-traces/latest`

返回当前 swarm 最新 run 的执行轨迹。

这个接口用于前端先把“静态图”画出来，再叠加实时运行态。

### 3.12 `POST /api/swarms/<swarm_name>/runs`

启动一个异步 run session。

请求体与同步 `/runs/execute` 基本一致：

```json
{
  "input": {
    "text": "write a summary"
  },
  "rounds": 0
}
```

返回示例：

```json
{
  "success": true,
  "status": "started",
  "swarm": "deepseek_demo",
  "run": {
    "run_id": "9f2c...",
    "status": "running",
    "events_url": "/api/runs/9f2c.../events",
    "status_url": "/api/runs/9f2c..."
  }
}
```

这个接口不会等待图执行结束，而是返回一个 `run_id` 供后续查询和订阅。

### 3.13 `POST /api/swarms/<swarm_name>/runs/stop`

对指定 swarm 的所有活跃 run 发起停止请求。

请求体：

```json
{
  "stop_type": "soft"
}
```

- `stop_type`：`soft`（允许当前节点完成后停止）或 `hard`（立即终止）

返回示例：

```json
{
  "success": true,
  "stopped": 2
}
```

说明：

- 该接口会遍历该 swarm 下所有 `active_run_ids`，对每个 run 调用 `registry.stop_run()`
- 如果没有活跃 run，返回 `{"success": true, "stopped": 0}`
- 前端 stop 按钮在两种场景下都会调用此接口：
  - 当没有 `activeRun` 时，直接调用 swarm-level stop
  - 当有 `activeRun` 时，优先按 `run_id` 停止，失败时回退到 swarm-level stop

### 3.11 `GET /api/runs/<run_id>`

查询一个异步 run session 的当前状态。

返回内容包括：

- `status`
- `rounds`
- `current_node_id`
- `current_node_name`
- `current_node_type`
- `state`
- `final_state`
- `error`
- `event_count`
- `events_url`
- `status_url`

这个接口适合轮询式前端，也适合调试当前执行进度。

### 3.12 `GET /api/runs/<run_id>/events`

订阅一个异步 run session 的 SSE 事件流。

该流会持续推送：

- `run.started`
- `node.started`
- `node.completed`
- `node.failed`
- `branch.started`
- `branch.completed`
- `branch.failed`
- `run.completed`
- `run.failed`

SSE 事件体是 JSON 字符串，前端可用来实时高亮当前节点、更新 trace 面板、展示分支状态。
连接建立后，后端会先推送一条 `run.snapshot` 作为初始状态。

更详细的实时执行协议见：

- [docs/backend/runs.md](/run/media/luna/数据和游戏/Codes/Python/angelus/docs/backend/runs.md)

## 4. 错误处理

当前 API 使用统一错误处理。

### 4.1 `ApiError`

用于 HTTP 友好的业务错误。

### 4.2 `NotFoundError`

返回 `404`。

### 4.3 `ConflictError`

返回 `409`。

### 4.4 `SwarmLoaderError`

用于 swarm 包加载失败，通常映射为 `500`。

### 4.5 `ValueError`

通常映射为 `400`。

### 4.6 未捕获异常

会被统一包装为 JSON 错误响应。

## 5. 运行时绑定关系

当前 FastAPI app 会把运行时注册表放到：

- `app.extensions["angelus_runtime"]`

这个注册表里主要包含：

- `config_path`
- `root_config`
- `swarms`
- `load_error`
- `runs`

路由层只消费这个注册表，不直接碰文件系统。

## 6. 与 core 的关系

API 层只负责调用 runtime，不直接执行业务逻辑。

典型流程是：

1. FastAPI 路由接收请求
2. 根据 swarm 名称找到已加载运行时
3. 调用 `ExecutionGraph.run(...)` 或 `Agent.round_call(...)`
4. 把结果转成 JSON 返回

## 7. 当前 API 的特点

- 只读接口已经完整
- 运行接口已经可用
- 图执行支持动态改图
- Agent 上下文隔离
- 返回结果统一 JSON 化

## 8. 后续可扩展方向

如果后面继续扩展 API，比较自然的方向有：

- `GET /swarms/<name>/agents`
- `GET /swarms/<name>/skills`
- `GET /swarms/<name>/agent-graph`
- `POST /swarms/<name>/agent-graph/edit`
- `POST /swarms/<name>/tools/<tool_name>/execute`

这些接口适合调试、运维和可视化，但现在还不是必须项。
