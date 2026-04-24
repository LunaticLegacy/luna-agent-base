# 执行轨迹图、思维图谱与 Agent 图分离方案

## 1. 背景

当前系统中，“思考图 / 拓扑图”同时承载了三类语义：

- **Agent 拓扑语义**：哪些 agent 存在、如何路由、如何协作
- **认知语义**：事实、证据、主张、假设、问题、风险、决策之间的关系
- **执行语义**：工具调用、节点跳转、分支执行、失败回退、并行汇合等运行过程信息

这会导致几个问题：

- Agent 拓扑、执行过程、认知结构被混成一张图
- 思维图谱的语义被执行日志污染
- 工具被错误地建模成拓扑节点，导致“工具就是图节点”的耦合
- 前端图例与后端输出契约不够严格统一
- 工程上难以分别优化“路由 / 执行 / 推理”三层

因此需要将其拆分为三张不同的图：

- **Agent 图**
- **执行轨迹图**
- **思维图谱**

同时，后端的任务图谱需要补齐为完整能力，和这三张图形成四层清晰分工。

---

## 2. 目标

本方案的目标是：

1. 将 Agent 路由、执行过程与认知内容彻底分层
2. 让 Agent 图只表达 agent 结构与协作关系
3. 让执行轨迹图真实表达 fork / join / retry / fallback / failure 过程
4. 让思维图谱只表达可复用的认知结构
5. 让前端和后端对三张图拥有一致的语义契约
6. 补齐后端任务图谱，使其成为可持久化、可查询、可展示的正式图谱能力

---

## 3. 四层职责划分

### 3.1 Agent 图

Agent 图描述“有哪些 agent、如何连线、如何路由、谁可以调度谁”。

它只包含 agent 节点，不包含 tool 节点。

它应该记录：

- agent 节点
- agent 间的路由边
- join / checkpoint / dispatcher / reviewer 等协调角色
- 版本、状态、持久化标记

工具不应该出现在 Agent 图里。工具应当由 agent 在运行时按 capability 调用，并通过执行轨迹图记录其发生过程。

### 3.2 执行轨迹图

执行轨迹图描述“发生了什么”。

它应该记录：

- 节点执行开始与结束
- 工具调用与返回
- agent spawn / destroy
- 并行分支 fork
- 分支 join
- 失败、重试、回退、跳过
- 图变更与路由切换

它的核心是控制流和时序，不是认知内容。

### 3.3 思维图谱

思维图谱描述“想到了什么、依据是什么”。

它应该记录：

- fact
- evidence
- claim
- hypothesis
- question
- assumption
- risk
- decision
- counterevidence

它不应该直接承载执行轨迹中的工具调用细节。

### 3.4 任务图谱

任务图谱描述“要做什么、先做什么、后做什么”。

它应该是可持久化的 DAG，负责：

- task 节点
- 依赖关系
- 状态流转
- 优先级
- 任务完成判定

它既不是认知图，也不是执行图，但要能驱动执行层调度。

---

## 4. Agent 图语义

### 4.1 结构要求

Agent 图是纯 agent 拓扑图。

它必须满足：

- 节点只允许是 agent
- 边只表达 agent 间的静态路由 / 协作关系
- 不包含 tool 节点
- 不包含 tool 调用细节
- 不包含 raw execution event

### 4.2 节点定义

建议 agent 节点至少包含：

- `agent_id`
- `node_id`
- `node_name`
- `role`
- `status`
- `persistence`
- `lifetime_policy`
- `metadata`
- `entry_condition`
- `exit_condition`

### 4.3 边定义

建议 agent 图边至少包含：

- `route_to`
- `fan_out_to`
- `join_to`
- `fallback_to`
- `replan_to`
- `review_to`
- `handoff_to`

### 4.4 工具与 Agent 的正交关系

工具不再作为 Agent 图节点出现，而应通过下面两层处理：

- **工具注册层**：工具作为 capability 进入工具目录
- **运行执行层**：agent 在执行时按需要调用工具

这样能把“谁负责路由”和“谁负责执行工具”分开。

工具调用记录应进入执行轨迹图，而不是进入 Agent 图。

---

## 5. 执行轨迹图语义

### 5.1 结构要求

执行轨迹图**不能只是链式图**。

它必须支持：

- 分叉执行
- 并行执行
- 汇合执行
- 回退分支
- 重试链路
- 局部失败后的替代路径

因此它的底层结构应当是：

- **以 DAG 为主**
- **允许局部链式呈现**
- **支持 fork/join 元数据**

### 5.2 推荐节点类型

执行轨迹图的节点建议至少包含：

- `run_started`
- `node_started`
- `node_finished`
- `tool_called`
- `tool_returned`
- `agent_spawned`
- `agent_destroyed`
- `branch_forked`
- `branch_joined`
- `node_failed`
- `node_retried`
- `node_skipped`
- `graph_mutated`
- `run_finished`

### 5.3 推荐边类型

