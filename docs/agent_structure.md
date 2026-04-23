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

### 3.1 `planner`

- 负责读取用户请求
- 产出结构化计划
- 识别哪些工作可以并行
- 作为 swarm 的分流起点

### 3.2 `researcher`

- 负责补充证据、假设和风险
- 为 writer 和 reviewer 提供支持信息
- 更偏“信息采集”和“证据整理”

### 3.3 `writer`

- 负责把 planner 和 researcher 的结果整理成可发布草稿
- 更偏“内容生成”

### 3.4 `reviewer`

- 负责审查草稿和分支结果
- 决定是否继续研究、重写或进入发布
- 输出图编辑指令，由 `graph_editor` 工具应用到运行时图

### 3.5 `publisher`

- 负责输出最终用户可读结果
- 不暴露内部 routing 或 graph edit 细节

## 4. 当前工作图

当前 demo 的图是一个“并行 + 汇聚 + 审查 + 动态改图 + 发布”的流程。

### 主流程

1. `planner`
2. 并行触发：
   - `researcher`
   - `writer`
3. 汇聚到 `reviewer`
4. `reviewer` 通过 `graph_editor` 修改图
5. `publisher`
6. `file_writer`

### 图的关键点

- `planner` 节点使用 `route_policy = "all"`，表示允许并行分支。
- `join_node_id = 4` 表示分支结果汇合到 `reviewer`。
- `graph_editor` 是 runtime 图编辑点，允许 swarm 在执行期间改写后续路径。
- `file_writer` 负责将最终输出保存到 `outputs/deepseek_demo_final.txt`。

## 5. 当前工具使用方式

当前 demo 依赖的默认工具包括：

- `echo`
- `file_writer`
- `graph_editor`

### 5.1 `graph_editor`

这是当前最重要的运行时工具之一。它可以：

- 添加节点
- 删除节点
- 添加边
- 删除边
- 替换某个节点的后继
- 设置入口节点
- 设置出口节点

这意味着文件中定义的图只是初始图，运行时可以继续演化。

### 5.2 `file_writer`

用于把结果写入文件。当前 demo 默认写到：

- `outputs/deepseek_demo_final.txt`

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
- 如果你希望完全无状态，需要在路由层或调用方显式重置，而不是假设 agent 默认短生命周期

## 9. 未来扩展建议

如果后续继续扩展这个 swarm，建议优先考虑：

- 增加真正的 router 节点
- 增加并行汇总节点
- 给 skill contract 增加更严格的 schema 校验
- 给 tool 增加分类和权限标记
- 给 graph editor 增加更细粒度的审计日志
