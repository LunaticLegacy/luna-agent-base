# Agents 页面实现现状

本文只记录 `frontend/angelus/src/app/pages/agents.page.ts` 以及其依赖的 `state.service.ts`、`api.service.ts` 中与 Agents 板块相关的实现现状。

## 1. 页面定位

当前 `Agents` 页面更像是一个“Agents 清单 + 状态查看 + 详情抽屉”的管理面板，而不是完整的 Agent 市场或配置中心。

页面已经实现了：

- Agents 汇总指标展示
- 本地筛选与分页
- Agents 列表表格
- 右侧详情抽屉
- 单个 Agent 的“调试”入口按钮

页面尚未实现的部分会在文末单独说明。

## 2. 页面结构

`AgentsPageComponent` 位于：

- [`frontend/angelus/src/app/pages/agents.page.ts`](/run/media/luna/数据和游戏/Codes/Python/angelus/frontend/angelus/src/app/pages/agents.page.ts)

页面主要由以下几个区域组成：

- 顶部统计卡片
- Tabs 切换条
- 过滤栏
- Agents 表格
- 分页栏
- 右侧详情抽屉

### 2.1 统计卡片

页面顶部展示 5 个指标：

- 总 Agents
- 活跃 Agents
- 总任务执行
- 平均响应时间
- 总 Token 消耗

这些指标都来自 `state.agentStats()` 和 `state.totalAgents()`，不是页面本地计算。

## 3. 筛选能力

页面提供的是前端内存筛选，不是额外发请求的服务端筛选。

筛选条件包括：

- 搜索框：按 `name` 或 `id` 模糊匹配
- 状态筛选：`online` / `offline` / `busy` / `error`
- 类型筛选：`coordinator` / `worker` / `specialist` / `reviewer`
- 能力筛选：`llm` / `tool` / `memory` / `planning`
- 标签筛选：`core` / `experimental` / `production`
- 仅看在线：只保留 `status === 'online'`

筛选逻辑在：

- [`frontend/angelus/src/app/pages/agents.page.ts`](/run/media/luna/数据和游戏/Codes/Python/angelus/frontend/angelus/src/app/pages/agents.page.ts)

核心实现是 `filteredAgents()` 这个 computed，它直接基于 `state.derivedAgents()` 做过滤。

### 3.1 注意点

当前筛选只是 UI 层逻辑，没有：

- URL 同步
- 服务端分页
- 服务端搜索
- 筛选条件持久化

## 4. 列表展示

Agents 列表是一个表格，列字段包括：

- Agent
- 状态
- 类型
- 能力 / 标签
- 任务执行
- 成功率
- 响应时间
- Token 消耗
- 最后活动
- 操作

表格数据来自 `paginatedAgents()`，也就是先筛选再分页后的结果。

### 4.1 行内展示规则

每行会展示：

- `name`
- `id`
- `status` 状态徽章
- `type`
- 前两个 capability
- 前两个 tag
- `tasksExecuted`
- `successRate` 百分比和进度条
- `avgResponseTime`
- `tokenUsage`
- `lastActivity`

### 4.2 空状态

如果没有匹配数据，会显示：

- “没有找到匹配的 Agent”

## 5. 详情抽屉

点击任意 Agent 行，会打开右侧详情抽屉。

抽屉当前展示：

- 基本信息
- 实时指标
- 资源使用
- 标签

### 5.1 基本信息

展示字段包括：

- 状态
- 类型
- 任务执行
- 成功率
- 响应时间
- Token 消耗
- 最后活动

### 5.2 实时指标

当前是静态 sparkline 数据，来自页面内写死的：

- `sparkHeights()`

它不是实时接口返回值，也没有轮询更新。

### 5.3 资源使用

CPU / 内存 / 网络条形图目前也是静态占位值：

- CPU 28%
- 内存 45%
- 网络 12%

这部分没有接后端接口。

### 5.4 标签展示

抽屉会把：

- `tags`
- `capabilities`

全部列出来。

## 6. Tabs

页面顶部有 4 个 Tabs：

- Agents列表
- Agent市场
- 我的收藏
- 已禁用

当前实现里，`activeTab` 只是本地 signal，点击后只会改变高亮状态。

没有看到与 Tab 对应的不同数据源、不同页面内容或路由切换逻辑。

换句话说，Tabs 目前是视觉占位，不是完整业务切换。

## 7. 数据来源

Agents 页面本身不直接请求接口，而是依赖 `StateService`。

相关文件：

