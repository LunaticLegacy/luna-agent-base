# Swarm Management 前端实现说明

本文基于以下前端实现整理：

- `frontend/angelus/src/app/pages/swarm-management.page.ts`
- `frontend/angelus/src/app/services/state.service.ts`
- `frontend/angelus/src/app/api.service.ts`

## 页面定位

`swarm-management.page.ts` 现在更像一个“Swarm 运行态控制台”，而不是完整的管理后台。
页面本身几乎不存业务状态，只负责展示由 `StateService` 暴露出来的数据和动作。

页面目前已经覆盖的核心内容：

- 选择某个 swarm
- 刷新当前 swarm 的图和详情
- 启动 swarm 运行
- 查看运行中的任务与实时活动
- 查看 agents / tasks / events / knowledge / memory 的派生数据

## 已实现功能

### 1. Swarm 选择

当前页面通过 `StateService.selectSwarm()` 触发 swarm 切换。

实现方式是：

- 首次进入时，`init()` 会调用 `loadOverview()`
- `loadOverview()` 拉取 swarm 列表后，如果当前没有选中项，会默认选中第一个 swarm
- 选中 swarm 后会进入 `reloadSelectedSwarm()`，重新加载详情、图、agents、tasks、tools、统计信息

这说明“选择 swarm”已经是实打实的功能，不是纯前端假数据。

### 2. 图和详情刷新

页面里有两个层面的刷新：

- `refreshAll()`：重新拉取整个概览
- `refreshGraph()`：只刷新当前 swarm 的 graph

对应实现如下：

- `loadOverview()`：拉 `index / health / ready / swarms`
- `reloadSelectedSwarm()`：拉单个 swarm 的详情
- `loadSelectedGraph()`：优先使用列表里缓存的 graph，缓存没有时再请求后端 `GET /swarms/{name}/graph`

这个逻辑的特点是：

- 详情刷新会级联刷新 graph、agents、tasks、tools、stats
- graph 刷新有缓存回退
- 如果后端拉图失败，但列表里已经有 graph，仍然会回到缓存图

### 3. Load / Reload / Unload 相关能力

`ApiService` 里已经存在下面这些接口：

- `loadSwarm()`
- `reloadSwarm()`
- `unloadSwarm()`

这三类操作现在都已经接到页面上：

- `重新加载` 按钮会调用 `reloadCurrentSwarm()`
- `加载 Swarm` 会先弹出一个输入框，再调用 `loadSwarmFromSource()`
- `删除 Swarm` 会先二次确认，再调用 `unloadCurrentSwarm()`

`loadSwarmFromSource()` 会在成功后把新加载的 swarm 设为当前选中项，并重新拉取概览。
`reloadCurrentSwarm()` 会调用后端 reload 接口，然后重新拉取当前 swarm 的详情、graph、agents、tasks 和统计。
`unloadCurrentSwarm()` 会调用后端卸载接口，然后回到概览刷新 swarm 列表。

这部分现在是“后端接口能力已封装，前端管理面板已接线”。

### 4. 运行启动控制

当前页面已经接了两种运行启动方式：

- `startSwarmStructure()`：同步启动
- `startSwarmBackground()`：后台启动

页面中可见的触发点包括：

- 右上角“重新启动结构”
- 运行表格里的“启动结构”

启动逻辑使用的是 `ApiService.startSwarm()` 和 `ApiService.startSwarmBackground()`，并带有兼容回退：

- `startSwarm()` 优先请求 `/swarms/{name}/start`
- 如果返回 405，会回退到 `/swarms/{name}/run`
- `startSwarmBackground()` 优先请求 `/swarms/{name}/start/background`
- 如果返回 405，会回退到 `/swarms/{name}/runs`

这部分说明前端已经在兼容后端不同版本的路径设计。

### 5. Agent 轮次调试

`StateService.runAgentRound()` 已经实现，可以对指定 swarm 中的某个 agent 发起 round 调试：

- 路径：`POST /swarms/{swarm}/agents/{agent}/round`
- 参数：`message`、`rounds`、`additional_prompt`

页面上虽然没有做成一个很完整的独立控制台，但状态服务已经具备这条能力。

### 6. SSE / 实时运行跟踪

这块是当前前端里最明确的实时链路。

`startSwarmBackground()` 成功后会：

- 把返回的 `run` 写入 `activeRun`
- 调用 `watchRun(run)`

`watchRun()` 的行为是：

