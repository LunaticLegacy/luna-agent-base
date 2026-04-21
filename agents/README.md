# Swarm 包结构说明

`agents/` 下的每个子目录都是一个独立的 swarm 包。

示例：

```text
agents/
  deepseek_demo/
    swarm.toml
    graph.py
    agents/
      planner.py
    skills/
      planner.prompt.md
```

顶层 `tools/` 目录存放可复用的默认工具。

## 约束规则

- 每个 swarm 包目录中只能有一个 `*.toml` 清单文件。
- 清单必须定义 `graph_file`。
- 清单必须定义一个或多个 `agent_files`。
- 清单可以定义 `skill_files` 和 `tool_files`。

## `swarm.toml` 示例

```toml
[swarm]
name = "deepseek_demo"
graph_file = "graph.py"
agent_files = ["agents/planner.py"]
skill_files = ["skills/planner.prompt.md"]
tool_files = ["tools.echo_tool", "tools.file_writer_tool"]

[llm.default]
name = "deepseek"
provider = "openai"
api_url = "https://api.deepseek.com"
api_key = "YOUR_DEEPSEEK_API_KEY"
model = "deepseek-reasoner"
```

## Agent 文件

每个 agent 文件应导出一个映射，例如：

- `AGENT`
- `AGENT_SPEC`
- `AGENTS`

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

## Skill 文件

每个 skill 文件可以是：

- `.md` 或 `.txt` 的提示词内容
- 带有 `[skill]` 表的 `.toml` 文件

## Tool 模块

每个 tool 模块应导出以下之一：

- `TOOL`
- `TOOLS`

如果某个 tool 依赖额外的第三方包，可以在它旁边放一个 `tool_requirements.txt` 文件，运行时会先安装这些依赖再加载该 tool。