- [`frontend/angelus/src/app/services/state.service.ts`](/run/media/luna/数据和游戏/Codes/Python/angelus/frontend/angelus/src/app/services/state.service.ts)
- [`frontend/angelus/src/app/api.service.ts`](/run/media/luna/数据和游戏/Codes/Python/angelus/frontend/angelus/src/app/api.service.ts)
- [`frontend/angelus/src/app/api.types.ts`](/run/media/luna/数据和游戏/Codes/Python/angelus/frontend/angelus/src/app/api.types.ts)

### 7.1 列表主数据

`state.derivedAgents()` 是页面的实际数据源。

它的规则是：

1. 如果 `agentsLoaded()` 为真，直接返回 `agents()`
2. 否则从当前选中的 swarm 推导 Agents

推导逻辑会用到：

- `selectedSwarm()?.agent_files`
- `resolvedGraph()`
- `activeRun()`
- `responseFeed()`

因此在没有真实 Agents 列表时，页面仍能从 swarm 元信息、graph 和运行记录中拼出一个“近似的 Agents 视图”。

### 7.2 真实接口拉取

`state.loadAgents()` 会调用：

- `apiService.listAgents(baseUrl, swarmName, { q: '' })`

对应接口路径是：

- `GET /swarms/{swarmName}/agents`

返回后会映射成 `AgentRow[]`，再写入 `this.agents`。

### 7.3 Agent 行数据映射

`state.mapAgentCatalogItem()` 会把后端 `AgentCatalogItem` 映射成页面的 `AgentRow`。

映射字段：

- `id` -> `id`
- `name` -> `name`
- `status` -> `status`
- `type` -> `type`
- `capabilities` -> `capabilities`
- `tags` -> `tags`
- `tasks_executed` -> `tasksExecuted`
- `success_rate` -> `successRate`
- `avg_response_time_ms` -> `avgResponseTime`，格式化为 `xxxms`
- `token_usage_total` -> `tokenUsage`
- `last_activity` -> `lastActivity`

## 8. 相关 API

### 8.1 列表 API

`api.service.ts` 中已经实现：

- `listAgents(baseUrl, swarmName, query)`

实际请求为：

- `GET /swarms/{swarmName}/agents`

### 8.2 单 Agent 轮次 API

`api.service.ts` 中也已经实现：

- `runAgentRound(baseUrl, swarmName, agentId, request)`

实际请求为：

- `POST /swarms/{swarmName}/agents/{agentId}/round`

请求体结构：

- `message`
- `rounds?`
- `additional_prompt?`

响应结构包含：

- `success`
- `swarm`
- `agent_id`
- `result`
- `context`

## 9. 页面操作

当前页面上可触发的操作只有这些：

- 点击行选中 Agent，打开详情抽屉
- 点击右上角 `✕` 关闭抽屉
- 点击分页上一页 / 下一页
- 修改每页条数
- 点击“调试”按钮

其中“调试”按钮的实现是：

- `onAction(agent, 'run')`

这个按钮现在会：

- 选中对应的 Agent
- 调用 `runAgentRound()`

## 10. 当前缺失或未闭环的功能

这部分是目前 Agents 页面最重要的缺口。

### 10.1 “Agent市场 / 我的收藏 / 已禁用” 未实现

Tabs 已经有了，但没有对应的数据切换或内容区实现。

### 10.2 “调试”按钮已经接业务

按钮会触发后端的 `POST /api/swarms/{swarm}/agents/{agent}/round`。

### 10.3 详情抽屉中的实时信息是静态的

以下内容目前都是占位：

- sparkline 数据
- CPU / 内存 / 网络使用率

### 10.4 没有对单个 Agent 的更多操作

当前没有看到：

- 查看历史运行
- 调整配置
- 暂停 / 启用
- 收藏 / 取消收藏
- 禁用 / 解禁

### 10.5 没有服务端筛选和分页

所有筛选都在前端内存中做，列表规模大时会有局限。

### 10.6 选中状态不跟随筛选条件自动校正

当前代码没有看到在筛选后自动重置 `selectedAgent` 的逻辑。  
如果筛选后当前选中项不再可见，抽屉状态可能仍然保留旧对象。

### 10.7 页码没有在过滤变化时自动归一

`pageSize` 改变时会重置到第 1 页，但搜索/筛选变化时没有看到同步回第 1 页的处理。

## 11. 结论

现在这个 Agents 板块已经具备“可浏览、可筛选、可查看详情”的基础能力，真实数据也能从后端的 agents catalog 接入。

但从业务完整性上看，它还没有形成真正的 Agents 管理台，主要差距集中在：

- Tabs 未落地
- 详情抽屉中的实时指标是静态假数据
- 缺少收藏、禁用、更多管理动作

如果后续要继续补，我建议优先补两件事：

1. 把详情抽屉里的静态指标接到真实后端数据
2. 把 Tabs 变成真实的子视图或过滤维度
