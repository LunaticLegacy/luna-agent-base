# Overview 页面

`Overview` 是前端的系统总览页，核心职责是把全局状态、当前 Swarm、图谱、实时事件和运行控制聚合到一个页面里。它不是静态仪表盘，而是直接驱动后端 API 读取与执行。

## 当前页面结构

页面当前可见区块如下：

1. 顶部标题区
   - 标题是“系统概览”
   - 有一个“刷新数据”按钮

2. 第一行状态卡片
   - 系统状态
   - 总 Agents
   - Swarm 数量
   - 当前任务
   - Graph 状态
   - 事件流数量

3. 中间主区，左右两栏
   - 左栏是 Swarm 列表
   - 右栏是 Swarm 详情
   - 详情里包含 Agent 图和实时活动列表

4. 执行控制台
   - Swarm 运行
   - Agent 调试

5. 响应记录
   - 展示最近的接口响应摘要

6. 底部指标卡片
   - CPU 使用率
   - 内存占用
   - 请求延迟
   - 吞吐速率
   - Token 用量
   - 错误率

7. 系统信息
   - API Base URL
   - Health
   - Ready
   - Selected Swarm
   - Stream State
   - Error Detail

## 数据来源

这个页面的数据几乎全部来自 [`StateService`](../../frontend/angelus/src/app/services/state.service.ts)。

页面初始化时会执行 `state.loadOverview()`，随后继续加载：

- 全局索引、健康和就绪状态
- Swarm 列表
- 事件列表
- 日志列表
- 指标数据
- 知识库列表
- 记忆库列表

选中某个 Swarm 后，还会再加载该 Swarm 的：

- 详情
- 图谱
- Agents
- Tasks
- Tools
- 统计信息

如果某些接口失败，`StateService` 会保留已经拿到的数据，并尽量用本地派生数据继续渲染页面。

## 使用到的 API

`Overview` 相关的真实接口都由 [`ApiService`](../../frontend/angelus/src/app/api.service.ts) 发起：

- `GET /api`
- `GET /api/health`
- `GET /api/ready`
- `GET /api/swarms`
- `GET /api/swarms/{swarmName}`
- `GET /api/swarms/{swarmName}/graph`
- `GET /api/swarms/{swarmName}/agents`
- `GET /api/swarms/{swarmName}/stats`
- `GET /api/tasks`
- `GET /api/tools`
- `GET /api/events`
- `GET /api/logs`
- `GET /api/metrics`
- `GET /api/knowledge`
- `GET /api/memory`
- `POST /api/swarms/{swarmName}/start`
- `POST /api/swarms/{swarmName}/start/background`
- `POST /api/swarms/{swarmName}/agents/{agentId}/round`

另外，`ApiService` 里对部分启动接口带了回退逻辑：

- `startSwarm()` 先打 `/start`，遇到 `405` 时回退到 `/run`
- `startSwarmBackground()` 现在直接打 `/start/background`
- `getRun()` 现在直接访问 `/swarms/runs/{runId}`

## 页面交互

当前页面已经实现的交互包括：

- 点击“刷新数据”重新拉取 Overview 所需的数据
- 在 Swarm 列表里点击某一项切换当前 Swarm
- 点击“启动结构”发起 Swarm 执行
- 点击“后台启动”发起后台运行，并监听 SSE 事件流
- 在执行控制台里修改任务模板、轮次、输出风格、Meta 模式、执行目标、补充上下文
- 在 Agent 调试区选择 Agent 并发起单轮调试
- 点击“Error Detail”把错误详情复制到剪贴板

页面还会把运行过程中的结果追加到：

- `responseFeed`
- `liveEvents`

这样右侧和底部的多个区域会跟着动态更新。

## 现在的实现特点

- 页面标题和大部分卡片标题已经是中文，并且全部基于真实状态字段渲染
- `Swarm` 选择后，右侧详情、Agent 图和统计会联动更新
- Agent 图优先使用选中 Swarm 自带的 graph，缺失时再走单独的 graph 接口
- 指标卡片支持后端指标，也支持本地 fallback 数据
- 实时运行会通过 `EventSource` 监听 `run.events_url`
- `StateService` 会为页面构造派生数据，例如 agent、task、tool、event、knowledge、memory 的摘要视图

## 限制

- 页面没有提供 `API Base URL` 的输入框，虽然状态层支持修改，但当前 UI 只展示，不编辑
- 没有 Swarm 的创建、删除、卸载、重载入口
- 没有任务、事件、日志、知识库、记忆库的筛选和分页控制
- 没有独立的运行历史列表，只能通过当前运行和响应记录侧面观察
- `Swarm` 运行控制依赖后端接口可用性，若接口不支持 `/start` 或 `/start/background`，会走回退路径，但前端本身不保证这些动作一定成功
- 响应记录和实时事件列表都有数量上限，超过后会截断旧项

- 现在可以做的事：
  - 看到当前系统健康状态、Swarm 数量、图谱状态和实时事件
  - 选择某个 Swarm 并查看它的 Agent 图、Agents、统计和活动
  - 直接发起 Swarm 结构启动、后台启动和 Agent 单轮调试
  - 查看最近的接口响应、系统指标和系统信息

- 现在还不能做的事：
  - 不能在这个页面里新增、删除或重载 Swarm
  - 不能在这个页面里直接编辑 API Base URL
  - 不能对任务、日志、事件、知识库、记忆库做完整 CRUD 或复杂查询
  - 不能在 UI 里显式停止、暂停或管理历史运行
