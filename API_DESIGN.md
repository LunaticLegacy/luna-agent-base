# Angelus API 设计文档 v2

基于 `modules/llm_fetcher` 重构，目标是：**比 LangGraph 更简单**。

---

## 核心原则

1. **一个 Swarm = 一个 Agent 群 + 一张图**。没有认知系统、故障分类、架构管理等重量级基础设施。
2. **API 即 Python 函数调用**。不需要 TOML 配置、manifest 声明、蓝图注册——直接 `Swarm(...)` 创建，`.run()` 执行。
3. **Web 层仅做薄透传**。提供 REST API 把 Swarm 的操作暴露出去，不夹带业务逻辑。

---

## 数据模型

```
Agent          — 一个 LLM 后端 + 系统提示词 + 工具
Tool           — 名称 + 描述 + JSON Schema + handler
ToolRegistry   — 注册/查找/执行工具
ExecutionGraph — 节点（Agent/Tool/Router/Join）+ 边
Swarm          — 一组 Agent + 一张 ExecutionGraph + 工具池
ThinkingGraph  — 思维链图（推理追踪用，非必需）
```

---

## 核心 API

### 创建 Swarm

```python
from angelus import Swarm

# 最简单的单 Agent
swarm = Swarm(
    model="deepseek/deepseek-v4-pro",
    system="你是一个翻译助手。",
)

# 带工具的 Swarm
swarm = Swarm(
    name="coder",
    model="kimi",
    system="你是一个代码助手。",
    tools=[
        Tool(name="read_file", description="读取文件", parameters={...}, handler=read_file),
        Tool(name="write_file", description="写入文件", parameters={...}, handler=write_file),
    ],
)

# 多 Agent 图（手动构建）
from angelus import Agent, Tool, Edge

swarm = Swarm(name="novelist")
swarm.add_agent("outline", model="kimi", system="你是大纲规划师。")
swarm.add_agent("writer",  model="kimi", system="你是小说写手。")
swarm.add_agent("critic",  model="kimi", system="你是质量审查员。")
swarm.add_edge("outline", "writer")
swarm.add_edge("writer", "critic")
swarm.add_edge("critic", "outline", label="revise")  # 循环修订
```

### 运行

```python
# 直接运行：输入 → 图执行 → 输出
result = await swarm.run("写一首关于秋天的诗")
print(result)  # str

# 流式运行
async for chunk in swarm.run_stream("写一首诗"):
    print(chunk, end="")

# 带上下文的运行
result = await swarm.run("写第二章", context={"chapter": 2, "style": "古龙"})
```

### 从配置加载

```python
# 从 TOML 文件
swarm = Swarm.from_file("novelist.toml")

# 从目录（兼容旧版 angelus swarm 包）
swarm = Swarm.from_package("agents/novelist")
```

---

## REST API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET /health` | 健康检查 | 返回 `{status: "ok"}` |
| `GET /swarms` | 列出已加载的 swarm | `{swarms: [{name, agent_count, tool_count}]}` |
| `POST /swarms/load` | 加载 swarm | `{source: "path/to/swarm.toml"}` → `{name, id}` |
| `DELETE /swarms/{name}` | 卸载 swarm | |
| `POST /swarms/{name}/run` | 执行 | `{input: "...", context?: {...}}` → `{output, trace}` |
| `POST /swarms/{name}/run/stream` | SSE 流式执行 | 逐个输出 token |
| `GET /swarms/{name}/graph` | 获取图结构 | 节点 + 边 |
| `GET /swarms/{name}/history` | 运行历史 | 最近 N 次运行的 input/output |

---

## 与 LangGraph 对比

| 维度 | LangGraph | Angelus v2 |
|------|-----------|------------|
| 定义图 | `StateGraph` + `add_node` + `add_conditional_edges` | `Swarm.add_agent()` + `add_edge()` |
| 状态管理 | 显式 `State` TypedDict + reducer | 隐式传递，payload 透传 |
| 工具 | `@tool` 装饰器 + 手动绑定 | `Tool(name=..., handler=...)` + 自动注册 |
| 流式 | `astream_events` | `run_stream()` |
| 持久化 | `Checkpointer` | 无内置（可插 SQLite） |
| 多 Agent | 需要 `create_react_agent` + Send API | `add_agent()` 即可 |
| 并行 | `fanout` / `Send` | `route_policy="all"` + `JoinNode` |
| 循环 | 条件边 | `label="revise"` 条件路由 |
| 学习曲线 | 概念多（State, Node, Edge, Checkpoint） | Swarm + Agent + Tool |

---

## 代码量预估

```
angelus/
├── __init__.py         # ~30 行：重导出
├── core.py             # ~200 行：Swarm, Agent, Tool 核心类
├── graph.py            # ~250 行：ExecutionGraph (已有的 llm_fetcher 版本)
├── thinking_graph.py   # ~300 行：思维链图（已有的）
├── llm_fetcher.py      # ~400 行：LLM 请求管理（已有的）
├── server.py           # ~150 行：FastAPI 启动 + 路由
└── tools/              # 内置工具
    ├── file.py         # file_reader, file_writer, file_editor
    ├── shell.py        # command_runner
    └── web.py          # web_search
```

总计约 **1300 行**（含已有代码），对比旧 angelus core/ 的 16000+ 行。

---

## 迁移路径

1. `pip install angelus-v2` 安装
2. `angelus serve` 启动 HTTP 服务
3. `swarm = Swarm(host="localhost:8877")` 远程连接
4. 旧 `agents/x/swarm.toml` 可通过 `Swarm.from_package()` 兼容加载
