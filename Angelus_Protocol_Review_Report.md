# 《Angelus 当前 LLM 上下文互通协议审查报告》

> 审查范围：基于仓库代码，重点分析 `core/executor_parts/`、`core/runtime/`、`core/results.py`、`core/policy.py`、`core/toodefl.py`、`web/routes/swarms.py`、`agents/deepseek_demo/` 及相关工具定义。
> 
> 审查日期：2026-04-25

---

## A. 总览

当前 Angelus 的上下文互通模型采用**双模式运行**：

- **Legacy 模式**：`state.payload` 是可变的，每个节点执行后都会覆盖它。原始用户输入在第一个节点后就会丢失。
- **Envelope 模式**（推荐但非强制）：`state.payload` 是一个包含 `original_request` 等字段的不可变信封。节点输出写入 `state.metadata["outputs"]`，路由决策写入 `state.metadata["control"]`。

**关键字段定义与读写责任：**

| 字段 | 定义 | 谁写 | 谁读 | 谁传递 |
|---|---|---|---|---|
| **payload** | 当前执行状态的主负载。Legacy 模式下被节点覆盖；Envelope 模式下为不可变信封 dict | GraphExecutor 初始化；Agent/Tool 节点覆盖（Legacy） | 下一个节点的输入；Tool 的参数构建 | `ExecutionState` 对象在节点间传递 |
| **metadata** | 运行时元数据。Envelope 模式下包含 `outputs`、`control` 等子字段 | Agent/Tool 节点通过 normalization 写入；`metadata_patch` / `metadata_clear` 可修改 | 路由逻辑读取 `metadata["control"]`；后续 Agent 读取 `metadata["outputs"]` 构建 prompt | `ExecutionState` 深拷贝传递 |
| **trace** | `ExecutionStep` 列表，记录每个节点的输入/输出/状态 | `GraphExecutor._execute_from_node()` 在每个节点完成后 append | 外部 observer、RunRecord、SSE 流读取 | `ExecutionState.trace` |
| **branch_results** | 当 `route_policy="all"` 时，各分支执行结果的字典 | `GraphExecutor` 在分支合并时写入 | 后续 join node 可能读取 | `ExecutionState.branch_results` |
| **cognitive_graph** | 认知图（swarm 级共享 + agent 级私有）。节点类型包括 `FACT`, `GOAL`, `HYPOTHESIS`, `EVIDENCE`, `TOOL_RESULT`, `EXECUTION_TRACE` 等 | Agent 的 `round_call()` 自动将 tool call 图化；Agent 输出中的 `<cognitive_graph>` XML 标签被提取并合并 | `Core.build_thought_context_export()` 读取并生成 prompt 注入 | `Core.swarm_cognitive_graph`（内存态）；agent 私有图通过 `merge_agent_cognitive_delta()` 合并入 swarm |
| **additional_prompt** | 节点级额外提示。来自 `AgentNode.additional_prompt` | graph.py 中的节点定义写入 | `GraphExecutor` 将其与 cognitive_prompt 拼接后传入 `agent.round_call(additional_prompt=...)` | 通过 `AgentRoundResult` 返回记录 |
| **ToolContext** | 工具执行时的上下文对象，包含 `agent_id`, `node_id`, `rounds`, `workspace_root`, `metadata`, `core`, `graph`, `capabilities` | `GraphExecutor._execute_from_node()` 构造 | Tool 的 `execute(arguments, context=...)` 读取 | 每次 tool 调用时新构造 |
| **graph_edit** | 图修改指令。例如 `{"action": "replace_next", "from_node_id": 4, "to_node_ids": [5,9,13]}` | Agent 输出中的 `graph_edit` 字段被 `PayloadHelperMixin._extract_control_patch()` 提取 | `organizer` 等 agent 被 prompt 要求输出；但**实际执行 graph_edit 的是 `graph_editor_tool`**，不是 GraphExecutor 直接解析 | 从 agent output → `state.metadata["control"]` → 如果 agent 调用了 graph_editor tool，则 tool 内部执行修改 |
| **next_node_ids** | 下一跳节点 ID 列表 | Agent 输出（`next_node_ids`）或 Tool 输出；或 `node.next_node_ids` 静态定义 | `RoutingHelperMixin._resolve_next_targets()` 读取 | 通过 `NodeExecutionResult.next_node_override` 或 `metadata["control"]` 传递 |

**重要发现**：`graph_edit` 字段虽然在 agent output 中被提取到 `control_patch`，但 GraphExecutor 本身**不会自动执行 graph_edit**。实际改图必须由 agent 调用 `graph_editor_tool` 完成，或者由外部代码读取 `metadata["control"]` 后手动执行。这是当前协议的一个关键缺口。

---

## B. 用户输入协议

### B.1 HTTP 请求进入 GraphExecutor 的路径

```
HTTP POST /api/swarms/{swarm_name}/runs/execute
  → web/routes/swarms.py::_execute_swarm_run()
    → request_data = await parse_json_body(request)
    → payload = request_data.get("input")   # 任意 Any
    → rounds = int(request_data.get("rounds", 0))
    → GraphExecutor().execute(graph, core, payload, rounds=rounds)
```

### B.2 初始 ExecutionState 构造

```python
# core/executor_parts/engine.py::GraphExecutor.execute()
state = ExecutionState(payload=initial_payload, rounds=rounds)
```

`initial_payload` 是用户传入的 `request_data.get("input")`，**没有任何 schema 校验**。它可以是：
- `str`（Legacy 模式最常见）
- `dict`（如果包含 `"original_request"` 或 `"_envelope": True`，则触发 Envelope 模式）
- 任意其他类型

### B.3 当前实际结构

```python
@dataclass
class ExecutionState:
    payload: Any           # 用户 input 或上一个节点的输出（Legacy）/ 不可变信封（Envelope）
    rounds: int = 0        # 全局轮次计数，每个 AgentNode 执行前 +1
    metadata: Dict[str, Any] = field(default_factory=dict)
    trace: List[Dict[str, Any]] = field(default_factory=list)
    branch_results: Dict[str, Any] = field(default_factory=dict)
```

当 HTTP 请求体为 `{"input": "帮我写一个 transformer"}` 时：

```json
{
  "payload": "帮我写一个 transformer",
  "rounds": 0,
  "metadata": {},
  "trace": [],
  "branch_results": {}
}
```

当 HTTP 请求体为 `{"input": {"original_request": "帮我写一个 transformer", "artifact": "code/transformer.py", "requirements": ["使用 NumPy"]}}` 时：

```json
{
  "payload": {
    "original_request": "帮我写一个 transformer",
    "artifact": "code/transformer.py",
    "requirements": ["使用 NumPy"]
  },
  "rounds": 0,
  "metadata": {},
  "trace": [],
  "branch_results": {}
}
```

### B.4 原始用户输入是否被保留

- **Legacy 模式**：**否**。第一个 AgentNode 执行后，`state.payload` 被覆盖为 agent output。
- **Envelope 模式**：**是**。`payload["original_request"]` 始终不变，后续 agent 通过 `_build_envelope_agent_input()` 读取它。