- 关闭旧的 SSE 连接
- 从 `run.events_url` 构造 `EventSource`
- 监听 `run.snapshot`
- 监听普通 `message`
- 根据事件更新：
  - `activeRun`
  - `liveEvents`
  - `streamState`
  - `streamNote`

此外，组件销毁时会自动关闭 SSE：

- `init(destroyRef)` 里注册了 `destroyRef.onDestroy(() => this.closeStream())`

所以“后台运行 + 实时状态追踪”是当前已经实现的。

## 页面上的数据板块

### 概览页

概览页展示了：

- swarm 名称和状态
- agents 数量
- 当前任务状态
- 成功率、吞吐量、Token 使用
- 拓扑图
- 节点图例
- swarm 信息
- 资源使用趋势
- 任务状态分布
- 正在运行的任务
- 实时活动

这些数据大部分来自 `StateService` 的派生计算值，而不是手写死数据。

### 拓扑视图

`拓扑视图` 和 `概览` 页共享同一个 graph 渲染：

- 通过 `resolvedGraph()` 获取 graph
- 通过 `app-graph-viewer` 展示

### Agents / 任务 / 活动 / 知识 / 记忆 / 设置

这些 tab 都已经在 UI 里存在，并且和 `StateService` 的派生数据联动。

其中很多内容并不是独立拉页面接口，而是走“真实数据优先，缺失时用派生数据补齐”的策略：

- `derivedAgents()`
- `derivedTasks()`
- `derivedTools()`
- `derivedEvents()`
- `derivedKnowledge()`
- `derivedMemories()`

换句话说，这些 tab 不是空壳，但也不等于每个 tab 都有完整 CRUD。

## 当前实现的降级策略

这套前端有明显的“可用优先”策略：

- 如果后端返回了 swarm / graph / stats / lists，就直接用真实数据
- 如果某些列表没返回，就从 `responseFeed`、`activeRun`、`selectedSwarm`、`resolvedGraph` 派生出可展示数据

具体例子：

- `derivedAgents()` 可以从 `selectedSwarm.agent_files` 和 graph 推导 agent 表
- `derivedTasks()` 可以从 `activeRun` 和响应流推导任务表
- `derivedEvents()` 可以把 SSE 和 response feed 变成活动记录
- `derivedKnowledge()` 可以从 graph metadata 推知识条目
- `derivedMemories()` 可以从 run state 和最近的 feed 推记忆

这意味着：

- 视图层在后端部分缺失时仍能“看起来有内容”
- 但这些内容有一部分是推导出来的，不代表后端真的提供了完整实体列表

## 目前仍然偏占位的部分

下面这些点仍然是页面里比较明显的“展示型”内容：

### 1. 最后更新时间

标题区域里显示的是：

- `最后更新: —`

这里仍然没有绑定真实时间戳。

### 2. 基本信息字段

在 swarm 信息区里，以下字段仍然没有真实数据接入：

- 创建时间：`—`
- 描述：`—`
- 标签：默认显示 `默认`

这意味着详情区域还在用静态展示兜底。

### 3. 重新启动结构

右上角的 `重新启动结构` 按钮会尝试调用 `startSwarmStructure()`。
如果当前没有 active run，这个按钮会在 UI 上被禁用。

虽然 `ApiService` 已经有：

- `loadSwarm()`
- `reloadSwarm()`
- `unloadSwarm()`

但 `StateService` 没有把这些动作暴露成当前页面的按钮操作。

如果从“Swarm 管理板”的角度看，这一块现在是 API 有、UI 未接。

### 6. 同步启动与后台启动的 UI 命名有点混用

页面里显示的是“重新启动结构”“启动结构”，但底层实际又分成：

- 同步启动
- 后台启动

这部分目前保留了现有命名，因为它直接对应运行控制语义，没有再改成更抽象的标签。

而当前模板主要直接调用 `startSwarmStructure()`，后台启动按钮并没有完整铺到 UI 上。

## 结论

现在的 Swarm management 前端已经具备以下能力：

- 选择 swarm
- 重新拉取当前 swarm 详情和 graph
- 查看 agents / tasks / events / knowledge / memory
- 启动 swarm 运行
- 通过 SSE 跟踪后台运行

但它还不是一个完整的“生命周期管理面板”。

最关键的缺口是：

- 标题区的最后更新时间仍是静态占位
- swarm 信息区里的创建时间、描述和标签仍没有真实后端数据接入
- 还有一些展示型指标属于静态或派生值，而不是完整的生命周期元数据

如果后续要继续完善，这个页面更像是从“运行态控制台”补成“完整 swarm 管理台”。
