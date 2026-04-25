# Angelus 架构优化稿

本文档基于 `STRUCTURE.md` 的原始想法整理而来，目标不是改变项目方向，而是把四个核心抽象的职责、边界和读写关系写清楚，方便后续落到代码结构中。

## 1. 顶层定位

Angelus 的目标不是做一个简单的 agent 调度器，而是做一个可动态演化的 agent swarm runtime。

它的核心思想是：不要把执行流、上下文、推理线索和任务分解全部塞进 prompt 或 message history，而是拆成四套相互协作但边界明确的结构：

- `dynamic execution graph`：控制 agent swarm 的执行流。
- `context tree`：控制每个 agent 当前可见、可激活的上下文。
- `thinking graph`：沉淀 swarm 内部共享的线索、证据、推理和结论关系。
- `quest tree`：将大型任务分解为层次化、可追踪、可调度的子任务结构。

这四套结构共同构成 Angelus 的运行时控制面。

## 2. 四图职责

### 2.1 dynamic execution graph

职责：操纵整个 agent swarm 的执行流。

它回答的问题是：

- 当前应该执行哪个 agent 或 tool？
- 多个 agent 之间是流水线、上下级、分支还是汇聚关系？
- 运行期间是否需要创建、删除、替换 agent 节点？
- 当前任务模式是否需要改变执行拓扑？

特点：

- 本质是有向图。
- 可以是 DAG，也可以包含受控环路。
- 节点可以是 agent、tool、join、router、checkpoint 等执行单元。
- 边表示执行转移、分支条件、优先级或汇聚关系。
- 它是唯一直接决定 runtime 下一步执行位置的图。

边界：

- execution graph 只负责执行拓扑，不直接存储长期记忆。
- execution graph 不应该自己理解复杂任务语义。
- 任务语义应由 `quest tree` 表达，再由 `GraphPolicy` 或 `SwarmPlanner` 转换为图变更。

建议实现：

- `ExecutionGraph`：纯图模型，负责节点、边、校验和序列化。
- `GraphExecutor`：执行器，负责解释 execution graph。
- `GraphTransaction`：图变更事务，负责 prepare、validate、commit、rollback。
- `GraphPolicy`：读取 quest tree、agent capability、runtime state 后，决定是否需要改图。

### 2.2 context tree

职责：管理 agent 的上下文内容。

它回答的问题是：

- 某个 agent 当前能看见哪些上下文？
- 哪些上下文应该被激活并注入 prompt？
- agent 是否能读取其他 agent 的上下文？
- 上下文之间是否存在父子、引用、摘要或派生关系？

特点：

- 以树状结构组织上下文，但允许通过索引或引用形成跨树链接。
- 每个上下文节点需要有明确的作用域、所有者和激活策略。
- agent 可以选择激活或不激活特定上下文。
- context tree 不是简单的 message dump，而是可选择、可裁剪、可解释的上下文索引系统。

最小数据结构建议：

```text
ContextNode:
- id
- parent_id
- owner_agent_id
- scope: private | shared | swarm
- kind: message | memory | artifact | evidence | instruction | constraint | summary
- content
- content_ref
- tags
- activation_policy
- visibility_policy
- created_by
- created_at
- updated_at
```

关键点：

- `activation_policy` 决定一个上下文节点什么时候进入 agent prompt。
- `visibility_policy` 决定哪些 agent 可以读取该上下文节点。
- `content_ref` 用于引用大文件、artifact、外部知识库或 thinking graph 节点，避免 prompt 膨胀。

边界：

- context tree 可以被 execution graph 中的 agent/tool 查询。
- context tree 不直接改变 execution graph。
- context tree 可以引用 thinking graph 的节点，但不应该复制整张 thinking graph。

### 2.3 thinking graph

职责：辅助 agent swarm 组织线索、证据、推理步骤和结论关系。

它回答的问题是：

- 当前 swarm 已经知道了什么？
- 哪些证据支持某个结论？
- 哪些结论互相冲突？
- 某个推理步骤来自哪些来源？
- 哪些信息值得被 context tree 按需取用？