### B.5 是否存在 canonical request / original_request 概念

- 在 **Envelope 模式** 下存在。`_build_envelope_agent_input()` 明确读取 `payload["original_request"]`、`payload["artifact"]`、`payload["requirements"]` 等字段。
- 但系统**不会强制**用户传入信封结构。如果用户只传了一个字符串，系统以 Legacy 模式运行，原始需求在第一个节点后丢失。

### B.6 当前设计中用户原始请求是否会丢失

**会**。这是当前设计的最大风险之一：

1. 如果用户输入是字符串，Legacy 模式下第一个 agent 输出直接覆盖 `state.payload`。
2. 即使 Envelope 模式下，如果某个 agent 输出 `{"original_request": "...", ...}` 但包含了覆盖键，目前没有机制阻止后续节点意外修改 `state.payload`（虽然 envelope 设计意图是 immutable，但 `state.payload` 只是 dict，没有真正的 immutability 保障）。

---

## C. AgentNode 到 AgentNode 的上下文互通协议

### C.1 AgentNode 的 raw LLM response 形态

```python
@dataclass
class AgentRoundResult:
    rounds: int
    user_message: str
    assistant_message: Optional[str] = None      # LLM 最终文本输出
    raw_response: Any = None                     # 原始 LLM 响应对象（OpenAI 格式等）
    additional_prompt: Optional[str] = None      # 注入的 cognitive context
    cognitive_graph_snapshot: Optional[Dict] = None
    cognitive_graph_delta: Optional[Dict] = None
```

`assistant_message` 是核心。它可能是：
- 纯文本
- JSON 字符串（如 `{"decision": "widen", "next_node_ids": [3]}`）
- Markdown 包裹的 JSON（如 ` ```json\n{...}\n``` `）
- 包含 `<cognitive_graph>` XML 标签的文本

### C.2 normalize 后的 output_payload / state_payload / routing_payload

```python
@dataclass
class NodeExecutionResult:
    output_payload: Any      # 用于事件/trace 的完整输出
    routing_payload: Any     # 用于路由决策的负载
    state_payload: Any       # Legacy 模式下成为新的 state.payload
    next_node_override: Optional[int] = None
```

**Envelope 模式下的 normalization**（`core/executor_parts/payloads.py:205-252`）：

1. 从 `assistant_message` 解析 JSON → `parsed_output`
2. `output_payload = parsed_output`（完整 dict）
3. `routing_payload = parsed_output`
4. `state_payload = result.assistant_message`（保留原始文本）
5. `metadata_patch = _extract_metadata_patch(parsed_output)`（非 control 字段）
6. `control_patch = _extract_control_patch(parsed_output)`（包含 `next_node_ids`, `branch`, `graph_edit` 等）

注意：`control_patch` 被存储到 `state.metadata["control"]`，但 `NodeExecutionResult` 本身并没有 `control_patch` 字段！

> **代码问题**：`engine.py:244` 读取 `getattr(node_result, "control_patch", None)`，但 `NodeExecutionResult` dataclass 并没有定义 `control_patch` 字段。这意味着 `control_patch` 永远是 `None`，Envelope 模式下的 routing control 实际上**不会被应用到 metadata**。
> 
> 实际上，`_normalize_agent_node_result` 返回的是 `NodeExecutionResult`，其字段只有 `output_payload`, `routing_payload`, `state_payload`, `next_node_override`。`_extract_control_patch` 的结果虽然在函数内部计算了，但**没有附加到返回结果上**。
> 
> 这是当前协议的一个 **严重实现缺陷**：Envelope 模式下 agent 输出的 `next_node_ids` / `graph_edit` / `decision` 等 control 字段虽然被提取，但**没有进入 state.metadata["control"]**，路由逻辑依赖的 `metadata.get("control")` 因此可能是空的。

### C.3 当前节点输出如何更新 state.payload

**Legacy 模式**：
```python
state.payload = node_result.state_payload
```

**Envelope 模式**：
```python
# payload 不更新，保持不可变
state.metadata.setdefault("outputs", {})
state.metadata["outputs"][str(node.node_id)] = node_result.output_payload or node_result.state_payload
```

### C.4 当前节点输出如何更新 state.metadata

**Legacy 模式**：
- `_normalize_agent_node_result` 中不直接修改 metadata（除非通过 `_state_payload_from_structured_agent_output` 中的 `_apply_metadata_updates` 和 `_preserve_report_fields`）
- `_apply_metadata_updates` 处理 `metadata_patch` 和 `metadata_clear`

**Envelope 模式**：
- 意图是写入 `state.metadata["outputs"][node_id]` 和 `state.metadata["control"]`
- 但如上所述，`control_patch` 没有正确传递

### C.5 下一个 AgentNode 实际收到的是什么

下一个 AgentNode 收到的是通过 `_build_envelope_agent_input()` 构建的一个**大字符串**，而不是原始 state 对象：

```
## Original Request
{payload["original_request"]}

## Target Artifact
{payload["artifact"]}

## Requirements
[...]

## Previous Node Outputs
### Node 1
{metadata["outputs"]["1"][:1200]}
### Node 2
{metadata["outputs"]["2"][:1200]}

## Additional Instructions
{node.additional_prompt}
```

**重要限制**：
- 每个节点输出被截断到 **1200 字符**
- 只有 `metadata["outputs"]` 中的内容被注入，如果某个节点没有正确写入 outputs，后续 agent 看不到

### C.6 additional_prompt 如何注入

```python
# engine.py:217-222
cognitive_prompt = self._inject_cognitive_context(core, node)
combined_prompt = node.additional_prompt
if cognitive_prompt:
    if combined_prompt:
        combined_prompt = f"{combined_prompt}\n\n{cognitive_prompt}"
    else:
        combined_prompt = cognitive_prompt

result = await agent.round_call(
    rounds=state.rounds,
    user_message=agent_input,
    additional_prompt=combined_prompt,
)
```

`node.additional_prompt` 来自 graph.py 中节点的定义。`cognitive_prompt` 来自 `_inject_cognitive_context()`，两者拼接后作为 `additional_prompt` 传入 `round_call()`。

在 `agent.py` 中：
```python
def _build_system_prompt(self, additional_prompt):
    prompts = [self.character_prompt.strip()]
    if additional_prompt:
        prompts.append(additional_prompt.strip())
    return "\n\n".join(prompts)
```

即：`system_prompt = character_prompt + "\n\n" + (node.additional_prompt + "\n\n" + cognitive_context)`

### C.7 cognitive context 如何注入

通过 `CognitiveContextMixin._inject_cognitive_context()`：

1. 尝试 `core.build_global_context_export(agent_id=node.agent_id)` → 全局变量
2. 尝试 `core.build_thought_context_export(...)` → 完整的认知上下文 prompt，包含：
   - Main Shared Graph Summary
   - Active Schedulable Subgraph
   - Private Workspace Summary
   - Thought Graph Output Contract（要求 LLM 输出 `<cognitive_graph>` JSON）
