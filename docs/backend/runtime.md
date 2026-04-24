# 后端 Runtime 运行时说明

本文只说明后端运行时注册表 `RuntimeRegistry` 的真实行为，以及它如何把 swarm 包从磁盘装载进内存。

## 运行时注册表是什么

`web/runtime.py` 里的 `RuntimeRegistry` 是后端的内存态运行时中心，主要保存三类状态：

- 已加载的 swarm：`swarms: Dict[str, LoadedSwarm]`
- 运行中的任务：`runs: RunRegistry`
- 启动阶段的错误信息：`load_error`

它本身不负责持久化，也不负责业务执行；它只是把“哪些 swarm 已经加载好”“哪些 run 还在活跃”这两件事管理起来，再供 Flask 路由层调用。

## 初始化流程

应用启动时，`web/app_factory.py` 会调用 `RuntimeRegistry.from_config_path(config_path)`。

初始化顺序是：

1. 读取根配置 `config.toml`
2. 从配置里解析 `swarm_root`
3. 调用 `reload_all()` 扫描并加载所有 swarm

如果根配置不存在，`load_root_config()` 会回退到默认配置：

- `swarm_root = agents`

如果配置文件能读，但后续某个 swarm 加载失败，`from_config_path()` 会捕获 `SwarmLoaderError`，把错误字符串写入 `load_error`，然后返回一个“可启动但未完成加载”的 registry。

如果根配置对象根本不可用，`reload_all()` 会直接抛 `SwarmLoaderError("Root config is not available.")`。

## swarm 发现与全量加载

全量加载由 `reload_all()` 完成，内部调用的是 `core/swarm_loader.py` 里的 `load_all_swarms(root)`。

### 发现规则

`discover_swarm_packages(root)` 会把 `root` 下的子目录当作候选 swarm 包，但只接受满足条件的目录：

- 必须是目录
- 目录里必须至少有一个 `.toml`

这意味着一个目录是否是 swarm 包，取决于它有没有 manifest 文件，而不是目录名本身。

### manifest 规则

`load_swarm_manifest(package_path)` 对 manifest 的要求比较严格：

- 目录里必须且只能有一个 `.toml`
- 必须存在 `[swarm]` 表
- 必须定义 `graph_file`
- `agent_files` 必须是非空数组
- `llm.default` 或 `[[llm.backends]]` 至少要有一个

如果这些条件不满足，就会抛 `SwarmLoaderError`，导致该 package 不能被加载。

### LLM 配置与环境变量

`[llm.default]` 和 `[[llm.backends]]` 支持以下字段：

```toml
[llm.default]
name = "kimi"
provider = "litellm"        # 可选: openai | litellm
api_url = "https://api.moonshot.ai/v1"
api_key = "${MOONSHOT_API_KEY}"  # 支持 ${VAR} 和 $VAR 环境变量替换
model = "moonshot/kimi-k2.5"
timeout = 120.0
max_retries = 1
```

**Provider 说明：**

- `openai`：使用 `openai` 库直接调用，适用于 OpenAI 兼容接口（如 DeepSeek）
- `litellm`：通过 `litellm.completion()` 调用，支持 100+ 提供商（Moonshot、Anthropic、Gemini 等）

**超时与重试：**

- 单次 LLM 请求会根据 `timeout` 限制等待时间。
- 遇到超时时，系统会自动重试一次；如果显式设置了 `max_retries`，则会在默认重试基础上继续增加重试次数。
- 这类重试只针对“尚未产出结果的超时失败”，不会吞掉已经开始输出的流式中断。

**环境变量替换：**

`api_key` 和 `api_url` 支持 `${VAR_NAME}` 或 `$VAR_NAME` 语法，在加载时自动替换为对应的环境变量值。如果环境变量不存在，替换为空字符串。`api_key` 替换后仍不能为空，否则加载会失败。

这意味着敏感信息（如 API key）可以不硬编码在 TOML 中，而是通过环境变量注入：

```bash
export MOONSHOT_API_KEY="sk-..."
python app.py
```

## HTTP API 安全设置

根配置 `config.toml` 的 `[api]` 表现在同时控制前端 API 参数、认证和 CORS：