特点：

- thinking graph 中的每个节点和每条边都应有明确语义。
- 它是共享认知结构，不是执行控制结构。
- agent 可以向 thinking graph 写入观察、证据、假设、结论和反驳。
- agent 也可以查询 thinking graph，用于补充上下文或复核当前任务。

建议节点类型：

```text
ThoughtNode:
- id
- kind: observation | evidence | hypothesis | claim | conclusion | question | risk
- content
- confidence
- source
- tags
- created_by
- created_at
- metadata
```

建议边类型：

```text
ThoughtEdge:
- id
- from_node_id
- to_node_id
- relation: supports | contradicts | depends_on | derived_from | refines | relates_to | answers
- confidence
- metadata
```

边约束不应一刀切。更合理的做法是给每种 relation 定义自己的约束：

```text
RelationPolicy:
- relation
- directed: true | false
- acyclic: true | false
- transitive: true | false
- confidence_required: true | false
```

例如：

- `supports` 可以要求有向，通常应避免循环支持。
- `derived_from` 应该有向且无环。
- `contradicts` 可以是双向关系，不一定适合 DAG 约束。
- `relates_to` 可以允许无向或弱约束。

硬边界：

- thinking graph 不得直接 mutate execution graph。
- thinking graph 可以作为 `GraphPolicy`、`SwarmPlanner` 或 agent 决策的输入证据。
- 如果 thinking graph 发现当前执行路线有问题，应通过 policy 层提出建议，而不是直接改执行图。

### 2.4 quest tree

职责：层次化当前任务。

它回答的问题是：

- 用户的大任务可以拆成哪些子任务？
- 每个子任务的目标、状态、依赖和验收标准是什么？
- 哪些子任务可以并行？
- 哪些子任务需要额外 agent、tool 或上下文？
- 当前执行图是否覆盖了任务所需的职能边界？

特点：

- 将大型任务吸入后，对其进行层次化分析。
- 每个任务节点都有方向、状态和依赖。
- quest tree 是任务结构，不是执行结构。
- 它可以驱动 execution graph 的调整，但不直接执行 agent。

最小数据结构建议：

```text
QuestNode:
- id
- parent_id
- title
- description
- status: pending | running | blocked | completed | failed | cancelled
- priority
- required_capabilities
- assigned_agent_ids
- depends_on
- acceptance_criteria
- artifacts
- created_at
- updated_at
```

边界：

- quest tree 描述“要做什么”和“为什么这样拆”。
- execution graph 描述“谁来做、按什么顺序做”。
- context tree 描述“做的时候能看什么”。
- thinking graph 描述“做的过程中发现了什么、推理出了什么”。

## 3. 四图读写关系

推荐的默认数据流如下：

```text
user input
  -> quest tree
  -> GraphPolicy / SwarmPlanner
  -> dynamic execution graph
  -> GraphExecutor
  -> agent / tool
  -> context tree + thinking graph + quest tree status
```

更具体地说：

```text
quest tree -> 影响 execution graph
quest tree -> 查询或约束 context tree
execution graph -> 决定 agent/tool 调度
agent/tool -> 读取 context tree
agent/tool -> 写入 thinking graph
agent/tool -> 更新 quest tree 状态
thinking graph -> 提供证据给 context tree 或 GraphPolicy
context tree -> 为 agent 生成可激活上下文
```

禁止关系：

```text
thinking graph -/-> 直接修改 execution graph
context tree -/-> 直接修改 execution graph
execution graph -/-> 直接写长期知识
agent message history -/-> 充当全部记忆系统
```

如果需要从 thinking graph 或 context tree 影响执行流，应通过 `GraphPolicy` 或 `SwarmPlanner` 间接完成。

## 4. 读写权限矩阵

