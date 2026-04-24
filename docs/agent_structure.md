# 当前 Agent 结构说明

本文档总结当前项目里 `agents/` 下 swarm 包的结构，以及 `deepseek_demo` 这一组 agent 的组织方式。

## 1. 总体分层

当前系统的 agent 相关结构可以分成四层：

- `core/`：运行时与编排内核，负责 agent、tool、skill、graph 的注册、校验和执行。
- `agents/`：业务 swarm 包目录，每个子目录代表一个可加载的 swarm。
- `tools/`：默认工具实现，供 swarm 直接复用，也可以被单独引用。
- `web/`：HTTP 接入层，用 Flask 暴露运行时接口。

## 2. Swarm 包结构

当前 `agents/deepseek_demo/` 是一个完整的 swarm 包，包含：

```text
agents/deepseek_demo/
  swarm.toml
  graph.py
  agents/
    planner.py
    researcher.py
    writer.py
    reviewer.py
    publisher.py
  skills/
    planner.prompt.md
    planner.prompt.toml
    researcher.prompt.md
    researcher.prompt.toml
    writer.prompt.md
    writer.prompt.toml
    reviewer.prompt.md
    reviewer.prompt.toml
    publisher.prompt.md
    publisher.prompt.toml
```

### 2.1 `swarm.toml`

`swarm.toml` 是这个 swarm 的索引文件，负责声明：

- `graph_file`
- `agent_files`
- `skill_files`
- `tool_files`
- 默认 LLM 后端配置

它的职责是“索引和约束”，不是执行逻辑。

### 2.2 `agents/*.py`

每个 agent 文件只负责定义一个 `AGENT` 字典。

例如：

- `agent_id`
- `name`
- `skill_name`
- `backend_name`

当前这些文件本质上是**agent blueprint**，即配置描述，不包含行为逻辑。

### 2.3 `skills/*.prompt.md` 与 `skills/*.prompt.toml`

当前 skill 被拆成两部分：

- `*.prompt.md`：纯提示词文本
- `*.prompt.toml`：skill contract，定义输入/输出/依赖/前置条件/后置条件

这样 skill 不再只是 prompt asset，而是一个可描述、可校验的能力单元。

## 3. 当前 Demo 的 Agent 职责

当前 `agents/deepseek_demo/` 包含 7 个 agent：

### 3.1 `orchestrator`

- 负责分析用户研究请求
- 输出 JSON 格式的研究计划（topic/angles/depth/estimated_researchers）
- 作为 swarm 的入口和全局框架设定者

### 3.2 `organizer`

- 负责自适应架构控制
- 在 preflight 阶段判断分支树应该保持宽松还是被收窄
- 在 dispatch 阶段分发并行研究分支
- 在 checkpoint 阶段读取合并后的分支结果，决定是否需要重新规划
- 可选使用 `graph_editor` 和 `agent_manager` 工具调整运行时图

### 3.3 `planner`

- 负责将 orchestrator 的框架转化为紧凑的任务简报
- 定义研究角度（structure/evidence/risk）
- 输出 JSON 格式的控制计划（content/plan/organization_hint）

### 3.4 `researcher`

- 负责补充证据、假设和风险
- 使用 `web_search` 工具收集信息
- 输出结构化研究笔记（Key Findings / Supporting Evidence / Sources / Gaps / Uncertainties）
- 为 writer 和 reviewer 提供支持信息

### 3.5 `writer`

- 负责把 planner 和 researcher 的结果整理成可发布草稿
- 使用 Markdown 格式，结构为 Executive Summary → Background → Analysis → Conclusion → References
- 更偏“内容生成”

### 3.6 `reviewer`

- 负责审查草稿和分支结果
- 输出 JSON 格式的 verdict（approve/revise/re_research）
- 通过 `next_node_ids` 指示执行器下一步跳转到哪个节点
- 不直接输出图编辑指令

### 3.7 `publisher`

- 负责输出最终用户可读结果
- 不暴露内部 routing 或 graph edit 细节

## 4. 当前工作图

当前 demo 的图是一个“编排 + 自适应分发 + 并行研究 + 汇聚 + 审查 + 发布”的流程。

### 主流程

1. `orchestrator` — 分析请求并生成研究框架
2. `organizer_preflight` — 判断分支树宽度
3. `planner` — 生成任务简报
4. `research_dispatcher`（organizer）— 并行分发三条研究分支：
   - `architecture_researcher_runtime`（结构/拓扑研究）
   - `evidence_researcher_runtime`（实现证据研究）
   - `risk_researcher_runtime`（风险/失效模式研究）
   - 每条分支通过 `agent_manager` 创建临时 agent，通过 `graph_editor` 插入节点，执行后销毁
