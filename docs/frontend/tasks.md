# 任务板当前实现说明

本文只总结当前前端任务板的实际实现情况，来源是：
- [`frontend/angelus/src/app/pages/tasks.page.ts`](/run/media/luna/数据和游戏/Codes/Python/angelus/frontend/angelus/src/app/pages/tasks.page.ts)
- [`frontend/angelus/src/app/services/state.service.ts`](/run/media/luna/数据和游戏/Codes/Python/angelus/frontend/angelus/src/app/services/state.service.ts)
- [`frontend/angelus/src/app/api.service.ts`](/run/media/luna/数据和游戏/Codes/Python/angelus/frontend/angelus/src/app/api.service.ts)

## 已实现的页面能力

任务页已经具备一个完整的只读任务看板骨架：
- 顶部标题区和“刷新任务”按钮。
- 5 个统计卡片：总任务数、运行中、成功率、平均执行时间、待处理。
- 任务筛选栏：搜索、状态、优先级、时间范围、排序。
- 任务表格：展示名称、状态、优先级、执行者、耗时、创建时间和操作。
- 右侧详情抽屉：点击任务行或“查看”按钮后打开，展示基础信息、输入参数、输出结果和活动日志。

页面上任务状态和优先级都有中文映射：
- 状态：`pending`、`running`、`success`、`failed`、`cancelled`
- 优先级：`low`、`medium`、`high`、`urgent`

## 数据加载方式

任务数据有两条来源路径：

1. 正常后端加载
- `StateService.loadTasks()` 会调用 `ApiService.listTasks()`。
- 当前请求路径是 `POST /api/swarms/<swarm_name>/tasks/search`。
- 路径里的 `<swarm_name>` 来自当前选中的 swarm。
- JSON body 固定包含：
  - `limit: 500`
  - `page: 1`
- 后端返回的 `TaskListResponse.items` 会被映射成前端 `TaskItem`。

2. 兜底派生数据
- 如果 `tasksLoaded` 还没有标记为 `true`，页面会使用 `derivedTasks()` 生成临时任务列表。
- 兜底来源包括：
  - 当前 `activeRun`
  - `responseFeed` 中 `POST` 且 endpoint 包含 `/runs/execute` 或 `/round` 的记录
- 这意味着在任务接口没有回来之前，页面仍然可能显示部分“推导出来”的任务。

## 任务字段映射

后端 `TaskCatalogItem` 会被映射为页面上的 `TaskItem`，主要字段如下：
- `id`
- `name`
- `status`
- `priority`
- `executor`
- `duration`：由 `duration_ms` 格式化而来
- `createdAt`
- `detail.description`
- `detail.input`
- `detail.output`
- `detail.logs`

其中日志会保留：
- 时间
- 级别
- 文本消息

## 当前统计口径

统计卡片和一些派生指标都来自前端计算，而不是直接照搬后端返回值：

- `总任务数`：`state.derivedTasks().length`
- `运行中`：`derivedTasks` 中 `status === 'running'` 的数量
- `成功率`：`taskStats.successRate`
- `平均执行时间`：当前返回值固定是 `-`
- `待处理`：`derivedTasks` 中 `status === 'pending'` 的数量

`taskStats` 的当前实现只计算了：
- `total`
- `running`
- `successRate`
- `avgDuration`，但这里仍是占位值 `-`
- `pending`

## 当前筛选与排序

页面已经接了这些交互：
- 关键词搜索：按任务名称或任务 ID 模糊匹配
- 状态筛选：按 `status` 精确过滤
- 优先级筛选：按 `priority` 精确过滤
- 排序：
  - 最新创建
  - 最早创建
  - 优先级高到低
  - 优先级低到高

但要注意，当前真正生效的只有：
- 搜索
- 状态
- 优先级
- 优先级排序

## 分页情况

当前任务页没有前端分页。

现状是：
- `loadTasks()` 一次请求最多拉取 500 条
- 页面直接把 `filteredTasks()` 全量渲染到表格里
- 没有页码切换、每页条数选择、总页数展示

## 详情抽屉支持内容

任务详情抽屉已经支持：
- 查看任务名称和 ID
- 查看状态、优先级、执行者、耗时、创建时间、描述
- 查看输入参数 JSON
- 查看输出结果 JSON
- 查看活动日志列表

如果任务没有输出结果，页面会显示“暂无输出”。

## 交互按钮现状

当前任务页上的按钮中，真正有行为的是：
- 点击任务行或“查看”按钮：打开详情抽屉
- 点击右上角关闭按钮或遮罩层：关闭详情抽屉

当前页面上没有创建或重试动作，表格只保留查看和刷新：
- 顶部按钮会重新加载任务列表
- 行内只保留查看详情

## 已知限制

当前实现的主要限制如下：
- `filterDateRange` 在 UI 中可选，但 `filteredTasks()` 里没有真正实现按时间过滤。
- `avgDuration` 统计没有真正计算，仍然显示占位值 `-`。
- 前端没有分页。
- 页面没有创建或重试任务的后端入口，因此这两个动作被移除，而不是保留成假按钮。
- `derivedTasks()` 在任务接口未加载时会用运行态和 feed 伪造一批任务，因此首屏数据可能不是纯后端任务清单。
- 当前任务页是偏“监控看板”而不是“完整任务管理后台”，更多是浏览和查看，而不是编辑和编排。

## 结论

就当前代码而言，任务板已经实现了“任务列表 + 搜索/过滤/排序 + 详情抽屉 + 基础统计”的浏览能力，但还没有完成“创建、重试、时间过滤、分页和真实平均耗时”这些管理能力。
