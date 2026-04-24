# 前端知识板块实现说明

本文只记录当前前端知识板块的真实实现，基于以下三处代码：

- [`frontend/angelus/src/app/pages/knowledge.page.ts`](/run/media/luna/数据和游戏/Codes/Python/angelus/frontend/angelus/src/app/pages/knowledge.page.ts)
- [`frontend/angelus/src/app/services/state.service.ts`](/run/media/luna/数据和游戏/Codes/Python/angelus/frontend/angelus/src/app/services/state.service.ts)
- [`frontend/angelus/src/app/api.service.ts`](/run/media/luna/数据和游戏/Codes/Python/angelus/frontend/angelus/src/app/api.service.ts)

## 1. 当前页面做了什么

知识页是一个“知识库看板”，主要包含四块：

1. 顶部统计卡片
2. 筛选栏
3. 知识条目表格
4. 右侧详情抽屉

另外还有一个“Graph 知识图谱”展示区，用来显示当前选中 Swarm 的图快照，而不是独立的知识 CRUD 图谱。

### 1.1 数据来源

页面不直接请求接口，所有数据都来自 `StateService`：

- `state.derivedKnowledge()` 提供表格数据
- `state.knowledgeStats()` 提供统计卡片
- `state.resolvedGraph()` 提供图快照
- `state.selectedSwarmName()` 用于图谱提示文案

当 `knowledgeLoaded === true` 时，页面使用后端返回的知识列表。
如果知识列表尚未加载，`derivedKnowledge()` 会退回到 `resolvedGraph().nodes` 里的 `metadata`，把图节点元数据临时映射成知识条目。

当前页面还支持真正的知识 CRUD：

- 顶部 `+ 新建条目`
- 每行的编辑按钮
- 每行的删除按钮
- 保存后自动刷新列表

## 2. 列表能力

### 2.1 已实现

知识页的列表来自 `filteredEntries()`，支持以下列：

- 标题
- 类型
- 来源
- 标签
- 状态
- 引用次数
- 创建时间
- 操作

列表项点击后会打开右侧抽屉，查看条目详情。

### 2.2 列表数据结构

`KnowledgeEntry` 目前包含：

- `id`
- `title`
- `type`
- `source`
- `tags`
- `status`
- `citations`
- `createdAt`
- `content`
- `meta`
- `related`

其中 `meta` 里显示：

- 作者
- 版本
- 更新时间
- 大小

### 2.3 详情展示

右侧抽屉显示的内容包括：

- 内容预览：直接展示 `selectedEntry.content`
- 元信息：作者、版本、更新时间、大小、状态、引用次数
- 相关条目：通过 `related` 字段在当前知识集合里反查

注意：这里的“详情”仍然是前端本地选中项详情，不会再次发起 `GET /knowledge/{id}` 请求。

## 3. 创建、更新、删除

### 3.1 当前页面状态

这三个动作现在都已经接通：

#### 创建

- 页面顶部的 `+ 新建条目` 会打开编辑弹窗
- 可以填写标题、类型、来源、标签、状态和内容
- 保存后会调用 `state.createKnowledgeEntry()`

#### 更新

- 每行右侧的“编辑”按钮会打开同一个编辑弹窗
- 弹窗会回填当前条目的字段
- 保存后会调用 `state.updateKnowledgeEntry()`

#### 删除

- 每行右侧新增了删除按钮
- 删除前会弹出确认提示
- 删除后会调用 `state.deleteKnowledgeEntry()`

### 3.2 API 层

`ApiService` 已经提供了知识库 CRUD 方法：

- `getKnowledge(baseUrl, knowledgeId)`
- `createKnowledge(baseUrl, body)`
- `updateKnowledge(baseUrl, knowledgeId, body)`
- `deleteKnowledge(baseUrl, knowledgeId)`

`StateService` 已经封装了知识条目的创建、更新、删除，并在成功后刷新知识列表。

## 4. 筛选能力

### 4.1 已实现筛选

页面提供四个筛选控件：

- 关键词搜索：搜索标题、标签
- 类型筛选：`document` / `vector` / `rule` / `snippet`
- 来源筛选：官方文档、运行时采集、手动录入、社区贡献、模板库
- 标签筛选：`swarm` / `agent` / `api` / `graph` / `prompt`

对应逻辑在 `filteredEntries()` 中：

- 先基于 `derivedKnowledge()` 拿到当前列表
- 再按搜索词、类型、来源、标签逐层过滤

### 4.2 时间范围筛选

界面上有“时间范围”筛选：

- 今天
- 本周
- 本月

`filteredEntries()` 现在会按 `updatedAt` 或 `createdAt` 过滤最近 1 天、7 天或 30 天的数据，所以这组筛选已经生效。

## 5. 统计卡片

知识页顶部的统计卡片来自 `StateService.knowledgeStats()`，包括：

- 总条目
- 文档数
- 向量条目
- 引用次数
- 最近更新

### 5.1 统计计算方式

当前统计全部基于 `derivedKnowledge()` 计算：

- `total`：条目总数
- `documents`：`type === 'document'`
- `vectors`：`type === 'vector'`
- `citations`：引用次数求和
- `recentUpdates`：用 `updatedAt` 或 `createdAt` 判断是否在最近 30 天内

### 5.2 统计上的现实含义

如果知识数据来自图节点元数据的 fallback，那么：

- `documents` 和 `vectors` 通常可能为 0
- `citations` 也通常为 0
- `recentUpdates` 取决于元数据时间是否可解析

这意味着统计卡片在 fallback 模式下更多是“图快照摘要”，不是完整知识库统计。

## 6. Graph 知识图谱区

这一块不是独立知识库接口，而是展示当前 Swarm 的图快照：

- 有图时显示节点数、边数、密度、当前 Swarm 名称
- 没图时提示“尚未加载图数据，请在概览页选择 Swarm 以获取 Graph 快照”

密度计算方式：

- `edge_count / (node_count * (node_count - 1))`
- 节点数小于 2 时返回 `0.00`

## 7. 后端加载链路

知识页的数据加载实际发生在全局初始化阶段：

1. `StateService.loadOverview()`
2. 并发请求基础信息和 `listSwarms()`
3. 然后继续并发加载：
   - `loadEvents()`
   - `loadLogs()`
   - `loadMetrics()`
   - `loadKnowledge()`
   - `loadMemory()`
4. `loadKnowledge()` 调用 `ApiService.listKnowledge(baseUrl, { page: 1, limit: 500 })`
5. 返回结果映射为 `KnowledgeEntry[]`

也就是说，知识页的列表数据不是页面打开时单独加载，而是随全局总览初始化一起拉取。

## 8. 当前缺口

当前知识板块的主要缺口如下：

1. 详情抽屉仍然不走 `getKnowledge()` 的单条回源
2. 详情和列表仍然是同一个前端选中态，没有独立详情页
3. 后端知识实体的更新时间字段在前端只以映射字段展示，没有更复杂的历史视图
4. 现在的 CRUD 是表单式编辑，不是分步向导或富文本编辑器

## 9. 结论

当前前端知识板块的实现可以概括为：

- 已实现：列表、详情抽屉、基础统计、关键词/类型/来源/标签/时间筛选、创建、更新、删除
- 部分实现：图谱摘要展示
- 未实现：单条详情回源和更复杂的知识管理工作流

所以它现在更像一个“知识库浏览面板”，还不是完整的知识管理后台。
