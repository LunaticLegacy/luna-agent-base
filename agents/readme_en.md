# Swarm Package Layout

Each child directory under `agents/` is a standalone swarm package.

Example:

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

Default reusable tools live in the top-level `tools/` package.

Required manifest rules:

- Exactly one `*.toml` file must exist in the package directory.
- The manifest must define one `graph_file`.
- The manifest must define one or more `agent_files`.
- The manifest may define `skill_files` and `tool_files`.

Suggested `swarm.toml` shape:

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

Each agent file should export one mapping:

- `AGENT`
- `AGENT_SPEC`
- `AGENTS`

Supported agent fields:

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

Each skill file may be:

- `.md` or `.txt` prompt content
- `.toml` with a `[skill]` table

Each tool module should export one of:

- `TOOL`
- `TOOLS`

If a tool needs extra third-party dependencies, place a `tool_requirements.txt` file next to that tool module. The runtime will preinstall those requirements before loading the tool.
