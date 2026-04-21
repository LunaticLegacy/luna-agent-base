# 当前前端 API 映射说明

本文档总结当前 Angelus 项目中 Angular 前端如何消费后端 API，以及页面状态如何驱动这些请求。

## 1. 前端 API 总体定位

前端的职责是：

- 读取后端运行时状态
- 展示 swarm 列表和详情
- 触发 swarm 执行
- 触发单个 agent 的单轮调用
- 将后端返回的 JSON、错误和诊断信息可视化

前端不负责：

- 解析 swarm 包
- 构建 runtime 对象
- 执行 graph / agent / tool 逻辑

这些都由 Flask 后端和 `core/` 运行时完成。

## 2. API Service Methods

当前 Angular API 请求封装位于 `frontend/angelus/src/app/api.service.ts`。

### 2.1 `index(baseUrl = '/api')`

请求：

- `GET /api`

用途：

- 获取 API root 信息
- 显示 `service`
- 显示 `swarm_count`
- 显示 `load_error`
- 显示 `api_root`

### 2.2 `health(baseUrl = '/api')`

请求：

- `GET /api/health`

用途：

- 检查服务是否存活
- 用于页面概览中的 health 状态

### 2.3 `ready(baseUrl = '/api')`

请求：

- `GET /api/ready`

用途：

- 检查后端 runtime 是否已准备好
- 用于页面概览中的 ready 状态

### 2.4 `listSwarms(baseUrl = '/api')`

请求：

- `GET /api/swarms`

用途：

- 获取当前已加载的 swarm 列表
- 驱动左侧 swarm registry

### 2.5 `getSwarm(baseUrl, swarmName)`

请求：

- `GET /api/swarms/<swarmName>`

用途：

- 获取单个 swarm 的详细信息
- 包括 `agent_files`、`graph_valid`、`graph_errors`、`graph_warnings`

### 2.6 `runSwarm(baseUrl, swarmName, request)`

请求：

- `POST /api/swarms/<swarmName>/run`

用途：

- 触发整个 swarm 的 graph 执行
- 请求体包含 `input` 和 `rounds`

### 2.7 `runAgentRound(baseUrl, swarmName, agentId, request)`

请求：

- `POST /api/swarms/<swarmName>/agents/<agentId>/round`

用途：

- 直接驱动某个 agent 执行一轮
- 请求体包含 `message`、`rounds`、`additional_prompt`

## 3. App State Flow

当前页面主组件位于 `frontend/angelus/src/app/app.ts`。

### 3.1 主要状态

页面状态主要由以下 signal 管理：

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

### 3.2 状态流转

页面初始化时会执行 `loadOverview()`。

当用户：

- 点击 swarm
- 刷新概览
- 运行 swarm
- 运行 agent

这些操作都会更新上面的状态，并驱动模板重绘。

## 4. Overview Loading

概览加载发生在 `App` 构造函数中。

### 4.1 加载内容

`loadOverview()` 会并发请求：

- `index('/api')`
- `health('/api')`
- `ready('/api')`
- `listSwarms('/api')`

### 4.2 概览展示

概览区域会展示：

- API root
- health 状态
- ready 状态
- 已加载 swarm 数量

### 4.3 失败行为

如果任一请求失败：

- `catch` 会捕获错误
- `error` signal 会被写入
- 页面顶部错误框会显示诊断信息

## 5. Swarm Selection

左侧 swarm registry 来自 `swarms` signal。

### 5.1 选择方式

用户点击某个 swarm 后：

- `selectSwarm(swarmName)` 被调用
- `selectedSwarmName` 更新
- `reloadSelectedSwarm()` 拉取详情

### 5.2 选择后的默认 agent

当 swarm 详情加载成功后：

- `syncAgentDefaults()` 会根据 `agent_files` 推导可用 agent
- 如果存在 `planner`，优先选择 `planner`
- 否则选第一个可用 agent

### 5.3 作用

选择 swarm 后会同步更新：

- 详情面板
- 可用 agent 下拉框
- 默认 agent round 输入内容

## 6. Swarm Detail Loading

详情加载由 `reloadSelectedSwarm()` 完成。

### 6.1 请求

- 调用 `getSwarm(apiBaseUrl(), selectedSwarmName)`

### 6.2 成功后更新

成功后会写入：

- `selectedSwarm`
- `selectedAgentId`
- 默认 agent message

### 6.3 失败后表现

如果详情接口失败：

- `error` 会显示可读化的 HTTP 错误信息
- 当前 swarm 详情不会更新

## 7. Swarm Execution

Swarm 执行由 `runSwarm()` 触发。

### 7.1 输入来源

执行请求使用：

- `swarmInput`
- `swarmRounds`

### 7.2 请求行为

`runSwarm()` 会：

- 解析 `swarmInput` 文本为 JSON
- 调用 `runSwarm(apiBaseUrl(), swarmName, { input, rounds })`
- 将返回结果写入 `swarmRunOutput`

### 7.3 页面反馈

执行结果会显示在：

- `Swarm result`

如果执行出错：

- `error` 会显示错误详情
- `loading` 会在完成后恢复

## 8. Agent Round Execution

单 agent round 由 `runSelectedAgent()` 触发。

### 8.1 输入来源

请求体来源于：

- `agentMessage`
- `agentRounds`
- `agentAdditionalPrompt`

### 8.2 请求行为

`runSelectedAgent()` 会：

- 确认当前已选 swarm
- 确认当前已选 agent
- 调用 `runAgentRound(apiBaseUrl(), swarmName, agentId, request)`
- 将返回结果写入 `agentRunOutput`

### 8.3 页面反馈

执行结果会显示在：

- `Agent result`

当前页面的 agent round 是“直接调用单个 agent”，不是通过 graph 编排触发。

## 9. Error Display

当前错误展示位于 `frontend/angelus/src/app/app.ts` 的 `formatError()`。

### 9.1 错误格式化策略

优先级大致是：

1. `HttpErrorResponse`
2. 普通 `Error`
3. 普通对象
4. 其他值的字符串化

### 9.2 HTTP 错误展开

对于 HTTP 错误，前端会尽量展示：

- 状态码
- 状态文本
- 请求 URL
- 返回体里的 `error` / `message` / `reason` / `detail`

### 9.3 页面展示位置

错误会显示在：

- 右上角错误框

这避免了以前直接显示 `[object Object]` 的问题。

## 10. Proxy and Base URL Configuration

当前前端的 API 访问统一基于 `/api`。

### 10.1 默认 base URL

`apiBaseUrl` 的默认值是：

- `/api`

### 10.2 开发代理

`frontend/angelus/proxy.conf.json` 将：

- `/api`

代理到：

- `http://127.0.0.1:5000`

当前代理不做 path rewrite，只负责透传。

### 10.3 页面可编辑

页面右上角提供了 API base URL 输入框。

这意味着：

- 开发时可以切换后端地址
- 默认还是使用 `/api`

## 11. Frontend Responsibilities Summary

当前 Angular 前端的职责可以概括为：

- 作为 Angelus runtime 的控制台
- 读取 API 根、health、ready、swarm 列表和 swarm 详情
- 提供 swarm 选择和 agent 选择入口
- 触发 swarm 执行和 agent round
- 展示结果、错误和诊断信息
- 通过代理把 `/api` 请求转到 Flask 后端

前端不参与执行逻辑，只负责把 runtime 暴露为可视化界面和交互入口。
