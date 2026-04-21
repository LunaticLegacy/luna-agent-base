# 后端 API 与调度映射说明

本文档只描述后端侧当前的 API 入口、请求如何进入 `Flask`、再如何分发到 `Core` / `ExecutionGraph` / `Agent` / `Tool`，以及每个接口的返回形态。

## 1. 后端职责边界

当前后端的职责是：

- 读取根配置和 swarm 包
- 构建运行时注册表
- 暴露健康检查、就绪检查和 swarm 调度接口
- 将 HTTP 请求分发到 runtime 对象
- 返回结构化 JSON 结果

后端不直接承担的职责：

- 不在路由层里手写业务流程
- 不在 Flask 层里解析 prompt / skill / tool 细节
- 不把 graph 执行逻辑写进 HTTP handler

真正的 runtime 行为由 `core/` 负责。

## 2. API Root

当前对外统一前缀是 `/api`。

### `GET /api`

API 首页，用于前端和调试工具确认服务状态。

返回字段：

- `success`
- `service`
- `swarm_count`
- `load_error`
- `api_root`

返回示例：

```json
{
  "success": true,
  "service": "angelus",
  "swarm_count": 1,
  "load_error": null,
  "api_root": "/api"
}
```

对应实现位于 `web/app_factory.py`。

### `GET /`

服务首页，和 `/api` 类似，但不带 `api_root` 字段。

返回字段：

- `success`
- `service`
- `swarm_count`
- `load_error`

## 3. Health / Ready

### `GET /api/health`

基础存活检查。

调度方式：

- 只要 Flask 应用正在运行，就返回 `200`
- 不检查 swarm 是否加载成功
- 不检查 graph 是否完整

返回示例：

```json
{
  "success": true,
  "status": "ok"
}
```

### `GET /api/ready`

运行时就绪检查。

调度顺序：

1. 检查 runtime 是否有 `load_error`
2. 检查是否至少加载了一个 swarm
3. 逐个检查每个 swarm 的 execution graph 是否可用
4. 只要有一个 swarm 不可用，就返回 `503`

典型返回：

```json
{
  "success": true,
  "ready": true,
  "swarm_count": 1
}
```

失败时可能返回：

```json
{
  "success": false,
  "ready": false,
  "reason": "swarm load error",
  "load_error": "..."
}
```

或：

```json
{
  "success": false,
  "ready": false,
  "reason": "no swarms loaded"
}
```

或：

```json
{
  "success": false,
  "ready": false,
  "invalid_swarms": [
    {
      "swarm": "deepseek_demo",
      "errors": ["..."]
    }
  ]
}
```

## 4. Swarm List / Detail

### `GET /api/swarms`

列出所有已加载的 swarm。

调度方式：

- 从 `app.extensions["angelus_runtime"]` 里取 `swarms`
- 对每个 swarm 调 `core.check_execution_graph_available()`
- 汇总为列表返回

每个条目包含：

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

返回示例：

```json
{
  "success": true,
  "swarms": [
    {
      "swarm_name": "deepseek_demo",
      "package_path": "...",
      "manifest_path": "...",
      "graph_file": "graph.py",
      "agent_count": 5,
      "skill_count": 5,
      "tool_count": 3,
      "graph_attached": true,
      "graph_valid": true,
      "graph_errors": [],
      "graph_warnings": []
    }
  ]
}
```

### `GET /api/swarms/<swarm_name>`

查看单个 swarm 的详情。

调度方式：

- 先按 `swarm_name` 在 runtime registry 中查找 swarm
- 找不到则返回 `404`
- 找到后再次检查 graph 有效性

返回内容包含：

- `swarm_name`
- `package_path`
- `manifest_path`
- `graph_file`
- `agent_files`
- `agent_count`
- `skill_count`
- `tool_count`
- `graph_attached`
- `graph_valid`
- `graph_errors`
- `graph_warnings`

## 5. Swarm Run

### `POST /api/swarms/<swarm_name>/run`

触发整个 swarm 的执行图运行。

请求体：

```json
{
  "input": {
    "text": "write a summary"
  },
  "rounds": 0
}
```

调度方式：

1. 先查找 swarm
2. 取出 swarm 绑定的 `ExecutionGraph`
3. 如果 graph 为空，返回 `400`
4. 读取请求体里的 `input`
5. 读取请求体里的 `rounds`
6. 调 `await graph.run(swarm.core, payload, rounds=rounds)`

图执行会继续分发到：

- `AgentNode` -> `core.get_agent(...)` -> `agent.round_call(...)`
- `ToolNode` -> `core.get_tool(...)` -> `tool.execute(...)`
- 分支节点 -> `ExecutionGraph` 的分支和汇合逻辑

