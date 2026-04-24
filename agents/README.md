# Swarm 包结构说明

`agents/` 是 swarm root。`config.toml` 里的 `[app].swarm_root` 会告诉 runtime 去哪里扫描这些包。

`agents/` 下的每个子目录都是一个独立的 swarm 包，包内通常包含：

```text
agents/
  deepseek_demo/
    swarm.toml
    graph.py
    agents/
      planner.py
      reviewer.py
    skills/
      planner.prompt.md
    apis/
      metrics_api.py
    tools/
      echo_tool.py
      tool_requirements.txt
```

## 包职责

一个 swarm 包负责描述一套完整的执行单元：

- `swarm.toml`：包清单，声明图、Agent、Skill、Tool 和默认后端
- `graph.py`：执行图定义
- `agents/*.py`：Agent 蓝图定义
- `skills/*`：可复用的角色提示词或 skill contract
- `tools/*`：包内专用工具模块
- `apis/*`：包内专用 API 模块，或通过 `native:` 前缀显式引用原生 API

顶层 `tools/` 目录则存放可被多个 swarm 复用的默认工具。

## 加载规则

- 每个 swarm 包目录中只能有一个 `*.toml` 清单文件
- 清单必须定义 `graph_file`
- 清单必须定义一个或多个 `agent_files`
- 清单可以定义 `skill_files` 和 `tool_files`
- 清单所在目录名可以和 `swarm.name` 不同，但如果两者都存在，最好保持一致，便于排查

加载时，runtime 会按以下顺序处理一个包：

1. 读取并校验 `swarm.toml`
2. 加载 skill 资源
3. 构建核心 `Core`
4. 注册 LLM backend
5. 加载 tool 模块
6. 加载 API 模块
7. 加载 Agent blueprints
8. 绑定 execution graph

这意味着：

- tool 必须在 agent 执行前可导入
- graph 是最后绑定到 core 的
- 任何一个步骤失败，这个 swarm 就不会进入运行时 registry

## `swarm.toml` 示例

```toml
[swarm]
name = "deepseek_demo"
graph_file = "graph.py"
agent_files = ["agents/planner.py", "agents/reviewer.py"]
skill_files = ["skills/planner.prompt.md", "skills/reviewer.prompt.md"]
    tool_files = ["tools.echo_tool", "tools.file_writer_tool"]
    api_files = ["apis/metrics_api.py"]
default_backend = "deepseek"

[workspace]
default_mode = "workspace"
default_root = "."

[globals]
project_name = "angelus"
release_channel = "beta"

[globals.visibility]
release_channel = ["orchestrator", "planner", "reviewer"]

[llm.default]
name = "deepseek"
provider = "openai"
api_url = "https://api.deepseek.com"
api_key = "YOUR_DEEPSEEK_API_KEY"
model = "deepseek-reasoner"
```

## `[swarm]` 字段

常见字段如下：

- `name`：swarm 名称
- `graph_file`：执行图入口文件
- `agent_files`：Agent 定义文件列表
- `skill_files`：Skill 文件列表
- `tool_files`：Tool 模块列表
- `api_files`：API 模块列表，默认按包内文件解析；如果需要引用框架原生 API，可以写成 `native:module.path`
- `default_backend`：默认使用的 backend 名称

其中：

- `graph_file` 和 `agent_files` 是必需的
- `skill_files`、`tool_files` 和 `api_files` 是可选的
- `default_backend` 只在你有多个 backend 时特别有用

## Workspace 配置

`workspace` 建议作为 swarm 级配置写在 `swarm.toml` 里，用来定义 agent 的文件访问边界。

常见字段如下：

- `default_mode`：默认工作空间模式，支持 `workspace` 和 `full_access`
- `default_root`：默认工作空间根目录，相对当前 swarm 的 `workspace/` 目录解析
- `agents.<agent_id>.mode`：某个 agent 的单独模式覆盖
- `agents.<agent_id>.root`：某个 agent 的单独根目录覆盖

推荐用法：

- 大多数 agent 使用 `workspace`
- 只有明确可信的系统 agent 才使用 `full_access`
- `file_writer` 等文件工具会根据这个配置限制写入路径

## Global Variables 配置

`globals` 用来给部分 agent 注入框架级全局变量。它更适合放那些：

