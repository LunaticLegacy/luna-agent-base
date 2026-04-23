# 前端记忆板实现说明

本文只记录当前前端 `memory` 页面在代码里的真实实现，不描述尚未接通的设想。

## 涉及代码

- 页面组件：[`frontend/angelus/src/app/pages/memory.page.ts`](/run/media/luna/数据和游戏/Codes/Python/angelus/frontend/angelus/src/app/pages/memory.page.ts)
- 状态来源：[`frontend/angelus/src/app/services/state.service.ts`](/run/media/luna/数据和游戏/Codes/Python/angelus/frontend/angelus/src/app/services/state.service.ts)
- API 封装：[`frontend/angelus/src/app/api.service.ts`](/run/media/luna/数据和游戏/Codes/Python/angelus/frontend/angelus/src/app/api.service.ts)

## 当前页面做了什么

记忆页标题是“记忆系统”，副标题写的是“Agent 记忆检索、管理与持久化”。从实际代码看，它现在更接近一个“记忆库浏览 + 新增/删除面板”：

1. 顶部统计卡片
2. 左侧记忆列表
3. 右侧记忆详情
4. 底部 System Memory 信息面板

页面已经提供了创建记忆的编辑弹窗和删除动作，但没有通用的编辑更新接口，因为后端当前只提供 `create` 和 `delete`。

## 数据来源

页面本身不直接请求接口，所有数据都来自 `StateService`。

### 列表数据

页面里的 `memories()` 实际指向 `state.derivedMemories()`，它有两种来源：

1. 如果 `state.memoriesLoaded()` 为 `true`，直接使用后端拉回来的记忆列表
2. 如果记忆列表还没加载成功，则回退为本地派生数据

这个 fallback 逻辑会从以下内容临时拼出“记忆视图”：

- 当前 `activeRun()` 的运行状态快照
- `responseFeed()` 里最近几条接口响应

所以在后端记忆库可用时，页面展示的是实际记忆数据；在不可用时，页面仍能显示一些由运行状态和响应流构造出来的临时项。

### 统计数据

顶部统计卡片来自 `state.memoryStats()`，包括：

- 总记忆数
- 活跃记忆
- 平均重要性
- 记忆类型分布
- 情感得分

这些统计都是基于 `derivedMemories()` 计算出来的，不是单独请求的后端聚合接口。

## 列表能力

### 已实现

左侧列表展示每条记忆的核心信息：

- `summary`
- `timestamp`
- `type`
- `importance`

列表是可点击的，点击后会把当前项设为 `selectedMemory()`，右侧详情区随之更新。

### 已实现的筛选

页面提供两类筛选控件：

- 关键词搜索
- 类型筛选

关键词搜索会同时匹配：

- `summary`
- `content`

类型筛选支持：

- `episodic`
- `semantic`
- `procedural`
- `working`

当前筛选逻辑在 `filteredMemories()` 中完成，先拷贝当前列表，再按搜索词和类型逐层过滤。

### 没有实现的列表能力

当前没有看到：

- 分页
- 排序
- 按来源筛选
- 按时间范围筛选
- 批量操作

也就是说，列表目前是一个本地过滤后的单页列表，不是完整的检索工作台。

## 详情查看

右侧详情面板由 `selectedMemory()` 驱动。

### 已实现

选中某条记忆后，右侧会展示：

- 标题：`summary`
- ID：`id`
- 正文：`content`
- 时间：`timestamp`
- 类型：`type`
- 来源：`source`
- 情感：`sentiment`
- 重要性：`importance`
- 关联数量：`relatedIds.length`

### 关联记忆

如果当前记忆的 `relatedIds` 能在现有列表中匹配到其他项，下面会显示“关联记忆”列表。

点击关联项会直接切换到那条记忆的详情。

### 详情模式的限制

详情面板是纯前端本地展示，不会因为点击某条记忆而再次发起 `GET /memory/{id}` 请求。

也就是说：

- 有列表数据就从列表里看详情
- 没有列表数据时不会自动回源单条详情接口

## 创建、编辑、删除

### 页面层现状

当前 `memory.page.ts` 里已经有这些功能入口：

- 新建记忆
- 删除记忆
- 保存/取消表单

但没有编辑记忆，因为后端没有对应的 `update` 接口。

页面上只有查看、筛选和点击切换详情。

### API 层现状

`ApiService` 里已经预留了记忆资源的接口封装：

- `listMemory(baseUrl, query)`
- `getMemory(baseUrl, memoryId)`
- `createMemory(baseUrl, body)`
- `deleteMemory(baseUrl, memoryId)`

`StateService` 现在已经把创建和删除串起来：

- `createMemoryEntry()` 会调用 `createMemory()` 并刷新记忆列表
- `deleteMemoryEntry()` 会调用 `deleteMemory()` 并刷新记忆列表

页面层在顶部新增了 `+ 新建记忆`，在详情区新增了删除按钮。

## System Memory 面板

页面底部的 `System Memory` 区块是一个状态信息面板，不是独立的记忆 CRUD 区。

它展示的是全局运行状态：

- API Base URL
- Health
- Ready
- Selected Swarm
- Active Run
- Live Events

这些字段来自 `StateService` 的全局信号，和当前记忆条目本身不是一回事。

## 后端加载链路

记忆列表的加载发生在全局初始化流程中：

1. `StateService.loadOverview()`
2. 并发加载基础状态和 `listSwarms()`
3. 随后并发执行：
   - `loadEvents()`
   - `loadLogs()`
   - `loadMetrics()`
   - `loadKnowledge()`
   - `loadMemory()`
4. `loadMemory()` 调用 `ApiService.listMemory(baseUrl, { page: 1, limit: 500 })`
5. 返回结果映射成 `MemoryItem[]`

这意味着记忆页的数据不是单独懒加载的，而是和 Overview 一起初始化。

## 记忆数据结构

当前页面使用的 `MemoryItem` 包含：

- `id`
- `summary`
- `content`
- `timestamp`
- `type`
- `source`
- `sentiment`
- `importance`
- `relatedIds`

页面里的类型标签映射如下：

- `episodic` -> 情景
- `semantic` -> 语义
- `procedural` -> 程序
- `working` -> 工作

## 当前限制

1. 没有编辑记忆的更新接口
2. 没有单条记忆详情回源
3. 没有分页和排序
4. 没有时间范围筛选
5. 没有按来源、情感或重要性做高级过滤
6. `relatedIds` 只有后端返回的内容可靠时才有完整效果
7. fallback 记忆是由运行状态和响应流拼出来的，不等同于真实持久化记忆

## 现在可以做的事

- 浏览当前记忆列表
- 用关键词和类型筛选记忆
- 点击条目查看详情
- 点击关联记忆跳转到相关项
- 查看当前 Swarm、运行和事件的系统上下文

## 现在还不能做的事

- 不能编辑现有记忆
- 不能在页面里编辑记忆
- 不能在页面里删除记忆
- 不能对记忆做分页、排序和高级查询
- 不能把详情面板当作完整的单条编辑器使用