```toml
[api]
base_url = "/api"
timeout_seconds = 120
sse_reconnect_interval_seconds = 5
auto_reconnect = true
require_auth = true
api_token_env = "ANGELUS_API_TOKEN"
cors_allowed_origins = ["http://localhost:4200", "http://127.0.0.1:4200"]
```

认证规则：

- `POST`、`PUT`、`PATCH`、`DELETE` 的 `/api/*` 请求属于高风险请求。
- 当 `require_auth = true` 或已配置 token 时，高风险请求必须携带 `Authorization: Bearer <token>` 或 `X-Angelus-Token: <token>`。
- token 优先从 `api_token_env` 指向的环境变量读取；也可以用 `api_token` 写在配置里，但不推荐把真实密钥落盘。
- `GET`、`OPTIONS`、健康检查和只读目录查询默认公开。

CORS 规则：

- `cors_allowed_origins` 为空时，运行时只允许内置的本地开发来源。
- `cors_allowed_origins` 指定后，只给匹配 `Origin` 的响应写入 `Access-Control-Allow-Origin`。
- 不再默认返回 `Access-Control-Allow-Origin: *`。

### Agent 工作空间访问

工作空间边界现在写在 `swarm.toml` 的 `[workspace]` 表里，而不是 agent Python 文件里。

例如：

```toml
[llm.default]
name = "kimi"
provider = "litellm"
api_url = "https://api.moonshot.ai/v1"
api_key = "${MOONSHOT_API_KEY}"
model = "moonshot/kimi-k2.5"
timeout = 120.0
max_retries = 1

[workspace]
default_mode = "workspace"
default_root = "."
```

`workspace` 当前支持两个模式：

- `workspace`: 只能访问分配的工作空间
- `full_access`: 不受工作空间边界限制

`default_root` 用来指定工作空间根目录。相对路径会按 swarm package 根目录解析，而不是按当前进程工作目录解析。runtime 会把它传给工具上下文，`file_writer` 会在 `workspace` 模式下拒绝写出该根目录之外的路径。

每个 graph run 会在自己的 workspace 根目录下拥有 run-scoped 私有运行目录：

```text
.angelus_private/runs/<run_id>/<agent_id>/
```

直接调用单个 agent round 且不属于 graph run 时，会使用：

```text
.angelus_private/manual/<agent_id>/
```

这个目录用于保存该 agent 的私有思考工件，例如认知图快照、草稿、缓存和本地笔记。它不会自动提升进 swarm 共享思考图；只有 agent 通过 `<cognitive_graph>...</cognitive_graph>` 输出显式节点和边时，才会合并进共享图。

如果某个 agent 需要特殊配置，可以在 `[workspace.agents.<agent_id>]` 下覆盖：

```toml
[workspace.agents.reviewer]
mode = "workspace"
root = "agents/docs_verifier"
```

### 工具能力声明

高风险工具必须在 `swarm.toml` 中显式声明能力。声明位置是 `[tool_capabilities]`：

```toml
[tool_capabilities]
agent_manager = ["agent_lifecycle"]
graph_editor = ["graph_mutation"]
file_writer = ["file_write"]
web_search = ["network_access"]
```

运行时会把能力写入 `ToolContext.capabilities`。工具执行前会检查所需能力：

- `file_writer` 需要 `file_write`
- `graph_editor` 需要 `graph_mutation`
- `agent_manager` 需要 `agent_lifecycle`
- `web_search` 需要 `network_access`
- `file_writer` 写 `config.toml`、`.env` 等配置/密钥文件时额外需要 `config_write`

`graph_editor` 新增节点时会读取生命周期字段：

- `runtime_transient`
- `persistence`
- `lifetime_policy`

其中 `runtime_transient` 仍然兼容旧语义，但现在更推荐显式使用 `persistence = "transient" | "persistent"` 来表达临时/持久节点。

如果 manifest 没有授予对应能力，即使 agent 绑定了工具，工具调用也会被拒绝。`agent_manager` 创建运行时 agent 时还会阻止从 `workspace` 升级到 `full_access`。

### 全量加载时的额外动作

`load_all_swarms()` 默认不会自动安装工具依赖。也就是说，启动阶段不会因为某个 swarm 声明了工具而自动执行：

- `python -m pip install -r <file>`