- 需要在多个节点间共享的固定配置
- 需要被 agent 读入 prompt 的项目级常量
- 不适合放进环境变量、但又需要在 swarm 内显式配置的值

常见写法如下：

```toml
[globals]
project_name = "angelus"
release_channel = "beta"

[globals.visibility]
release_channel = ["orchestrator", "planner", "reviewer"]
```

规则如下：

- `[globals]` 里的键值会作为全局变量值
- `[globals.visibility]` 用来限制某个变量只对哪些 agent 可见
- 如果某个变量没有出现在 `visibility` 里，它默认对该 swarm 内所有 agent 可见
- 运行时会把允许可见的变量注入到 agent prompt 中

建议：

- 放配置常量、项目名、目标模式、开关、稳定版本号
- 不要放敏感 secret；敏感信息仍然应该走环境变量或更严格的 secret 方案

## Agent 文件

每个 agent 文件应导出一个映射，支持三种入口：

- `AGENT`
- `AGENT_SPEC`
- `AGENTS`

它们的区别是：

- `AGENT`：单个 Agent 定义
- `AGENT_SPEC`：与 `AGENT` 等价的单个定义
- `AGENTS`：多个 Agent 定义组成的列表

支持的字段包括：

- `agent_id`
- `name`
- `character_prompt`
- `skill_name`
- `prompt_file`
- `prompt_text`
- `backend_name`
- `api_url`
- `api_key`
- `model`
- `provider`
- `tools`

建议：

- `agent_id` 必须稳定且唯一
- `character_prompt` 适合写角色人格、职责边界和工作风格
- `skill_name` / `prompt_file` / `prompt_text` 用来指定角色提示词来源
- `tools` 用来声明这个 Agent 可以调用哪些工具
- 工作空间边界应写在 `swarm.toml` 的 `[workspace]` 里，而不是写进 agent Python 文件

## Skill 文件

每个 skill 文件可以是：

- `.md` 或 `.txt` 的提示词内容
- 带有 `[skill]` 表的 `.toml` 文件

建议把 skill 设计成“可复用的能力片段”：

- 适合放角色约束、输入输出要求、前置条件、后置条件
- 不适合放过多和具体包耦合的实现细节

## Tool 模块

每个 tool 模块应导出以下之一：

- `TOOL`
- `TOOLS`

如果某个 tool 依赖额外的第三方包，可以在它旁边放一个 `tool_requirements.txt` 文件，运行时会先安装这些依赖再加载该 tool。

### Tool 的放置方式

Tool 可以放在两类位置：

- swarm 包内：只给当前包使用
- 顶层 `tools/`：给多个 swarm 复用

如果你不确定要放哪里，优先放到包内，等多个 swarm 都需要再提升到顶层。

## API 模块

每个 API 模块会在加载 swarm 时同步导入，并注册到 runtime 的 API registry 中。API 的来源会被区分为两类：

- `package`：swarm 包内声明的 API
- `native`：框架原生 API，使用 `native:` 前缀显式引用

`swarm.toml` 示例：

```toml
[swarm]
api_files = ["apis/metrics_api.py", "native:web.routes.health"]
```

建议：

- 包内 API 放在 `apis/` 目录，便于和工具、角色提示词分层
- 如果 API 依赖额外第三方包，可以在 API 模块旁边放一个 `api_requirements.txt`
- 如果你不确定某个能力更像 tool 还是 API，优先把它做成 tool；API 更适合框架级导入和注册

## 常见坑

- 目录里放了多个 `.toml` 文件
- `agent_files` 指向了不存在的文件
- `graph_file` 写了但文件实际不在包内
- agent 里忘了导出 `AGENT` / `AGENT_SPEC` / `AGENTS`
- tool 依赖没写 `tool_requirements.txt`
- manifest 名称和目录名不一致，导致后续 reload 时不好排查

## 一个简单判断标准

如果你在写一个 swarm 包，可以这样检查自己：

- 这个目录能不能单独被 runtime 发现
- `swarm.toml` 能不能完整描述这个包
- Agent 是否只负责角色和调用边界
- Skill 是否只负责提示词契约
- Tool 是否只负责可执行能力
- Graph 是否只负责节点和流转

如果这些边界清楚，这个包通常就比较好维护。