3. 拼接后返回字符串

### C.8 当前是否存在"中间 agent 摘要覆盖原始需求"的风险

**存在，且风险很高**：

1. Legacy 模式下，原始需求在第一个节点后就被覆盖。
2. Envelope 模式下虽然保留了 `original_request`，但：
   - `control_patch` 实现有缺陷，可能导致 routing 失败
   - `_build_envelope_agent_input()` 截断历史输出到 1200 字符，长报告会被截断
   - 如果 organizer agent 决定 "reroute" 并输出新的 `next_node_ids`，但没有正确保留上游 context，下游 agent 可能只看到截断后的摘要
3. `code_writer.prompt.md` 说 "Parse the user brief and identify the exact artifact to build"，但它接收的是 envelope 拼接后的字符串，如果上游 planner 的 output 很长，brief 部分可能被截断。

---

## D. AgentNode 到 ToolNode 的协议

### D.1 ToolNode 如何构造 arguments

```python
# core/executor_parts/payloads.py:192-199
def _build_tool_arguments(self, node: ToolNode, payload, runtime_metadata):
    if isinstance(payload, dict):
        base_arguments = dict(payload)
    else:
        base_arguments = {"input": payload}
    base_arguments.update(node.input_mapping)
    base_arguments.setdefault("runtime_metadata", dict(runtime_metadata))
    return base_arguments
```

即：
1. 如果 `state.payload` 是 dict，直接使用它作为参数基础
2. 否则包装为 `{"input": payload}`
3. 合并 `node.input_mapping`（覆盖同名字段）
4. 注入 `runtime_metadata`（即 `state.metadata`）

### D.2 input_mapping 如何工作

`input_mapping` 是 `ToolNode` 定义中的字段：

```python
@dataclass
class ToolNode(Node):
    tool_name: str = ""
    input_mapping: Dict[str, Any] = field(default_factory=dict)
```

在 `_build_tool_arguments()` 中：
```python
base_arguments.update(node.input_mapping)
```

这意味着 `input_mapping` 的键值对会**覆盖** payload 中的同名字段。例如，如果 payload 中有 `"path": "a.txt"`，而 `input_mapping = {"path": "b.txt"}`，最终参数使用 `"b.txt"`。

### D.3 ToolContext 包含哪些字段

```python
@dataclass
class ToolContext:
    agent_id: Optional[str] = None          # 调用者 agent ID
    node_id: Optional[int] = None           # 图节点 ID
    rounds: int = 0                         # 当前轮次
    workspace_mode: str = "workspace"       # 工作空间模式
    workspace_root: Optional[Path] = None   # 工作空间根目录
    metadata: Dict[str, Any] = field(default_factory=dict)  # 运行时 metadata 的拷贝
    core: Optional[Any] = None              # Core 运行时引用
    graph: Optional[Any] = None             # ExecutionGraph 引用
    capabilities: Set[str] = field(default_factory=set)     # 能力集合
```

### D.4 ToolContext 中 core / graph / metadata / capabilities 的作用

| 字段 | 作用 |
|---|---|
| `core` | 工具可以访问整个运行时。例如 `agent_manager_tool` 调用 `core.create_agent()`、`core.destroy_agent()`；`graph_editor_tool` 访问 `core.get_execution_graph()` |
| `graph` | `graph_editor_tool` 直接修改此 graph 对象（`add_node`, `remove_edge` 等） |
| `metadata` | 传递当前 `state.metadata` 的快照。工具可以读取但不能直接回写 state.metadata（除非通过返回值中的 `metadata_patch`） |
| `capabilities` | 权限边界。`require_tool_capability(context, "graph_mutation", "graph_editor")` 会检查此集合。来源于 `core.get_tool_capabilities(tool_name)`，而 capabilities 又来自 `swarm.toml` 中的 `[tool_capabilities]` 段 |

### D.5 Tool 的返回值如何进入 ExecutionState

```python
output_payload = await tool.execute(arguments, context=tool_context)
node_result = self._normalize_tool_node_result(state, output_payload, input_payload=input_payload)

if state.is_envelope:
    state.metadata.setdefault("outputs", {})
    state.metadata["outputs"][str(node.node_id)] = node_result.output_payload
else:
    state.payload = node_result.state_payload
```

工具返回的 dict 如果包含 `metadata_patch`，会通过 `_apply_metadata_updates` 合并到 `state.metadata`。

### D.6 Tool 是否可以修改 graph

**可以，但有条件**：
- 只有 `graph_editor_tool` 被赋予了 `graph_mutation` capability
- `graph_editor_tool` 直接操作 `context.graph`（`ExecutionGraph` 对象）
- 修改后，`RuntimeInfoManager` 会记录 graph 事件，但**不是通过 tool 返回值自动触发**，而是 `core` 内部在调用 graph 修改方法时通过 `_record_runtime_change` 记录

### D.7 Tool 是否可以修改 runtime state

**间接可以**：
- `agent_manager_tool` 可以调用 `core.create_agent()` / `core.destroy_agent()`，这会修改 `core.agents`
- 但 tool **不能直接修改** `ExecutionState.payload` 或 `metadata`。它只能通过返回 `metadata_patch` 来间接影响。

### D.8 Tool 是否可以访问 workspace_root

**可以**：
- `ToolContext.workspace_root` 已传递
- `file_writer_tool` 使用它来解析相对路径，并做路径安全检查（`_path_is_within_root`）

### D.9 Tool 权限边界目前是否清晰

**部分清晰，但有缺口**：

- **清晰的方面**：`capabilities` 机制存在；`require_tool_capability()` 会抛 `PermissionError`；敏感路径有黑名单（`.git`, `.venv`, `.bashrc` 等）
- **不清晰的方面**：
  1. `core` 引用给了工具**完全的运行时访问权**。虽然 capability 限制了特定操作，但如果 tool 代码直接调用 `core._execution_graph = None`，没有机制阻止。
  2. `ToolContext.agent_id` 在 GraphExecutor 中设置为 `None`（见 `engine.py:266`）。这意味着在 Graph 执行路径中，工具不知道自己被哪个 agent 调用。只有在 Agent 的 ReAct 循环中（`agent.py:234`），`agent_id` 才被设置。

### D.10 当前 ToolContext 的 schema

```python
{
  "agent_id": "str | null",           # 调用者 agent ID（GraphExecutor 中常为 null）
  "node_id": "int | null",            # 图节点 ID
  "rounds": "int",                    # 当前执行轮次
  "workspace_mode": "str",            # "workspace" | ...
  "workspace_root": "str | null",     # 绝对路径
  "metadata": "Dict[str, Any]",       # 当前 state.metadata 的深拷贝快照
  "core": "Core | null",              # 完整运行时引用
  "graph": "ExecutionGraph | null",   # 当前执行图引用
  "capabilities": "List[str]"         # 授权的能力列表
}
```

---

## E. ToolNode 到 AgentNode 的协议

### E.1 tool output 是直接变成 payload 吗

