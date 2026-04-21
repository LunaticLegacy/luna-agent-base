# Metadata Reference

本文档汇总当前项目中所有会出现的 `metadata` 约定，供前端图谱解析、运行态展示和调试使用。

## 1. 图节点 metadata

来源：

- `core/policy.py`
- `agents/<swarm>/graph.py`

图节点的 `metadata` 是一个自由字典，但当前已有的语义字段主要有：

### `route_policy`

- 类型：`string`
- 典型值：
  - `"all"`
  - `"first"`
- 语义：
  - `"all"` 表示从当前节点分叉后，所有后继节点都应执行
  - `"first"` 或缺省表示按默认顺序执行第一个后继

### `join_node_id`

- 类型：`int`
- 语义：
  - 表示并行分支执行后的汇合节点
  - 当前 demo 中常用于从分叉源节点回到审查/汇总节点

### 其他自定义字段

节点 metadata 仍然允许继续扩展，前端应保留未知字段并原样展示。

### `runtime_transient`

- 类型：`bool`
- 语义：
  - 表示该节点是运行时临时节点
  - 允许 runtime 在临时 agent 已删除、但对应节点尚未移除时，把它视为可接受的过渡态

---

## 2. 运行状态 metadata

来源：

- `core/results.py`
- `core/executor.py`

运行状态里的 `metadata` 会随着执行过程变化。当前已知字段包括：

### `branch_index`

- 类型：`int`
- 语义：
  - 当前分支编号
  - 用于在并行执行时区分不同分支

### `branch_source_node_id`

- 类型：`int`
- 语义：
  - 分支来源节点 id
  - 表示该分支从哪个节点 fork 出来

### 其他运行时字段

- 工具可继续写入新的执行上下文信息
- 前端应把未知字段展示为原始 JSON

### `metadata_clear`

- 类型：`array[string]` 或 `string`
- 语义：
  - 指示执行器从 `state.metadata` 删除哪些旧控制键
  - 适合 cleanup 场景清理 `next_node_id`、`spawned_agent_*` 等残留值

---

## 3. Agent 上下文 metadata

来源：

- `core/agent.py`

每个 agent 维护独立上下文，metadata 当前已知字段：

### `last_round`

- 类型：`int`
- 语义：
  - 最近一次 round 调用的轮次编号

### `turns`

- 类型：`int`
- 语义：
  - 该 agent 当前上下文中的消息条数

### 其他 agent-local 字段

- 可继续扩展记忆摘要、内部状态、临时标记等
- 不同 agent 之间不共享

---

## 4. ToolContext metadata

来源：

- `core/toodefl.py`
- `core/executor.py`

工具接收到的 `metadata` 是当前执行状态的一个拷贝，工具可读取并在执行逻辑中据此决定行为。

### 语义

- 代表工具执行时的上下文
- 通常来自 `ExecutionState.metadata`
- 可用于图编辑、状态写入、调试记录

---

## 5. Skill metadata

来源：

- `core/skills.py`

skill asset 会把 contract 结构扁平化到 `metadata` 中。当前字段包括：

### `contract_version`

- 类型：`string`
- 语义：
  - skill contract 版本号

### `capability`

- 类型：`string`
- 语义：
  - 该 skill 的能力名称或职责标签

### `description`

- 类型：`string`
- 语义：
  - skill 的文字说明

### `input_schema`

- 类型：`object`
- 语义：
  - 该 skill 可接受的输入结构

### `output_schema`

- 类型：`object`
- 语义：
  - 该 skill 期望输出的结构

### `requires_tools`

- 类型：`array[string]`
- 语义：
  - 执行该 skill 时所需工具

### `requires_skills`

- 类型：`array[string]`
- 语义：
  - 执行该 skill 时所依赖的其他 skill

### `preconditions`

- 类型：`array[string]`
- 语义：
  - 该 skill 的前置条件

### `postconditions`

- 类型：`array[string]`
- 语义：
  - 该 skill 的后置条件

### `failure_policy`

- 类型：`string`
- 典型值：
  - `"retry"`
  - 其他自定义策略
- 语义：
  - skill 失败时的处理策略

### `parallelizable`

- 类型：`bool`
- 语义：
  - 该 skill 是否允许并行执行

---

## 6. 前端解析建议

前端在解析图谱时应遵守以下原则：

- 保留所有原始 metadata
- 不要丢弃未知字段
- `route_policy` 和 `join_node_id` 应作为图语义增强项
- `branch_index` 和 `branch_source_node_id` 应作为运行态分组信息
- skill metadata 应显示在节点详情或能力详情面板
- 结构连接以 `edges` 为准，语义提示以 `metadata` 为准

---

## 7. 推荐展示方式

### 节点卡片

- 基础信息：`node_id`、`node_name`、`node_type`
- 语义标签：`entry`、`exit`、`branch_source`、`join_target`
- 元信息：`metadata` 折叠显示

### 运行态面板

- 当前 `run_id`
- 当前 `current_node_id`
- `branch_index`
- `branch_source_node_id`
- `rounds`
- 实时事件流

### Skill 面板

- `capability`
- `description`
- `input_schema`
- `output_schema`
- `requires_tools`
- `requires_skills`
- `failure_policy`
- `parallelizable`