如果开发环境需要预装工具依赖，可以显式调用 `load_all_swarms(root, preinstall_tool_requirements=True)`，或手动执行对应的 `tool_requirements.txt`。这是为了避免“加载 swarm package”同时变成隐式网络安装和代码执行边界。

## 单个 swarm 的加载

`RuntimeRegistry.load_swarm(source, replace=False)` 负责把一个 swarm package 装进 registry。

它的流程是：

1. 调用 `resolve_package_path(source)` 找到 package 目录
2. 读取 manifest
3. 检查是否已存在同名 swarm
4. 调用 `build_core_from_package(...)` 构建 `LoadedSwarm`
5. 放进 `self.swarms[swarm_name]`

### 同名冲突

如果 registry 里已经存在同名 swarm，且 `replace=False`，会抛：

- `ConflictError("Swarm '<name>' is already loaded.")`

如果你显式传 `replace=True`，则允许覆盖旧条目。

### 构建顺序

`build_core_from_package()` 的顺序大致是：

1. 读取 agent blueprints
2. 读取 skill assets
3. 创建 `Core`
4. 注册 skill
5. 合并 LLM backends
6. 加载 tool modules 并注册 tool
7. 从 `[tool_capabilities]` 给工具写入能力集
8. 根据 blueprint 创建 agent
9. 加载 graph 文件并绑定到 core

这意味着：

- tool 先于 agent 创建完成注册
- 高风险工具只有声明了能力才可执行对应动作
- graph 最后附着到 core
- 只要其中任一步失败，整个 swarm 就不会进入 registry

## 共享思考图与可调度子图

运行时现在把“执行图”和“思考图”分开处理：

- execution graph 负责节点调度、分支、join、循环和工具调用
- shared thought graph 负责事实、证据、假设、猜测、问题、风险和决策
- agent private workspace 负责 agent 私有草稿和本地思考工件

`core/cognitive.py` 中的思考图节点支持以下核心类型：

- `fact`
- `evidence`
- `hypothesis`
- `guess`
- `claim`
- `question`
- `assumption`
- `decision`
- `risk`
- `counterevidence`
- `tool_result`

关系类型支持：

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

`Core.build_thought_context_export()` 会为 agent prompt 组装三层上下文：

- 主共享图摘要
- 当前 agent 的可调度子图
- 当前 agent 的私有 workspace 摘要

可调度子图由 `CognitiveSubgraphDescriptor` 描述，包含 root nodes、frontier nodes、purpose、visibility、owner agent、expected next information 和状态字段。它不是新的执行图节点，而是给 LLM 使用的语义任务切片。

## 发布链路的内容流与控制流

`writer -> reviewer -> publisher` 链路中，正文和路由控制现在按不同通道处理。

结构化 agent 输出里的 `next_node_id`、`next_node_ids`、`branch` 和 `branches` 仍然用于路由；正文则会被保存进运行时 metadata 的专用字段，例如：

- `draft_report`
- `approved_report`
- `final_report`
- `latest_report`

这避免了 reviewer 这类控制节点在返回 `content = ""` 时把 writer 已生成的正文清空。`approve` verdict 会把当前最新报告提升为 `approved_report`，publisher 会继续收到非空正文。

## 包解析规则

`RuntimeRegistry.resolve_package_path(source)` 支持三种来源写法：

1. 直接传目录路径
2. 传相对 `swarm_root` 的目录名
3. 传 swarm 名称或包目录名

解析顺序是：

1. 如果 `source` 本身是存在的目录，直接使用
2. 再尝试 `swarm_root / source`
3. 最后遍历 `discover_swarm_packages(swarm_root)`，读取每个 manifest，比对：
   - `manifest.swarm_name == source`
   - 或 `package_path.name == source`

如果都找不到，就抛 `NotFoundError("Unable to resolve swarm package: ...")`

这表示：

- 你可以用“包目录名”加载
- 也可以用 manifest 里声明的 `swarm_name` 加载
- 但如果二者不一致，后续 reload 会再做一次一致性校验

## Reload 行为

`RuntimeRegistry.reload_swarm(swarm_name, force=False, source=None)` 是单包重载。

它的逻辑比较谨慎：