| 组件 | 可读取 | 可写入 | 不应直接写入 |
| --- | --- | --- | --- |
| GraphExecutor | execution graph, context tree | run state, run events | thinking graph, quest tree |
| Agent | context tree, thinking graph, quest tree slice | thinking graph, context tree, tool output | execution graph |
| Tool | runtime context, execution graph if authorized | tool result, graph transaction if authorized | agent private context |
| GraphPolicy | quest tree, thinking graph, runtime state, capabilities | graph transaction proposal | raw agent memory |
| QuestPlanner | user input, thinking graph, context tree | quest tree | execution graph |
| ContextManager | context tree, thinking graph refs | context tree | execution graph |
| ThinkingGraphManager | thought events, agent/tool outputs | thinking graph | execution graph |

说明：

- agent 不应直接改 execution graph；它应输出结构化意图，由授权 tool 或 policy 层提交图事务。
- tool 只有具备明确 capability 时才能改图，例如 `graph_mutation`。
- GraphPolicy 是跨图决策层，负责把任务和认知信息翻译成执行图变更。

## 5. 推荐运行循环

一次完整 run 可以分成以下阶段：

1. 接收用户输入。
2. `QuestPlanner` 创建或更新 quest tree。
3. `GraphPolicy` 检查 quest tree、agent capability、当前 execution graph 和 runtime state。
4. 如有必要，`GraphPolicy` 通过 `GraphTransaction` 修改 execution graph。
5. `GraphExecutor` 根据 execution graph 执行 agent/tool。
6. agent 通过 `ContextManager` 获取激活上下文。
7. agent/tool 产出结果。
8. 结果写入 thinking graph、context tree 或 quest tree status。
9. 如果任务未完成，回到第 3 步继续调整执行拓扑。
10. 输出最终结果，并持久化 run events、graph events、quest state 和必要上下文。

## 6. 与当前代码的对应关系

当前代码中已经有一部分实现基础：

- `core/policy.py` 中的 `ExecutionGraph`、`AgentNode`、`ToolNode` 对应 dynamic execution graph 的模型层。
- `core/executor_parts/engine.py` 中的 `GraphExecutor` 对应执行器。
- `core/graph_transaction.py` 对应执行图事务。
- `core/context_graph.py` 和 `core/cognitive.py` 可以作为 thinking graph / context tree 的一部分基础。
- `core/task_graph.py` 可以作为 quest tree 的基础。
- `web/runstore/` 和 `core/runtime_info.py` 可以作为 run events 与 runtime projection 的基础。

当前主要问题是：

- `Core` 同时承担 registry、runtime state、graph state、event recording、cognitive state 等职责，边界过重。
- execution graph 模型仍然知道如何运行，模型层和执行层没有完全拆开。
- agent output protocol 仍依赖较多魔法字段，例如 `content`、`final_report`、`metadata_patch`、`next_node_id`。
- graph state 和 graph event 的 revision 来源需要统一，避免双账本。

## 7. 建议演进顺序

第一阶段：明确协议。

- 定义 `AgentOutputEnvelope`。
- 定义 `NodeResult`。
- 定义 `GraphMutationProposal`。
- 定义 `ContextNode`、`ThoughtNode`、`QuestNode` 的最小 schema。

第二阶段：拆分 Core。

建议将当前 `Core` 拆成：

```text
RuntimeKernel
AgentRegistry
ToolRegistry
ExecutionGraphStore
RuntimeEventStore
ContextManager
ThinkingGraphManager
QuestManager
```

第三阶段：建立 policy 层。

- 新增 `GraphPolicy` 或 `SwarmPlanner`。
- 它读取 quest tree、thinking graph、agent capability 和 runtime state。
- 它只产出 graph mutation proposal，不直接执行 agent。

第四阶段：统一持久化。

- 明确 graph event log 是否是唯一事实源。
- 如果 event log 是事实源，则 current graph state 应是 projection。
- 如果 current graph state 是事实源，则 graph events 应只作为审计记录。
- 推荐使用 event log 作为事实源，current state 作为投影缓存。

## 8. 最终架构一句话

Angelus 的核心不是“让多个 agent 按顺序聊天”，而是：

> 用 quest tree 表达任务结构，用 execution graph 控制执行拓扑，用 context tree 控制上下文可见性，用 thinking graph 沉淀共享认知，再由 policy 层把它们组合成一个可动态演化、可追踪、可审计的 agent swarm runtime。