- **Legacy 模式**：是的。`_normalize_tool_node_result` 会提取 `final_payload` 或 `"content"`，赋值给 `state.payload`。
- **Envelope 模式**：不是。tool output 存入 `state.metadata["outputs"][node_id]`，`state.payload` 保持不可变。

### E.2 tool output 是否进入 metadata

是的。无论 Legacy 还是 Envelope：
- 如果 tool output dict 包含 `metadata_patch`，会合并到 `state.metadata`
- Envelope 模式下完整 tool output dict 进入 `state.metadata["outputs"]`

### E.3 tool output 是否进入 trace

是的。每个节点（包括 ToolNode）完成后都会生成 `ExecutionStep`：

```python
state.trace.append(
    ExecutionStep(
        node_id=node.node_id,
        node_name=node.node_name,
        node_type="ToolNode",
        input_payload=input_payload,
        output_payload=output_payload,
    ).__dict__
)
```

### E.4 后续 agent 如何看到 tool output

- **Legacy 模式**：如果 tool output 成为了 `state.payload`，下一个 agent 直接接收它（通过 `_format_agent_input`）
- **Envelope 模式**：后续 agent 通过 `_build_envelope_agent_input()` 读取 `state.metadata["outputs"]` 中该 tool node 的输出，截断到 1200 字符后注入 prompt

### E.5 如果 tool output 是结构化 dict，哪些字段会影响 routing

`_normalize_tool_node_result` 中：
```python
next_node_override = self._extract_next_node_id(output_payload)
```

即只有 `output_payload.get("next_node_id")` 会影响路由。其他字段如 `next_node_ids`、`branch`、`decision` 在 tool output 中**不会被路由逻辑识别**（因为 `_extract_next_node_id` 只读 `"next_node_id"` 单字段，不读 `"next_node_ids"` 列表）。

这是一个**不对称设计**：agent output 可以输出 `next_node_ids` 列表，但 tool output 只能输出 `next_node_id` 单值。

### E.6 tool output 中 next_node_ids / graph_edit 是否会被识别

- `next_node_ids`（列表）：**不会被识别**。`_extract_next_node_id` 只读 `"next_node_id"`。
- `graph_edit`：**不会被 GraphExecutor 识别**。tool 返回的 dict 中的 `graph_edit` 会作为普通数据存入 metadata，不会自动触发图修改。

---

## F. LLM 输出解析协议

### F.1 LLM 可以输出纯文本、JSON、markdown、代码块时分别怎么处理

解析逻辑在 `_parse_structured_agent_output()`（`payloads.py:332-345`）：