执行轨迹图的边建议至少包含：

- `next`
- `forks_into`
- `joins_from`
- `spawns`
- `retried_after`
- `failed_to`
- `replaced_by`
- `depends_on`

### 5.4 前端展示建议

前端应提供两种视图：

- **压缩视图**：主链优先，分支折叠
- **展开视图**：完整 DAG 展示 fork / join

---

## 6. 思维图谱语义

### 6.1 结构要求

思维图谱只表达认知结构，不表达执行动作。

### 6.2 推荐节点类型

建议的标准节点类型包括：

- `fact`
- `evidence`
- `claim`
- `hypothesis`
- `question`
- `assumption`
- `risk`
- `decision`
- `counterevidence`
- `tool_result`

### 6.3 推荐关系类型

建议的标准关系类型包括：

- `supports`
- `opposes`
- `derives_from`
- `leads_to`
- `depends_on`
- `questions`
- `refines`
- `verifies`
- `disproves`
- `speculates`

### 6.4 晋升规则

工具结果、执行产物、原始日志不应自动等同于思维图谱节点。

建议流程是：

1. 执行层产生原始结果
2. 原始结果进入执行轨迹或私有 workspace
3. agent 对结果做语义提炼
4. 只有提炼后的内容才进入思维图谱

---

## 7. 后端改造范围

### 7.1 Agent 图后端

后端需要将现有拓扑图改造成纯 agent 图：

- 执行图里的 agent 节点保留
- tool 节点从拓扑层移除
- tool 调用改为 runtime capability 调用
- agent 图需要支持版本、增删改、启停、持久化

建议后端提供的能力：

- agent 图快照 API
- agent 图 diff API
- agent 图变更事件 API
- agent 图编辑 API

### 7.2 执行轨迹后端

后端需要补齐执行轨迹图的数据采集与导出：

- 统一记录 append-only execution events
- 从事件流派生执行轨迹图
- 提供图快照 API
- 提供变更 diff API
- 提供 SSE / stream 事件 API

### 7.3 思维图谱后端

后端需要把思维图谱输出契约收敛到标准 schema：

- 输出认知节点和关系
- 过滤执行噪声
- 保留 `active_subgraphs`
- 保留可用于 LLM 的上下文摘要

### 7.4 任务图谱后端

后端任务图谱需要补齐为完整图谱能力，至少包括：

- 任务持久化
- 任务查询 API
- 任务更新 API
- 依赖校验
- 状态流转
- 图快照导出
- 图编辑或 patch 更新

任务图谱要成为明确的基础设施层，而不是临时数据结构。

---

## 8. 前端改造范围

### 8.1 界面拆分

前端应将原来的单一图谱入口拆成四个区域或标签：

- **Agent 图**
- **执行轨迹图**
- **思维图谱**
- **任务图谱**

任务页则继续保留独立任务视图，并逐步接入后端完整任务图谱。

### 8.2 前端图例

前端图例需要按三层重新组织：

- Agent 图图例
- 执行轨迹图图例
- 思维图谱图例
- 任务图谱图例

不要再共用一套模糊的“思考图”图例。

### 8.3 数据来源

前端需要分别调用：

- Agent 图 API
- 执行轨迹图 API
- 思维图谱 API
- 任务图谱 API

并分别维护状态缓存与版本号。

---

## 9. 任务图谱完成项

后端任务图谱需要完成以下能力：

### 8.1 核心实体

- `Task`
- `TaskGraph`

### 8.2 核心字段

- `task_id`
- `title`
- `description`
- `status`
- `priority`
- `dependencies`
- `next_tasks`
- `metadata`
- `created_at`
- `updated_at`

### 8.3 核心行为

- 创建任务
- 更新任务
- 删除任务
- 添加 / 删除依赖
- 判断 ready 状态
- 判断 blocked 状态
- 完成任务后自动解除依赖

### 8.4 可视化要求

任务图谱前端需要支持：

- 依赖 DAG 展示
- 状态高亮
- ready / blocked / completed 区分
- 点击任务查看详情

---

## 10. 推荐实施顺序

1. 先冻结语义定义，明确 Agent 图 / 执行轨迹图 / 思维图谱 / 任务图谱 的边界
2. 再拆分后端输出契约和存储模型
3. 再拆分前端页面与图例
4. 再把现有拓扑图迁移为纯 Agent 图
5. 再补齐后端任务图谱
6. 最后做执行轨迹图的 fork / join 可视化优化

---

## 11. 验收标准

满足以下条件时，方案可认为完成：

- Agent 图只包含 agent，不再混入 tool
- 执行轨迹图和思维图谱完全分离
- 前端页面和后端接口各自有独立语义
- 工具调用只出现在执行轨迹图和运行事件里
- 思维图谱不再混入执行日志
- 执行轨迹图可以表达分叉与汇合
- Agent 图可以表达静态拓扑、路由和协调
- 后端任务图谱具备完整持久化和查询能力
- 文档、图例、API 说明保持一致