返回字段：

- `success`
- `swarm`
- `rounds`
- `output`
- `trace`
- `metadata`

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

其中：

- `output` 是最终 `ExecutionState.payload`
- `trace` 是执行轨迹
- `metadata` 是执行状态附加信息

## 6. Agent Round

### `POST /api/swarms/<swarm_name>/agents/<agent_id>/round`

直接驱动某个 agent 执行一轮。

请求体：

```json
{
  "message": "hello",
  "rounds": 0,
  "additional_prompt": "Be concise."
}
```

调度方式：

1. 先查找 swarm
2. 再在 swarm 的 `Core` 中查找 agent
3. 读取 `message`
4. 如果 `message` 为空，返回 `400`
5. 读取 `rounds`
6. 读取可选的 `additional_prompt`
7. 调 `await agent.round_call(...)`

返回字段：

- `success`
- `swarm`
- `agent_id`
- `result`
- `context`

其中：

- `result` 是这轮 agent 调用结果
- `context` 是该 agent 的隔离上下文快照

## 7. Runtime Loading

当前 runtime 加载链路是：

1. `app.py` 调 `web.app_factory.create_app()`
2. `create_app()` 读取 `config.toml`
3. `load_root_config()` 解析根配置
4. `load_all_swarms()` 扫描 `agents/`
5. `load_all_swarms()` 先预装 `tool_requirements.txt`
6. 对每个 swarm 包：
   - `load_swarm_manifest()`
   - `load_agent_blueprints()`
   - `load_skill_assets()`
   - 创建 `Core`
   - 注册 skills
   - 创建 agents
   - 加载 tools
   - 加载 graph
   - `core.set_execution_graph(graph)`
7. 最终把运行时注册表放到 `app.extensions["angelus_runtime"]`

### 运行时注册表内容

当前注册表主要包含：

- `config_path`
- `root_config`
- `swarms`
- `load_error`

### 启动日志

加载阶段会输出：

- 发现了多少 swarm 包
- 哪个 swarm 包正在加载
- 加载了多少 agent / skill / tool
- graph 是否 ready
- graph 的 warnings / errors
- swarm 是否最终加载完成

这对调试 swarm 包非常关键。

## 8. Error Handling

当前后端错误处理分三层：

### 8.1 业务错误

通过 `web.errors.ApiError`、`NotFoundError` 等包装，返回 JSON 错误体。

常见映射：

- `NotFoundError` -> `404`
- `ApiError` -> `4xx` 或 `5xx`，取决于错误类型

### 8.2 请求参数错误

例如：

- `message` 为空
- `swarm_name` 不存在
- `graph` 没有挂载

通常返回 `400` 或 `404`

### 8.3 加载 / 运行错误

例如：

- swarm 包无法解析
- graph 文件不存在
- graph 不是 `ExecutionGraph`
- agent / tool / skill 依赖缺失
- graph 执行时抛异常

这类错误通常会：

- 在启动期进入 `load_error`
- 或在执行期返回 `500`

### 8.4 Readiness 错误

`/api/ready` 如果不通过，会返回 `503`，并说明：

- `swarm load error`
- `no swarms loaded`
- `invalid_swarms`

## 9. 后端调度方式总览

从请求进入到 runtime 执行，整体链路是：

- Flask 路由接收请求
- 从 `app.extensions["angelus_runtime"]` 取运行时注册表
- 定位到 swarm
- 定位到 `Core`
- 再进入：
  - `ExecutionGraph.run(...)`
  - 或 `Agent.round_call(...)`
  - 或 `Tool.execute(...)`

### 具体职责

- `web/app_factory.py`
  - 创建 app
  - 加载 runtime
  - 挂载路由
  - 提供 `/api` 根入口
- `web/routes/health.py`
  - 提供 health / ready
- `web/routes/swarms.py`
  - 提供 swarm 列表、详情、run、agent round
- `core/swarm_loader.py`
  - 加载 swarm 包
  - 装配 `Core`
  - 注册 agent / skill / tool / graph
- `core/executor.py`
  - 负责 graph 调度
- `core/agent.py`
  - 负责单 agent round 调用
- `tools/`
  - 负责工具能力，包含可改图工具

## 10. 简短总结

当前后端的定位很明确：

- `Flask` 负责 HTTP 入口
- `Core` 负责 runtime 容器和资源管理
- `ExecutionGraph` 负责图编排
- `Agent` 负责单轮推理
- `Tool` 负责外部能力扩展
- `swarm_loader` 负责把磁盘上的 swarm 包装配成 runtime

也就是说，后端 API 只是“触发器”和“结果出口”，真正的调度和执行都发生在 `core/`。