1. 先确认目标 swarm 已加载
2. 如果该 swarm 还有 active runs，且 `force=False`，拒绝重载
3. 解析重载来源
4. 读取新的 manifest
5. 检查新 manifest 的 `swarm_name` 必须仍然等于原来的 `swarm_name`
6. 重新构建 `LoadedSwarm`
7. 用新对象覆盖旧对象

### 原子性

这类重载是“先构建成功，再替换旧对象”的风格。也就是说：

- 新包没构建成功时，旧 swarm 还在
- 只有新对象完整构建完成后，才会写回 `self.swarms`

这对运行时安全性比较重要。

### active run 冲突

如果目标 swarm 还有未完成的运行，默认会拒绝重载，并抛：

- `ConflictError("Swarm '<name>' still has active runs; use force=true to reload it.")`

这里的 active run 由 `RunRegistry.active_run_count(swarm_name)` 判断，判定条件是：

- 记录还没 `_done`
- 且 `swarm_name` 匹配

也就是说，完成态的 run 不算 active。

## Unload 行为

`RuntimeRegistry.unload_swarm(swarm_name, force=False)` 负责卸载一个 swarm。

流程是：

1. 找到对应 swarm
2. 检查是否还有 active runs
3. 如果有且 `force=False`，拒绝卸载
4. 从 `self.swarms` 删除该条目

### 冲突处理

默认情况下，只要该 swarm 还有活跃运行，就不会允许卸载，并抛：

- `ConflictError("Swarm '<name>' still has active runs; use force=true to unload it.")`

如果你传 `force=true`，则允许卸载，即使还有 run 记录在跑。

需要注意的是，这里“卸载”只是把 swarm 从 registry 里移除，不会终止已经启动的后台线程或正在执行的 graph。run 仍然由 `RunRegistry` 持有，直到它自然结束。

## 运行态和路由层的关系

`web/routes/swarms.py` 只是把 HTTP 请求转成对 `RuntimeRegistry` 的方法调用。

对应关系大致是：

- `POST /api/swarms/load` -> `load_swarm()`
- `POST /api/swarms/<name>/reload` -> `reload_swarm()`
- `DELETE /api/swarms/<name>` -> `unload_swarm()`
- `GET /api/swarms` / `GET /api/swarms/<name>` -> 读取 `registry.swarms`

所以后端的“开放能力”本质上取决于：

- registry 里是否已经有该 swarm
- 当前是否存在 active runs
- manifest 和 package 路径是否能正确解析

## 你可以把它理解成什么

可以把 `RuntimeRegistry` 理解成一个“只在进程内存在的 swarm 目录”和“只在进程内存在的运行队列”：

- 目录负责：发现、加载、重载、卸载
- 队列负责：记录 run、统计 active run、给 SSE 提供事件流

它的设计偏向于“可热更新，但不自动取消正在跑的东西”。

## 配置范围说明

当前后端配置仍然比较精简，但已经分成两个表：

```toml
[app]
swarm_root = "agents"

[api]
base_url = "/api"
timeout_seconds = 30
sse_reconnect_interval_seconds = 5
auto_reconnect = true
```

### `app` 与 `api` 的分工

- `[app]` 仍然只负责运行时发现 swarm 包
- `[api]` 负责持久化 API 配置，并通过 `/api/settings` 对外读写
- 前端的显示偏好（深色模式、紧凑布局、显示调试信息、语言）仍然保存在浏览器 `localStorage`

这意味着：

- 后端现在会消费并持久化 API 配置
- API 设置改动后会写回 `config.toml`
- 前端显示偏好仍然是浏览器级别的本地设置
- 多设备 / 多浏览器之间仍不会自动同步显示偏好
- `api_base_url` 仍然先由前端本地值启动，再与后端 settings API 同步

### 扩展后端配置时的建议

如果后续需要让后端也支持可配置的超时、重试策略或日志级别，建议：

1. 继续把后端级设置放进 `[api]` 或新增独立表
2. 在 `core/swarm_spec.py` 中扩展对应 dataclass
3. 在 `web/routes/settings.py` 里同步读写接口
4. 在 `web/app_factory.py` 中保持 settings blueprint 注册
5. 必要时将读到的配置注入 `RuntimeRegistry` 或 `Flask.extensions`

当前实现有意保持后端配置最小化，以降低部署复杂度。
