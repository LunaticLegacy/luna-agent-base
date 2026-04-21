# 当前 API 结构说明

本文档总结当前项目的 Flask API 形态、返回结构，以及它和 `core/` 运行时之间的关系。

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
- 创建 Flask app
- 注册 health 和 swarm 路由

## 3. 当前路由

### 3.1 `GET /health`

基础存活检查。

返回示例：

```json
{
  "success": true,
  "status": "ok"
}
```

### 3.2 `GET /ready`

检查当前运行时是否可用。

行为：

- 如果没有加载任何 swarm，返回 `503`
- 如果某个 swarm 的执行图不可用，也返回 `503`
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

### 3.4 `GET /swarms`

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

### 3.5 `GET /swarms/<swarm_name>`

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

### 3.6 `POST /swarms/<swarm_name>/run`

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

### 3.7 `POST /swarms/<swarm_name>/agents/<agent_id>/round`

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

当前 Flask app 会把运行时注册表放到：

- `app.extensions["angelus_runtime"]`

这个注册表里主要包含：

- `config_path`
- `root_config`
- `swarms`
- `load_error`

路由层只消费这个注册表，不直接碰文件系统。

## 6. 与 core 的关系

API 层只负责调用 runtime，不直接执行业务逻辑。

典型流程是：

1. Flask 路由接收请求
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
- `GET /swarms/<name>/graph`
- `POST /swarms/<name>/graph/edit`
- `POST /swarms/<name>/tools/<tool_name>/execute`

这些接口适合调试、运维和可视化，但现在还不是必须项。

