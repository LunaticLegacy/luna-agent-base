# 动态图编辑协议说明

本文档总结当前动态节点编辑机制的执行方式、已知问题，以及后续需要优先修复的点。

## 1. 协议目标

动态图编辑协议的目标，是让 swarm 在运行期间能够对 **Agent 图** 做动态编辑，并将执行过程单独记录到 **执行轨迹图**：

- 创建临时或持久 agent 节点
- 把新 agent 插入活图
- 在运行时修改后继关系
- 删除、禁用或归档 agent 节点
- 将所有变更写入 runtime_info

也就是说，文件里的 `graph.py` 只是初始 Agent 图，真正的 Agent 图允许在运行中继续演化；工具不再作为图节点存在，而是在运行时由 Agent 调用。

## 2. 当前执行机制

### 2.1 Planner 产出控制计划

`planner` 节点会输出一段结构化控制内容，通常包含：

- `content`
- `spawn`
- `graph_edit`
- `cleanup`

其中：

- `content` 负责保留真正要发布的研究内容
- `spawn` 负责创建临时 agent
- `graph_edit` 负责修改运行时图结构
- `cleanup` 负责删除临时 agent 和临时节点

### 2.2 AgentNode 解析结构化输出

`GraphExecutor` 会尝试把 agent 的 `assistant_message` 解析成 JSON。

如果解析成功：

- `metadata_patch` 会合并进 `state.metadata`
- `metadata_clear` 会从 `state.metadata` 删除指定键
- 非空 `content` 会作为后续 payload
- reviewer 这类纯控制输出如果返回空 `content`，不会清空已有正文
- `next_node_id` 可能会被提取成下一跳

为了避免发布链路丢正文，执行器会把报告正文保存在专用 metadata 字段里：

- `draft_report`
- `approved_report`
- `final_report`
- `latest_report`

`next_node_id`、`next_node_ids`、`branch` 和 `branches` 仍然只负责调度，不再隐式代表正文内容。

### 2.3 ToolNode 接收 ToolContext

工具节点会得到：

- `core`
- `graph`
- `rounds`
- `metadata`

因此工具可以：

- 读 runtime 状态
- 改运行时图
- 改 agent registry
- 写 runtime_info

### 2.4 下一跳解析优先级

当前执行器的下一跳解析优先级是：

1. `next_node_override`
2. `payload.next_node_ids`
3. `payload.branch`
4. `payload.branches`
5. `graph.outgoing_edges(node.node_id)`
6. `node.next_node_ids`

这意味着：只要工具或 agent 返回了 `next_node_id`，执行器就会优先按它跳转。

### 2.5 runtime_info 记录

`Core.record_runtime_change(...)` 会把 mutation 写入：

- `agents/<swarm>/runtime_info/current.json`
- `agents/<swarm>/runtime_info/events.jsonl`

这保证了图变更、agent 变更和工具注册变更都可以被追踪。

## 3. 当前已知问题

### 3.1 `next_node_id` 语义污染

这是当前最核心的问题。

- `agent_manager` 和 `graph_editor` 的返回里都曾携带 `next_node_id`
- 执行器会优先相信这个值
- 结果就是工具抢占了调度权

对于动态图编辑来说，这很危险，因为可能跳到：

- 还没插入的节点
- 已经删除的节点
- 不应该立刻执行的节点

### 3.2 控制面和数据面混在一起

`content` 是内容流，`spawn` / `graph_edit` / `cleanup` 是控制流。  
但它们现在都在同一轮 state 中传播，后续工具容易拿到前一步残留的控制信息。

发布链路已经先做了最小隔离：writer/reviewer/publisher 会通过 `draft_report`、`approved_report`、`final_report` 和 `latest_report` 保留正文，避免 reviewer 的空控制 payload 覆盖正文。动态图编辑相关的控制信息仍需要继续收敛协议边界。

### 3.3 删除动作没有清理旧控制信息

删除临时节点后，旧的 `next_node_id` 仍可能保留在 metadata 中。  
这会让 executor 跳回一个已删除的节点。

### 3.4 改图不是原子操作

当前的“插节点 / 改边 / 跳转 / 记录 runtime_info”是分步执行的，不是一个事务。  
如果中间有一步和下一跳不同步，就会出现失配。

### 3.5 节点 ID 由上游协议分配，容易冲突

临时节点编号依赖 planner 或工具传入。  
如果 planner、tool、graph_editor 对 node_id 的理解不一致，就会出现：

- 跳到不存在的节点
- 覆盖旧节点
- 删除错节点
- 孤儿边

### 3.6 `replace_existing` 语义过强

直接删掉旧节点再插入新节点，如果没有自动重接上下游，图很容易断裂。

### 3.7 mutation 后缺少强制一致性校验

图在静态上合法，不代表 mutation 后仍然安全。  
目前缺少每次 mutation 后的局部一致性检查，例如：

- 节点是否仍可达
- 边是否仍有效
- next hop 是否仍存在

### 3.8 临时节点缺少显式生命周期标记

动态插入的临时节点需要一个明确的运行态标记，例如 `runtime_transient`，这样在临时 agent 已删除、但对应节点尚未移除时，运行时还能区分“可接受的过渡态”和真正的图损坏。

### 3.9 新增节点应支持临时与持久两种生命周期

当前协议只强调临时节点，但动态 swarm 还需要允许长期吸收能力。

建议把新增节点的生命周期拆成两类：

- `transient`：用完即弃，默认应当是这种
- `persistent`：长期保留，直到被显式删除、禁用、替换或回滚

对应的结构化元数据建议至少包含：

- `runtime_transient`
- `persistence`
- `lifetime_policy`

其中：

- `runtime_transient = true` 等价于临时节点
- `persistence = "persistent"` 表示长期保留
- `lifetime_policy` 用来补充生命周期边界，例如 `run`、`session`、`swarm`、`manual`

### 3.10 agent 生命周期和 node 生命周期没有强绑定

会出现：

- agent 已创建，但 node 还没插入
- node 已删除，但 agent 还没删
- 图里还有 node，agent 已被删除

### 3.11 branch / join 语义在动态改图后容易失效

如果运行时删掉了 branch target 或 join target，分支语义就会坏掉。  
执行器还会尝试按照旧路径继续执行。

### 3.12 runtime_info 只负责审计，不负责调度安全

它能告诉你“发生了什么”，但不能保证“下一步一定安全”。  
因此它不是调度保障，只是可追溯记录。

## 4. 修复优先级

建议优先修复以下内容：

1. 让创建 / 删除工具完全不返回 `next_node_id`
2. 让只有“插入节点”的工具能决定跳转
3. 每次 mutation 后做局部图校验
4. 清理旧的 `next_node_id` / `spawned_agent_*` / `deleted_agent_*` metadata
5. 为动态节点引入更清晰的 ID 管理策略
6. 把 runtime_info 从“审计”增强为“执行后置检查辅助”

## 5. 协议总结

当前动态图编辑协议的本质是：

- agent 负责产出结构化控制计划
- tool 负责修改运行时 agent / graph
- executor 负责按返回的 next hop 继续调度
- runtime_info 负责记录每次 mutation

它已经具备动态改图的雏形，但还没有达到“安全改图并继续执行”的程度。  
下一步的关键，是把控制流、数据流和图 mutation 的责任边界重新切清楚。
