# 前端日志板实现说明

本文只梳理当前前端 `logs` 页面在代码里的真实实现，不描述尚未接通的设想或未来规划。

## 页面位置

- 页面组件：`frontend/angelus/src/app/pages/logs.page.ts`
- 状态来源：`frontend/angelus/src/app/services/state.service.ts`
- 数据接口：`frontend/angelus/src/app/api.service.ts`

## 当前页面结构

日志板当前只有一个主要展示区，外加顶部统计与少量控制按钮。

### 顶部区域

- 标题：`系统日志`
- 副标题：`结构化日志查询与分析`
- 按钮：
  - `自动滚动 / 暂停滚动`
  - `导出`

### 统计卡片

页面顶部展示 5 个统计项：

- 总日志数
- ERROR
- WARN
- INFO
- DEBUG

这些统计值都来自 `StateService.logStats()`。

### 日志列表

主区域使用一个可滚动的日志容器，逐行展示：

- 时间
- 级别
- 服务名
- 日志内容

当前只支持列表式展示，没有详情抽屉、没有单条展开面板，也没有分组视图。

## 数据来源

日志页的数据不是页面自己请求的，而是直接读取 `StateService.derivedLogs()`。

### 真实后端来源

`StateService.loadLogs()` 会调用：

- `POST /api/catalog/logs/search`

分页条件放在 JSON body 里，例如 `{"page": 1, "limit": 200}`。

返回后，前端会把 `response.items` 映射为页面使用的 `LogItem`，再写入 `state.logs()`。

对应的后端响应结构是：

- `LogListResponse`
- `items: LogCatalogItem[]`

其中单条日志原始字段是：

- `id`
- `time`
- `level`
- `service`
- `message`

### 回退来源

如果 `logsLoaded` 还没有变成 `true`，`derivedLogs()` 不会返回后端日志，而是用 `responseFeed()` 临时拼一份日志视图。

回退视图的映射规则是：

- `id` = `log-${feed.id}`
- `time` = `feed.timestamp`
- `level`
  - `error` -> `ERROR`
  - `warn` -> `WARN`
  - `success` -> `INFO`
  - 其他 -> `DEBUG`
- `service`
  - endpoint 包含 `/agents/` -> `agent`
  - endpoint 包含 `/swarms/` -> `swarm`
  - 其他 -> `backend`
- `message` = `${method} ${endpoint} — ${title}`

也就是说，日志页在没有真正加载到 `/api/logs` 时，会先显示前端的响应流派生日志，而不是空白页。

## 查询和筛选

当前页面里可见的查询控件有：

- 级别筛选按钮：全部、ERROR、WARN、INFO、DEBUG
- 关键词搜索框
- 服务下拉框：所有服务 / backend / agent / graph

但从实际代码看，真正生效的只有前两项。
不过现在服务下拉框、导出和自动滚动也都已经接通，分别用于：

- 按服务名过滤日志
- 导出当前过滤后的日志 JSON
- 自动滚动到最新一条日志

### 真正生效的过滤

`filteredLogs()` 的逻辑是：

1. 先取 `state.derivedLogs()`
2. 如果级别不是 `all`，按 `log.level === levelFilter()` 过滤
3. 如果输入了搜索词，再按 `log.message.toLowerCase().includes(searchText.toLowerCase())` 过滤

这说明当前搜索是纯前端本地过滤，不会发起新的 API 请求。

### 目前已生效的控件

- 服务下拉框
- `导出` 按钮
- `自动滚动 / 暂停滚动` 按钮

## 刷新节奏

日志板没有自己的轮询定时器。

### 首次加载

`StateService.init()` 会先调用 `loadOverview()`，而 `loadOverview()` 内部会并行加载：

- `loadEvents()`
- `loadLogs()`
- `loadMetrics()`
- `loadKnowledge()`
- `loadMemory()`

所以日志数据通常是在应用初始化时一起拉取的，而不是用户进入日志页后再单独请求一次。

### 手动刷新

当前没有日志页专属的刷新按钮。

页面里如果触发全局刷新，本质上也是走：

- `StateService.refreshAll()`
- 最终回到 `loadOverview()`

因此日志数据的更新频率是“随全局刷新而刷新”，不是按固定秒数自动轮询。

### 服务状态

`logsLoaded` 只会在 `loadLogs()` 成功后被置为 `true`。

一旦成功加载过日志，`derivedLogs()` 就优先返回 `state.logs()`，不再使用 `responseFeed()` 做回退。

## 现有实现特点

### 统计口径是前端现算

`logStats()` 不是直接读取后端 `LogListResponse.stats`，而是基于 `derivedLogs()` 重新计算出来的。

也就是说，顶部统计卡片展示的是“当前前端看到的日志集合”的统计，不一定等于后端原始统计结果。

### 级别大小写在前端统一

后端返回的日志级别是大写：

- `INFO`
- `WARN`
- `ERROR`
- `DEBUG`

日志页的样式类和筛选逻辑也都按这个大写字段工作。

### 界面是只读的

当前日志板没有日志详情编辑、没有删除、没有批量操作，也没有服务端搜索参数透传。

## 当前限制

当前实现的主要限制有：

- 只有一次性拉取，没有分页翻页 UI
- 没有按时间范围过滤
- 没有服务端搜索
- 没有单条日志详情面板
- 没有实时追加日志的独立 SSE 订阅

## 结论

现在这个日志板更像是一个“结构化日志浏览器”而不是完整日志运维面板：

- 真实数据来自 `/api/logs`
- 页面加载时会跟随全局 `loadOverview()` 一起刷新
- 级别筛选、关键词搜索、服务筛选、导出和自动滚动都是可用的
