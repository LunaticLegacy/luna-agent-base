# 事件板实现说明

本文只梳理当前前端 `events` 页面在代码里的真实实现，不描述尚未接通的设想。

## 页面位置

- 页面组件：`frontend/angelus/src/app/pages/events.page.ts`
- 状态来源：`frontend/angelus/src/app/services/state.service.ts`
- 数据接口：`frontend/angelus/src/app/api.service.ts`

## 当前页面结构

事件板当前分成两种展示模式：

1. 常规事件表格
   - 显示时间、级别、来源、事件、详情
   - 点击某一行可以展开 JSON 明细

2. 实时流面板
   - 只有在切到“实时流”页签时才显示
   - 用于查看 SSE 推送过来的实时事件

页面顶部还显示 5 个统计卡片：

- 今日事件
- 错误事件
- 警告事件
- 信息事件
- 实时流状态

## 数据来源

事件板的数据并不是页面内自己请求的，而是直接读 `StateService` 的派生状态。

### 常规事件列表

`StateService.loadEvents()` 会调用：

- `GET /api/events`

然后把返回的 `response.items` 映射成页面使用的 `EventItem`，存进 `state.events()`。

`loadEvents()` 会在 `loadOverview()` 里被一起触发，所以事件列表通常是随着全局初始化一起加载的，而不是进入事件页后单独再拉一次。

### 回退来源

如果 `eventsLoaded` 还没变成 `true`，`StateService.derivedEvents()` 会走回退逻辑，把下面两类数据合并起来：

- `responseFeed`
- `liveEvents`

这时页面展示的是前端临时拼出来的事件视图，不是后端 `/api/events` 的正式列表。

回退模式下，来源会根据 endpoint 粗略推断：

- 包含 `/agents/` 的记为 `Agent`
- 包含 `/swarms/` 的记为 `Swarm`
- 其他都记为 `System`

### 事件模型

当前页面最终使用的事件字段是：

- `id`
- `time`
- `level`
- `source`
- `event`
- `detail`
- `data`

## 统计卡片

顶部统计不是直接读后端 `EventListResponse.stats`，而是读 `state.eventStats()`。

`eventStats()` 基于 `derivedEvents()` 重新计算：

- `today` = 当前事件总数
- `errors` = `level === 'error'` 的数量
- `warnings` = `level === 'warn'` 的数量
- `infos` = `level === 'info'` 的数量

也就是说，后端返回的统计字段虽然存在，但当前前端没有直接使用它们。

## 筛选和交互

当前页面里能看到的筛选控件有：

- 页签：全部、错误、警告、信息、实时流
- 搜索框：搜索事件
- 来源下拉框：所有来源 / 系统 / Swarm / Agent
- 时间范围下拉框：最近 1 小时 / 今天 / 最近 7 天

其中真正生效的只有这两类：

- 页签切换
- 搜索框
- 来源下拉框
- 时间范围下拉框

### 真正生效的筛选

`filteredEvents()` 里的过滤逻辑是：

1. 先取 `state.derivedEvents()`
2. 如果不是“全部”，按 `level` 过滤
3. 如果填写了搜索词，再按 `event` 或 `detail` 做 `includes()` 匹配

这里的搜索是前端本地过滤，不会发请求，也没有大小写归一化。

### 目前已生效的控件

- 来源下拉框会按 `source` 过滤
- 时间范围下拉框会按事件时间过滤
- 顶部“导出”按钮会下载当前筛选结果的 JSON

另外，“清除筛选”按钮只会：

- 把页签重置回 `all`
- 清空 `searchText`
- 重置来源筛选
- 重置时间范围筛选
- 清空详情展开状态

## 实时更新

实时流不是事件表格的自动增量刷新，而是独立的 SSE 监听链路。

### 触发时机

`StateService.watchRun()` 会在后台运行启动后被调用，典型入口是：

- `startSwarmBackground()`
- 以及它内部继续调用的 `watchRun(response.run)`

它会根据 `run.events_url` 创建 `EventSource`，然后监听：

- `run.snapshot`
- `message`

### 实时流如何进入页面

收到 SSE 后，`pushLiveEvent()` 会把数据压入 `state.liveEvents()`。

这个数组有两个限制：

- 状态层最多保留 20 条
- 页面“实时流”页签展示 `liveEvents().slice(-50)`

因为状态层先截断了，所以当前实际能看到的实时事件数量上限还是 20 条。

### 常规事件表是否跟着刷新

不会。

一旦 `eventsLoaded === true`，`derivedEvents()` 就直接返回 `state.events()`，不再合并 `responseFeed` 和 `liveEvents`。

所以当前实现是这样的：

- 常规事件表：一次性加载后基本静态
- 实时流页签：只显示 SSE 新消息

这也是现在最重要的边界。

## 目前缺少的部分

当前事件板已经能看、能筛、能导出，也能看实时流，但还缺少这些能力：

- 事件列表的手动刷新按钮
- 服务端分页
- 服务端排序
- 事件详情独立页
- 事件的增删改或其它管理动作
- 把 SSE 实时事件自动回写到常规事件表

另外，页面中的实时流和常规事件表是两条并行路径，不是同一个列表的不同视图，这一点在交互上还比较容易让人误解。

## 结论

当前事件板已经具备一个可用的查看页：

- 能从 `/api/events` 拉到正式事件列表
- 能做本地级别和关键词筛选
- 能在后台运行时看到 SSE 实时事件

但从完整性上看，它还是偏“观察面板”，而不是完整的事件管理中心。