5. `organizer_checkpoint` — 汇聚分支结果，决定是否需要重新规划
6. `writer` — 综合所有研究笔记撰写报告
7. `reviewer` — 审查并输出 verdict（approve → publisher, revise → writer, re_research → organizer_preflight）
8. `publisher` — 输出最终用户可读结果
9. `file_writer` — 将最终输出保存到 `outputs/deepseek_demo_final.txt`

### 图的关键点

- `orchestrator` 是入口节点（entry_node_id = 1）。
- `organizer_preflight` 和 `research_dispatcher` 使用 `organizer` agent，通过 `additional_prompt` 区分阶段（preflight / dispatch / checkpoint）。
- `research_dispatcher` 使用 `route_policy = "all"` 和 `join_node_id = 17` 实现三条研究分支的并行执行和汇聚。
- 每条研究分支包含 4 个 ToolNode：
  - `agent_manager` 创建临时 researcher
  - `graph_editor` 插入临时节点
  - `agent_manager` 销毁临时 researcher
  - `graph_editor` 移除临时节点
- 临时节点默认标记为 `runtime_transient = true`
- 若需要长期保留，则显式标记为 `persistence = "persistent"`，并将其作为可长期存在的 swarm 结构
- `reviewer` 通过返回 `next_node_ids` 控制路由：approve → 20, revise → 18, re_research → 2。
- `file_writer` 是出口节点（exit_node_id = 21）。

## 5. 当前工具使用方式

当前 demo 依赖的默认工具包括：

- `echo`
- `file_writer`
- `graph_editor_tool`
- `agent_manager_tool`
- `web_search_tool`

### 5.1 `graph_editor_tool`

这是当前最重要的运行时工具之一。它可以：

- 添加节点
- 删除节点
- 添加边
- 删除边
- 替换某个节点的后继
- 设置入口节点
- 设置出口节点

这意味着文件中定义的图只是初始图，运行时可以继续演化。

新增节点现在有明确生命周期语义：

- `transient`：用完即弃的运行态节点
- `persistent`：长期保留的节点，直到被显式编辑删除、禁用或替换

运行时会把生命周期写成结构化 `node_lifecycle` 元数据，建议包含：

- `runtime_transient`
- `persistence`
- `lifetime_policy`

默认情况下，新增节点应当是 `transient`，只有明确声明时才进入 `persistent`。

### 5.2 `agent_manager_tool`

用于在运行时创建和销毁临时 agent。当前 demo 在研究分支中使用它来：

- 创建临时 researcher（`create_agent`）
- 销毁临时 researcher（`destroy_agent`）

### 5.3 `file_writer`

用于把结果写入文件。当前 demo 默认写到：

- `outputs/deepseek_demo_final.txt`

### 5.4 `web_search_tool`

用于为 researcher 提供网络搜索能力。

## 6. Skill Contract 的意义

当前 skill contract 文件的目的，是把 skill 从“提示词文件”升级成“可验证能力描述”。

它目前包含：

- `capability`
- `description`
- `input_schema`
- `output_schema`
- `requires_tools`
- `requires_skills`
- `preconditions`
- `postconditions`
- `failure_policy`
- `parallelizable`

这样后续可以更容易做：

- 图校验
- 能力依赖分析
- 并行性判断
- 失败恢复策略

## 7. 目前的设计定位

现在这套结构的定位是：

- `agent` 是执行角色
- `skill` 是能力契约和提示词资产
- `graph` 是编排结构
- `tool` 是运行时能力扩展
- `core` 是 runtime 解释器

## 8. 运行态边界

这里有一个很重要的实现约束：`agent` 对象本身是长生命周期的，不会为每次请求自动重建。

因此，当前运行态可以分成两类：

- 请求级运行态
  - `ExecutionState` 会在每次 `graph.run()` 时新建
  - `RunRecord` 只负责后台 run 的事件和快照，不会回灌到模型
- agent 级运行态
  - `Agent._context.messages` 会保留历史消息
  - `Agent._context.metadata` 会保留 `last_round`、`turns`
  - `Agent.cognitive_graph` 会持续累积工具调用和推理痕迹

为了防止上一轮内容污染下一轮，当前路由层会在 swarm run 开始前调用 `core.reset_runtime_state()`，把这些可变状态清空后再执行图。

这意味着：

- `run` / `start` / `runs` 适合做“单次任务执行”
- 如果你在调试单个 agent，`/agents/<agent_id>/round` 仍然可能保留上下文，这是为了保留交互式调试体验
- `orchestrator` 和 `organizer` 作为架构控制 agent，同样会保留上下文，但 run 边界重置会清空所有 agent 的私有状态
- 如果你希望完全无状态，需要在路由层或调用方显式重置，而不是假设 agent 默认短生命周期

## 9. 未来扩展建议

如果后续继续扩展这个 swarm，建议优先考虑：

- 增加真正的 router 节点
- 增加并行汇总节点
- 给 skill contract 增加更严格的 schema 校验
- 给 tool 增加分类和权限标记
- 给 graph editor 增加更细粒度的审计日志
