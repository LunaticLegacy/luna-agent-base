# Angelus Memory Graph (alpha)

Angelus Memory Graph 是 luna-agent-base 的正式 alpha 核心记忆子系统，负责为 agent 提供长期对话历史管理、关键记忆提取、上下文压缩与记忆使用追踪。

## 模块定位

**负责：**
1. **Episode history graph** — 将对话轮次记录为 DAG 节点；
2. **Context selection** — 每轮 agent 调用前选择需注入 prompt 的历史节点；
3. **Context packing** — 将旧上下文压缩为 summary node；
4. **Pinned memory** — 提取不可压缩的关键记忆（公式、约束、接口定义、用户偏好）；
5. **Memory retrieval** — 根据当前输入检索相关记忆；
6. **Memory usage trace** — 记录本轮注入的记忆、agent 声称使用的记忆、runtime 验证结果。

**不负责：**
- 执行图调度、tool 权限、agent 创建/删除、swarm 加载、graph_editor_tool 的动态图修改 —— 这些仍由 luna-agent-base 现有 runtime 处理。

## 目录结构

```text
core/memory/
├── __init__.py
├── types.py              # EpisodeNode, KeyMemory, MemoryContextPlan, MemoryUsageTrace
├── episode_graph.py      # DAG  episode 图与压缩
├── memory_store.py       # KeyMemory 存储与 canonical 去重
├── planner.py            # LLM 驱动的上下文决策
├── context_builder.py    # 按分区构造 prompt
├── lifecycle.py          # 记忆生命周期规则
├── usage_trace.py        # 使用追踪与验证
└── runtime.py            # AgentMemoryRuntime  orchestration
```

## 核心数据结构

### EpisodeNode
- `node_id`, `user_content`, `assistant_content`
- `parent_ids`, `child_ids`
- `is_summary`, `summarizes`, `summarized_by`
- `active`, `archived`, `created_at`, `metadata`

### KeyMemory
- `memory_id`, `content`, `kind`
  - `kind` 可选值：`fact`, `formula`, `constraint`, `preference`, `api_contract`, `project_goal`, `timeline_constraint`, `decision`, `warning`
- `tags`, `source_node_ids`, `pinned`, `packable`, `status`
  - `status` 可选值：`candidate`, `committed`, `rejected`
- `created_turn_id`, `canonical_key`, `confidence`, `metadata`

### MemoryContextPlan
- `selected_node_ids`, `selected_memory_ids`
- `pack_triggers`, `compressed_node_ids`, `summary_node_ids`
- `memory_queries`, `prompt_messages`, `token_estimate`, `reasoning`

### MemoryUsageTrace
- `injected_memory_ids`, `declared_used_memory_ids`, `verified_used_memory_ids`
- `invalid_memory_refs`, `unused_injected_memory_ids`, `verification_notes`

## 生命周期规则

1. 当前轮提取的新记忆只能进入 `candidate` 状态；
2. `candidate` memory 不允许注入当前轮 prompt；
3. 回答完成后，runtime 校验 candidate memory；
4. 校验通过后变为 `committed`；
5. 只有 `committed` 且 `created_turn_id` 早于当前轮的 memory，才能被注入 prompt；
6. `pinned` memory 不允许被 summary packing 改写；
7. `formula` / `constraint` / `api_contract` 默认 `pinned=True, packable=False`；
8. 普通 `fact` / `decision` / `timeline_constraint` 默认可以不 pinned，但 `timeline_constraint` 应在 prompt 中作为约束类记忆单独展示。

## 上下文压缩

压缩后状态：
- `pack_triggers`: 触发压缩的节点；
- `compressed_nodes`: 实际被压缩的节点；
- `summary_nodes`: 新生成的摘要节点。

压缩后原始节点不删除，而是 `active=False, archived=True`，并在 `summarized_by` 中记录摘要节点 id。活跃图使用摘要节点接续后续对话，归档图仍可追溯原始节点。

最终状态打印区分：
- 【Active Graph 活跃图】
- 【Archived Graph 已归档节点】
- 【Pinned Memory 永久记忆】
- 【All Memory 全部记忆】

## Prompt 构造格式

构建 prompt 时区分不同类型记忆：

```text
【Pinned Memory / 精确保留记忆】
- [M0] ...

【Timeline Constraints / 时间线约束】
- [M2] ...

【Semantic Memory / 语义记忆】
- [M4] ...

【Packed History / 压缩历史】
- [S6] ...

【Recent Turns / 最近对话】
User: ...
Assistant: ...
```

## Agent 接入点

在 `Agent.round_call` 中加入 `AgentMemoryRuntime` hook：

- `before_round`：检索 committed memories，构建 prompt context，决定是否压缩旧上下文，返回 `MemoryContextPlan`。
- `after_round`：写入 episode node，提取 candidate memories，校验并 commit，写入 usage trace。

## 配置

`config.toml`：

```toml
[app.memory_graph]
enabled = true
max_context_nodes = 6
pack_keep_recent = 2
enable_usage_trace = true
enable_candidate_memory = true
```

新增模块默认可关闭，不破坏现有行为。

## 持久化

初期使用 JSON 文件持久化：

```text
agents/<swarm_name>/runtime_info/memory/
├── episode_graph.json
├── memories.json
├── memory_events.jsonl
└── usage_traces.jsonl
```

后续可接入 `ContentStore` 适配器。

## 测试

新增测试覆盖：
- `test_episode_graph_compression.py` — 压缩后 summary node、archived 状态、active path
- `test_pinned_memory.py` — pinned 默认、canonical 去重
- `test_memory_lifecycle.py` — candidate 不可注入、commit 后可用
- `test_context_builder.py` — prompt 分区
- `test_usage_trace.py` — 注入记录、invalid 声明、candidate 使用判 invalid

## 参考实现

本模块基于参考实现 [memory_graph](https://github.com/LunaticLegacy/memory_graph.git) 重构而来，已整合进 luna-agent-base 的现有 agent runtime、FastAPI、run session、runtime_info 和 ContentStore 架构。