```python
def _parse_structured_agent_output(self, assistant_message):
    if not isinstance(assistant_message, str):
        return None
    candidate = assistant_message.strip()
    if candidate.startswith("```"):
        candidate = self._strip_code_fence(candidate)  # 去掉 ```json ... ```
    if not candidate.startswith("{") and not candidate.startswith("["):
        return None
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None
```

**处理规则**：
1. **纯文本**（不以 `{` 或 `[` 开头）：返回 `None`，进入纯文本路径
2. **Markdown 代码块**（以 ` ``` ` 开头）：剥离 fence，如果内部以 `{`/`[` 开头则尝试 JSON 解析
3. **JSON 对象/数组**：直接解析
4. **其他格式**：返回 `None`

**纯文本路径**：`state_payload = result.assistant_message`（Envelope）或 `_capture_report_payload`（Legacy 根据 node name 猜测是 writer/publisher 输出）。

### F.2 系统是否要求固定 JSON schema

**不要求**。系统使用开放式解析：
- 任何以 `{` 开头的输出都被尝试解析为 dict
- 然后 `_extract_metadata_patch` 和 `_extract_control_patch` 从中提取已知字段
- 未知字段被放入 `metadata_patch`

这意味着系统对 agent 输出是**宽容的、schema-less 的**。

### F.3 如果 agent 输出包含 content、decision、next_node_ids、graph_edit，这些字段如何处理

| 字段 | 处理方式 |
|---|---|
| `content` | 非 control 字段，进入 `metadata_patch`；Legacy 模式下可能作为 `state_payload`（优先级低于 `final_report`/`final_answer`） |
| `decision` | control 字段，进入 `control_patch`（但 control_patch 未正确传递，见 C.2） |
| `next_node_ids` | control 字段，进入 `control_patch`；同时 `_extract_next_node_id` 不会读取它（只读 `next_node_id` 单数）。**路由逻辑 `_resolve_next_targets` 会读它**，但那是从 `metadata["control"]` 或 `payload` 读取，不是从 `NodeExecutionResult.next_node_override` 读取 |
| `graph_edit` | control 字段，进入 `control_patch`。但 GraphExecutor 不自动执行它 |

### F.4 如果格式错误，系统如何 fallback

- JSON 解析失败 → `parsed_output = None` → `output_payload = result`（原始 `AgentRoundResult`）→ `routing_payload = state_payload = result.assistant_message`
- 纯文本 → Legacy 模式下根据节点名称（writer/publisher）自动捕获到 metadata；其他节点直接传递文本

### F.5 是否存在"模型输出推断过度"或"schema 不稳定"的风险

**存在严重风险**：

1. **Schema 不稳定**：agent 被不同的 prompt 文件要求输出不同格式：
   - `organizer.prompt.md` 要求输出 `{"decision", "content", "next_node_ids", "graph_edit"}`
   - `reviewer.prompt.md` 要求输出 `{"verdict", "feedback", "content"}`
   - `code_writer.prompt.md` 要求输出**纯 Python 代码**，不是 JSON
   - `writer.prompt.md` 要求输出 Markdown 报告
   
   但系统对所有 agent 使用**同一套** `_normalize_agent_node_result` 逻辑。这导致：
   - code_writer 输出的 Python 代码如果以 `def ` 开头而不是 `{`，会被当作纯文本处理（正确）
   - 但如果 code_writer 不小心输出了 `{"code": "..."}`，系统会把它当作结构化输出，可能丢失代码内容

2. **推断过度**：`_is_review_control_payload()` 通过 `verdict` 或 `branch` 值来猜测是否是 review payload，然后决定 fallback 行为。这种启发式推断可能在 agent 输出非预期格式时产生错误行为。

3. **截断风险**：`_build_envelope_agent_input` 截断历史输出到 1200 字符，如果 agent 输出的是关键结构化数据，截断后可能变成无效 JSON，但系统不会重新解析它，只是作为字符串注入 prompt。

---

## G. Routing / Handoff 协议

### G.1 默认 next_node_ids 如何决定

优先级从高到低（`_resolve_next_targets`，`routing.py:55-113`）：

1. `next_node_override`（来自 `NodeExecutionResult`，由 `payload.get("next_node_id")` 提取）
2. **Envelope 模式**：`metadata["control"]` 中的：
   - `next_node_ids`（列表）
   - `branch`（字符串，匹配 edge label/condition）
   - `branches`（列表）
3. **Legacy 模式**：`payload` dict 中的同名字段
4. `graph.outgoing_edges(node.node_id)` 按 priority 排序
5. `node.next_node_ids`

### G.2 next_node_override 如何决定

来自 `_extract_next_node_id(payload)`，读取 `payload["next_node_id"]`（注意是单数，不是复数）。

### G.3 routing_payload 是什么

`NodeExecutionResult.routing_payload`：
- 如果 agent 输出被成功解析为 JSON dict → `routing_payload = parsed_output`
- 否则 → `routing_payload = result.assistant_message`（纯文本）

### G.4 node metadata route_policy 如何工作

```python
route_policy = str(node.metadata.get("route_policy", "first")).strip().lower()
```

- `"first"`（默认）：取 `next_targets[0]`
- `"all"`：对每个 `next_targets` 创建分支，并行（顺序）执行

### G.5 route_policy=all 时如何处理 branch

```python
if route_policy == "all":
    for branch_index, branch_node_id in enumerate(next_targets):
        branch_state = state.clone()
        branch_state.metadata["branch_index"] = branch_index
        branch_state.metadata["branch_source_node_id"] = node.node_id
        branch_state = await self._execute_from_node(..., branch_state, branch_node_id)
        branch_results.append({...})
    state.branch_results[str(node.node_id)] = branch_results
```

注意：分支是**顺序执行**的，不是真正的并行。每个分支获得 `state.clone()`（深拷贝）。

### G.6 join_node_id 如何工作

在 `route_policy="all"` 的分支全部完成后：

```python
join_node_id = node.metadata.get("join_node_id")
if join_node_id is None:
    return state  # 没有 join 节点，直接结束
join_node_id = int(join_node_id)
current_node_id = join_node_id  # 跳转到 join 节点
```

### G.7 decision=reroute 是否直接影响下一节点

**不会**。`decision` 字段只是 `control_patch` 中的一个普通字符串。路由逻辑不看 `decision`，只看 `next_node_ids` / `branch` / `branches`。`decision="reroute"` 必须通过配合 `next_node_ids` 才能实际影响路由。如果 agent 只输出了 `"decision": "reroute"` 而没有 `next_node_ids`，路由会 fallback 到 graph edges。

### G.8 next_node_ids 是否来自 LLM 输出

**是的**，在 Envelope 模式下意图如此。但存在以下问题：
- 如 C.2 所述，`control_patch` 未正确传递到 `state.metadata["control"]`
- 即使正确传递了，路由逻辑读取的是 `metadata["control"]["next_node_ids"]`，这需要 normalization 正确写入

### G.9 GraphExecutor 如何 validate next targets

```python
self._validate_next_targets(graph, node, next_targets)
```

验证规则：
1. 目标节点必须存在于 `graph.nodes`
2. 目标节点必须在 `graph.outgoing_edges(current_node)` 或 `current_node.next_node_ids` 中
3. **例外**：如果当前节点是 `graph_editor` tool node，且目标节点是 transient 节点，则允许动态路由

### G.10 流程图

```
Agent output (assistant_message)
  ↓
_parse_structured_agent_output()
  ├─ 是 JSON dict → parsed_output
  └─ 否 → parsed_output = None
  ↓
_normalize_agent_node_result()
  ├─ Envelope 模式:
  │   ├─ output_payload = parsed_output
  │   ├─ routing_payload = parsed_output
  │   ├─ state_payload = assistant_message (原始文本)
  │   ├─ metadata_patch = 非 control 字段
  │   └─ control_patch = {next_node_ids, branch, decision, graph_edit, ...}
  │      ⚠️ 但 control_patch 没有附加到 NodeExecutionResult！
  └─ Legacy 模式:
      ├─ state_payload = 压缩后的字符串
      └─ output_payload / routing_payload = parsed_output
  ↓
routing_payload + next_node_override + state.metadata
  ↓
_resolve_next_targets()
  ├─ 1. next_node_override?
  ├─ 2. metadata["control"]?      ← Envelope 意图路径
  ├─ 3. payload dict?             ← Legacy 路径
  ├─ 4. outgoing_edges?
  └─ 5. node.next_node_ids
  ↓
_validate_next_targets()
  ↓
next node(s)
```

---

## H. Graph Edit 协议

### H.1 graph_edit 是从哪里来的

来自 agent 的 JSON 输出中的 `"graph_edit"` 字段。例如 `organizer.prompt.md` 明确要求：

```json
{
  "graph_edit": {
    "action": "replace_next",
    "from_node_id": 4,
    "to_node_ids": [5, 9, 13]
  }
}
```

### H.2 谁执行 graph_edit

**不是 GraphExecutor，而是 `graph_editor_tool`**。

`PayloadHelperMixin._extract_control_patch()` 会把 `graph_edit` 提取到 `control_patch`，但：
- `control_patch` 没有正确写入 `state.metadata["control"]`（见 C.2）
- 即使写入了，GraphExecutor 也不会自动读取 `metadata["control"]["graph_edit"]` 并执行图修改

实际执行路径：
1. agent 输出包含 `graph_edit`
2. agent 被绑定了 `graph_editor` tool（如 organizer）
3. 在 ReAct 循环中，LLM 调用 `graph_editor` tool，传入参数
4. `graph_editor_tool.execute()` 内部调用 `GraphTransaction` 修改 `context.graph`

### H.3 graph_edit 是否直接改 ExecutionGraph

是的，但只能通过 `graph_editor_tool` 修改。`GraphTransaction` 提供原子性：

```python
# tools/graph_editor_tool.py 中（根据 explore 报告）
GraphTransaction 用于 atomic mutations
```

### H.4 修改后是否持久化

**部分持久化**：
- `RuntimeInfoManager.record()` 会记录 graph 变更事件到 `graph_events.jsonl`
- `current.json` 包含最新 graph snapshot
- 但 `ExecutionGraph` 对象本身是内存中的，重启后从 graph.py 重新加载，运行时修改**不会**自动写回 graph.py

### H.5 RuntimeInfo 是否记录 graph revision

是的。每次 graph 相关事件：
```python
self._graph_revision += 1
self._graph_hash = self._graph_hash_for_snapshot(graph_snapshot)
```

### H.6 graph_events.jsonl 记录什么

每行一个 JSON，包含：
```json
{
  "sequence": 1,
  "revision": 1,
  "timestamp": "...",
  "action": "graph_add_agent_node",
  "subject_kind": "graph",
  "subject_id": "...",
  "detail": {...},
  "change": {"change_id": "graph-00000001", "kind": "...", "subject": {...}, "summary": "..."},
  "snapshot": {...},
  "graph_hash": "sha256:..."
}
```

### H.7 graph hash 如何生成

```python
def _graph_hash_for_snapshot(self, snapshot):
    encoded = json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
```

### H.8 当前 graph mutation 是否事务化

`graph_editor_tool` 使用了 `GraphTransaction`，但 explore 报告未提供其完整实现。从代码引用来看，存在事务化的意图，但无法确认是否支持完整的 rollback。

### H.9 graph mutation 是否可 rollback

**不明确**。`RuntimeInfoManager` 保存了历史 snapshot，理论上可以 diff 回退，但代码中没有看到显式的 rollback API。

### H.10 agent/tool 是否有 capability 限制

是的，通过 `ToolContext.capabilities` 和 `require_tool_capability()`：
- `agent_manager` → `"agent_lifecycle"`
- `graph_editor` → `"graph_mutation"`
- `file_writer` → `"file_write"`
- `web_search` → `"network_access"`

但这些 capabilities 是**静态配置**在 `swarm.toml` 中的，运行时不会动态增减。

---

## I. Cognitive Context / Swarm Context 协议

### I.1 swarm_cognitive_graph 存在哪里

存在 `Core.swarm_cognitive_graph`（`core/runtime/core_runtime.py`），是一个 `CognitiveGraph` 实例。

### I.2 agent cognitive_graph_delta 如何 merge 到 swarm

在 `GraphExecutor._execute_from_node()` 中：

```python
merge_delta = getattr(core, "merge_agent_cognitive_delta", None)
if callable(merge_delta):
    merge_delta(blueprint_ref, getattr(result, "cognitive_graph_delta", None))
else:
    core.merge_agent_cognitive_graph(node.agent_id)
```

`merge_agent_cognitive_delta()`（`cognitive_state.py:35-46`）：
```python
def merge_agent_cognitive_delta(self, agent_id, snapshot):
    if not snapshot:
        return
    try:
        delta_graph = CognitiveGraph.from_dict(snapshot)
    except Exception:
        return
    merge_cognitive_graphs(self.swarm_cognitive_graph, delta_graph)
```

注意：`cognitive_graph_delta` 来自 `AgentRoundResult`，是**单个 round 的增量**，不是 agent 完整私有图。

### I.3 build_thought_context_export 做了什么

（`cognitive_state.py:145-195`）构造一个完整的 prompt 段落，包含：

1. **Main Shared Graph Summary**：通过 `build_context_graph_export()` 生成的 token-budgeted prompt
2. **Active Schedulable Subgraph**：当前 agent 的聚焦子图
3. **Private Workspace Summary**：agent 私有工作区的文件摘要
4. **Thought Graph Output Contract**：要求 LLM 在输出中包含 `<cognitive_graph>` JSON 块

### I.4 active_thought_subgraphs 是什么

```python
self.active_thought_subgraphs: Dict[str, CognitiveSubgraphDescriptor]
```

每个 agent 在同一时间只能有一个 active subgraph。当新的 subgraph 被 schedule 时，旧的被标记为 `"retired"`。Descriptor 包含 `root_node_ids`, `frontier_node_ids`, `purpose`, `owner_agent` 等。

### I.5 private workspace summary 如何注入 prompt

通过 `get_private_workspace_summary(agent_id)`：
1. 找到 agent 实例
2. 调用 `agent.summarize_private_workspace(max_files=8, max_chars=1200)`
3. 读取 `.angelus_private/swarms/{swarm}/runs/{run_id}/{agent_id}/` 下的最近文件
4. 生成 markdown 格式的摘要

这个摘要被放入 `ContextGraph` 的 `WORKSPACE` entry 中，最终出现在 `build_thought_context_export()` 的 prompt 里。

### I.6 哪些 context 是内存态

- `Core.swarm_cognitive_graph`
- `Core.active_thought_subgraphs`
- `Agent._context.messages`（对话历史）
- `Agent.cognitive_graph`（私有认知图）
- `ExecutionState`（执行状态）

### I.7 哪些 context 会落盘

- `RuntimeInfoManager`：
  - `events.jsonl`：所有运行时事件
  - `graph_events.jsonl`：图变更事件
  - `current.json`：最新 snapshot
- `Agent.persist_private_thought_snapshot()`：
  - `.angelus_private/.../cognitive_graph_snapshot.json`
- `file_writer_tool` 写入的文件

### I.8 reset_runtime_state 会清掉什么

`Core.reset_runtime_state()`（`cognitive_state.py:353-362`）：
1. 遍历所有 agent，调用 `agent.reset_runtime_state()`：
   - 清空 `agent._context.messages`
   - 重置 `agent.cognitive_graph` 为新空图
   - `agent.current_run_id = None`
2. `self.swarm_cognitive_graph = CognitiveGraph(...)`（**清空 swarm 级图**）
3. `self.active_thought_subgraphs.clear()`
4. `self.current_run_id = None`

**注意**：`reset_runtime_state()` 不会清空 `ExecutionState`，因为它不是 `Core` 的持久字段。每次 `GraphExecutor.execute()` 都会新建 `ExecutionState`。

### I.9 当前 cognitive graph 是否能作为持久长期记忆

**不能可靠地作为长期记忆**：
1. `swarm_cognitive_graph` 在 `reset_runtime_state()` 时被完全清空
2. 每次 HTTP 执行请求前，`_execute_swarm_run()` 都会调用 `swarm.core.reset_runtime_state()`，这意味着**每次 run 认知图都会被重置**
3. 虽然 agent 私有图可以通过 `persist_private_thought_snapshot()` 落盘，但 swarm 级共享图没有对应的持久化机制
4. `cognitive_graph_snapshot.json` 是分散在各个 agent workspace 中的，没有统一的加载/合并机制

---

## J. RuntimeInfo / Trace 协议

### J.1 node.started / node.completed / node.failed 分别记录什么

**node.started**：
```python
ExecutionEvent(
    event_type="node.started",
    node_id=node.node_id,
    node_name=node.node_name,
    data={
        "input_payload": input_payload,       # 节点输入（可能很大）
        "state_snapshot": state.snapshot(),   # 完整 state 深拷贝
    }
)
```

**node.completed**：
```python
ExecutionEvent(
    event_type="node.completed",
    data={
        "input_payload": input_payload,
        "output_payload": output_payload,
        "state_snapshot": state.snapshot(),
    }
)
```

**node.failed**：
```python
ExecutionEvent(
    event_type="node.failed",
    data={
        "input_payload": input_payload,
        "error": str(exc),
        "state_snapshot": state.snapshot(),
        "failure": failure.to_dict(),
        "regulation": regulation.to_dict() if regulation else None,
    }
)
```

### J.2 run.started / run.completed / run.failed 记录什么

**run.started**：entry_node_id, entry_node_name, state_snapshot
**run.completed**：final state_snapshot
**run.failed**：error, state_snapshot, failure, regulation

### J.3 trace 和 runtime_info/events.jsonl 的关系是什么

- `trace` 是 `ExecutionState.trace`，即 `ExecutionStep` 列表，保存在内存中，随 `ExecutionState` 返回
- `events.jsonl` 是 `RuntimeInfoManager` 写入的，包含更丰富的 event（`run.started`, `node.started`, `branch.started` 等），且包含 snapshot
- `GraphExecutor` 通过 `event_sink` 回调发射事件，在 `swarms.py` 同步执行路径中没有提供 `event_sink`，事件**不会**被记录！只有在 `use_background=True` 时，`RunRecord` 作为 `event_sink` 才会记录事件。

> **重大发现**：在同步执行路径（`POST /runs/execute`）中，`GraphExecutor.execute()` 被调用时没有传入 `event_sink`，因此所有 `ExecutionEvent` 都被丢弃，不会写入 `events.jsonl`。只有后台运行路径（`POST /runs`）才会记录事件。

### J.4 current.json 保存什么

`RuntimeInfoManager._write_snapshot()` 写入：
```json
{
  "sequence": 1,
  "timestamp": "...",
  "action": "...",
  "subject_kind": "...",
  "subject_id": "...",
  "detail": {...},
  "snapshot": {
    "agent_name": "...",
    "updated_at": "...",
    "agents": [...],
    "tools": [...],
    "skills": [...],
    "graph": {...},
    "last_event": {...},
    "graph_state": {...}
  }
}
```

### J.5 graph_events.jsonl 保存什么

每次 graph 变更时追加：
```json
{
  "sequence": 1,
  "revision": 1,
  "timestamp": "...",
  "action": "graph_add_agent_node",
  "subject_kind": "graph",
  "detail": {...},
  "change": {...},
  "snapshot": {...},
  "graph_hash": "sha256:..."
}
```

### J.6 trace 是否可用于 replay

**不足以完全 replay**：
- `trace` 包含每个节点的 `input_payload` 和 `output_payload`
- 但不包含：
  - 完整的 LLM prompt（`user_message` + `system_prompt` + `additional_prompt`）
  - `cognitive_context` 的内容
  - 路由决策的中间过程
  - agent 的 `raw_response`
  - 分支的完整并行状态（分支是顺序执行的）

### J.7 trace 是否足够还原当时 prompt

**不够**：
- `trace` 中的 `input_payload` 是 `state.payload`（Legacy）或 envelope（Envelope），不是实际传给 LLM 的字符串
- `additional_prompt` 和 `cognitive_prompt` 没有被记录到 trace 或 event 中（`_sanitize_detail` 会截断 prompt 内容到 500 字符）

### J.8 trace 是否保存了 raw_response / additional_prompt / cognitive graph snapshot

- `raw_response`：**没有**。`AgentRoundResult.raw_response` 未被写入 `ExecutionStep` 或 `ExecutionEvent`
- `additional_prompt`：**没有直接保存**。`_sanitize_detail` 会截断包含 "prompt" 或 "content" 的字段到 500 字符
- `cognitive_graph_snapshot`：**没有**。agent 的 `cognitive_graph_delta` 被合并到 swarm 图，但没有被记录到 trace 中

---

## K. 当前协议的问题

### K.1 payload 被中间节点覆盖，导致原始用户需求丢失

**确认存在**。Legacy 模式下 `state.payload` 被每个节点覆盖。Envelope 模式虽然设计为 immutable，但缺乏真正的不可变性保障（Python dict 可被修改）。

### K.2 metadata 保存了 plan，但后续 code_writer 未必读取

**确认存在**。`code_writer.prompt.md` 说 "Parse the user brief and identify the exact artifact to build"，但：
- 如果上游 planner 输出的 plan 很长，被截断到 1200 字符
- code_writer 依赖 `_build_envelope_agent_input()` 中的 `## Previous Node Outputs` 来获取 plan，但截断可能导致关键信息丢失
- 更重要的是，`payload["requirements"]` 是可信的原始需求，但 prompt 没有明确告诉 code_writer "优先使用 requirements，而不是被截断的上游输出"

### K.3 routing 节点把 payload 改成分类摘要

**在 Legacy 模式下确认存在**。orchestrator/organizer 等节点输出分类/决策 JSON，会覆盖 `state.payload`，导致下游 writer 收到的是 `{"decision": "...", "content": "..."}` 而不是原始需求。

### K.4 implementation brief 没有作为 canonical payload 保留

**确认存在**。虽然 Envelope 模式有 `payload["artifact"]` 和 `payload["requirements"]`，但：
1. 系统不强制使用 Envelope 模式
2. 即使使用 Envelope，如果某个节点返回了 `"original_request": "..."` 的 metadata_patch，是否会覆盖？不会，因为 payload 本身不更新。但下游 agent 如何区分 "原始需求" 和 "上游处理后的需求"？当前 prompt 结构没有区分。

### K.5 code_writer 可能收到空 brief 或弱 brief

**确认存在**。如果：
- 用户没有传 Envelope（即没有 `original_request`）
- 或 organizer 决定直接路由到 code_writer 但没有传递足够 context
- 或上一个节点的输出被截断到 1200 字符

code_writer 收到的 `## Previous Node Outputs` 可能非常薄弱。

### K.6 tool / agent 输出 schema 不稳定

**确认存在**。`_normalize_agent_node_result` 和 `_normalize_tool_node_result` 使用同一套开放式解析，对不同 agent（organizer JSON、writer Markdown、code_writer Python）没有区分处理。这导致：
- writer 输出的 Markdown 如果被错误解析为 JSON（极不可能，但）
- organizer 的 JSON 中字段含义没有 schema 约束
- tool 返回的 dict 中的字段没有被严格校验

### K.7 graph_edit / reroute 混在普通 payload 中

**确认存在**。`graph_edit` 是 agent JSON 输出中的一个字段，与 `content`、`decision` 等混在同一层级。虽然 `_extract_control_patch` 试图分离它们，但：
1. `control_patch` 没有正确传递（C.2）
2. 即使传递了，graph_edit 的实际执行依赖于 agent 调用 tool，而不是系统自动处理
3. `decision` 和 `next_node_ids` 也在同一层级，容易让 LLM 混淆

### K.8 cognitive context 与 execution context 边界不清

**确认存在**：
- `cognitive_graph` 包含 `TOOL_RESULT` 和 `EVIDENCE` 节点，这些是执行痕迹，不是认知推理
- `_public_thought_graph()` 会过滤掉 `EXECUTION_TRACE` 节点，但 `TOOL_RESULT` 和 `EVIDENCE` 仍然留在公共图中
- `build_thought_context_export()` 将 swarm 图、子图、私有工作区全部拼接进 prompt，没有区分 "认知上下文" 和 "执行上下文"

### K.9 trace 可观察但未必可恢复

**确认存在**：
- 同步执行路径没有 event_sink，trace 只在内存中
- trace 不包含 raw_response、完整 prompt、routing decision 理由
- 分支执行时 `state.clone()` 后的子状态没有被完整保存

### K.10 runtime state 与 prompt state 没有明确 schema version

**确认存在**：
- `ExecutionState` 没有 `schema_version` 字段
- `AgentRoundResult` 没有版本信息
- 如果未来 protocol 变更，无法向后兼容

---

## L. 当前协议总结表

| 通道 | 来源 | 目标 | 数据字段 | 是否结构化 | 是否可覆盖 | 是否落盘 | 风险 |
|---|---|---|---|---|---|---|---|
| user input → ExecutionState | HTTP POST `input` | `GraphExecutor.execute()` | `initial_payload: Any` | 否（任意类型） | 是（Legacy） | 否（仅内存） | 原始输入无 schema，易丢失 |
| AgentNode output → state.payload | `AgentRoundResult` | `ExecutionState` | `assistant_message` / 压缩后的字符串 | 是/否混合 | 是（Legacy） | 否 | 中间节点覆盖原始需求 |
| AgentNode output → state.metadata | `AgentRoundResult` | `ExecutionState.metadata` | `metadata_patch`, `outputs`, `control` | 部分结构化 | 是 | 否 | `control_patch` 实现缺陷 |
| AgentNode output → trace | `NodeExecutionResult` | `state.trace` | `ExecutionStep` dict | 是 | 否（append-only） | 否（同步路径） | 无 event_sink 时丢失 |
| ToolNode input → ToolContext | `GraphExecutor` | `tool.execute()` | `arguments + ToolContext` | 是 | 否 | 否 | `agent_id` 常为 null |
| ToolNode output → state.payload | `ToolDefinition.execute()` | `ExecutionState` | tool 返回的 dict/str | 部分结构化 | 是（Legacy） | 否 | tool output schema 不稳定 |
| cognitive graph → additional_prompt | `Core.swarm_cognitive_graph` | `agent.round_call()` | 拼接的 markdown 字符串 | 否（文本化） | 否 | 否（内存） | 执行痕迹混入认知图 |
| graph_edit → ExecutionGraph | `graph_editor_tool` | `ExecutionGraph` | GraphTransaction 操作 | 是 | 是 | 是（graph_events.jsonl） | 不自动执行，依赖 agent 调 tool |
| RuntimeInfo → current.json/events.jsonl | `RuntimeInfoManager.record()` | 磁盘 | 完整 snapshot + 事件 | 是 | 是（追加） | 是 | 同步路径不记录事件 |
| run events → SSE | `RunRecord.stream_events()` | HTTP SSE 流 | `ExecutionEvent` 序列 | 是 | 否 | 是（内存列表） | 仅后台运行模式有效 |

---

## M. 推荐的新协议（明确标注：这是建议，不是当前实现）

### M.1 建议方向

1. **payload 改为 canonical immutable request**：`payload` 永远不可变，所有节点输出进入 `metadata.node_outputs`
2. **metadata 改为 append-only node outputs**：`metadata.node_outputs[node_id] = {...}`，禁止 `metadata_clear`
3. **control 字段单独承载 reroute / graph_edit**：与 `payload` / `metadata` 分离，明确 `state.control` 字段
4. **artifact brief 单独结构化保存**：`payload.artifact` / `payload.requirements` 标准化
5. **code_writer 必须读取 payload.original_request 和 payload.requirements**：prompt 明确指示优先使用 canonical request
6. **tool call 使用显式 schema**：每个 tool 定义严格的输入/输出 JSON Schema，runtime 做校验
7. **cognitive context 与 execution context 分离**：execution trace 不进 cognitive graph；cognitive graph 不混入 tool_result
8. **RuntimeState 引入 schema_version**：支持协议演进
9. **trace 记录 prompt input / normalized output / routing decision**：可完整 replay
10. **graph mutation 走 transaction / validation / revision**：GraphExecutor 识别 `state.control.graph_edit`，自动提交到 GraphTransaction，验证后执行

### M.2 建议 schema

```json
{
  "schema_version": "angelus.runtime_state.v1",
  "payload": {
    "original_request": "用户原始输入文本",
    "artifact": {
      "type": "code|report|image|api",
      "target_path": "code/transformer.py",
      "description": "..."
    },
    "requirements": [
      "使用 NumPy 实现",
      "包含演示代码"
    ],
    "constraints": [
      "不依赖 PyTorch"
    ],
    "attachments": [
      {"name": "ref.md", "content": "..."}
    ]
  },
  "metadata": {
    "node_outputs": {
      "1": {"node_name": "orchestrator", "output": {"task_mode": "implementation"}, "timestamp": "..."},
      "2": {"node_name": "planner", "output": {"plan": {...}}, "timestamp": "..."}
    },
    "control": {
      "next_node_ids": [22],
      "decision": "reroute",
      "graph_edit": null
    },
    "diagnostics": {
      "total_rounds": 5,
      "total_tokens": 12345
    }
  },
  "trace": [
    {
      "node_id": 1,
      "node_name": "orchestrator",
      "status": "completed",
      "input_prompt": "完整的 LLM prompt 文本（包括 system + user + cognitive）",
      "raw_response": "LLM 原始响应对象",
      "normalized_output": {"task_mode": "implementation"},
      "routing_decision": {"next_node_ids": [2], "reason": "default_edge"},
      "timestamp": "..."
    }
  ],
  "branch_results": {},
  "runtime_context": {
    "swarm_name": "deepseek_demo",
    "run_id": "uuid",
    "cognitive_graph_revision": 3,
    "graph_hash": "sha256:..."
  }
}
```

### M.3 关键改进点说明

1. **`payload` 真正不可变**：通过 `dataclass(frozen=True)` 或 deepcopy + write-once 保证。所有节点通过 `metadata.node_outputs` 贡献输出。
2. **`state.control` 独立**：GraphExecutor 在每个节点后读取 `state.control.next_node_ids` 和 `state.control.graph_edit`，自动执行路由和图变更（通过 capability-gated GraphTransaction）。
3. **Trace 可 replay**：记录完整的 `input_prompt`（包括 cognitive context）、`raw_response`、`normalized_output` 和 `routing_decision`。
4. **Schema Versioning**：允许运行时识别旧版本 state 并迁移。
5. **Tool I/O Schema**：`ToolDefinition` 必须声明 `input_schema` 和 `output_schema`，runtime 在调用前/后做 JSON Schema 校验。
6. **Cognitive / Execution 分离**：
   - `cognitive_graph` 只包含推理节点（fact, hypothesis, claim, evidence 等）
   - `execution_trace` 只记录在 `state.trace` 中
   - `tool_result` 节点由 agent 私有图记录，不自动升入 swarm 图，除非 agent 明确输出 `<cognitive_graph>` 标记

---

## 附录：发现的代码缺陷汇总

1. **`NodeExecutionResult` 缺少 `control_patch` 字段**（`core/executor_parts/payloads.py` + `core/executor_parts/engine.py:244`）：Envelope 模式下 routing control 无法正确传递。
2. **同步执行路径不记录事件**（`web/routes/swarms.py`）：`GraphExecutor.execute()` 未传入 `event_sink`，导致 `events.jsonl` 只在后台运行模式下写入。
3. **`_extract_next_node_id` 只读 `"next_node_id"` 单数**：Tool output 中的 `"next_node_ids"` 列表不被识别。
4. **`ToolContext.agent_id` 在 GraphExecutor 中为 `None`**：工具无法知道调用者身份。
5. **`reset_runtime_state()` 清空 swarm cognitive graph**：每次 run 都丢失共享认知状态。
6. **`_build_envelope_agent_input()` 截断到 1200 字符**：长报告的关键信息可能丢失。

---

*报告结束。以上分析完全基于仓库实际代码，未推测未实现功能。*
