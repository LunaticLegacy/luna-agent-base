# Swarm Package Layout

`agents/` is the swarm root. The `[app].swarm_root` field in the top-level `config.toml` tells the runtime where to scan for packages.

Each child directory under `agents/` is a standalone swarm package. A package usually contains:

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
    tools/
      echo_tool.py
      tool_requirements.txt
```

## Package Responsibilities

One swarm package describes a complete execution unit:

- `swarm.toml`: package manifest, declaring graph, agents, skills, tools, and defaults
- `graph.py`: execution graph definition
- `agents/*.py`: agent blueprint definitions
- `skills/*`: reusable prompt assets or skill contracts
- `tools/*`: package-specific tool modules

Default reusable tools live in the top-level `tools/` package.

## Loading Rules

- Exactly one `*.toml` file must exist in the package directory
- The manifest must define `graph_file`
- The manifest must define one or more `agent_files`
- The manifest may define `skill_files` and `tool_files`
- The package directory name may differ from `swarm.name`, but keeping them aligned makes debugging easier

The runtime loads a package in this order:

1. Parse and validate `swarm.toml`
2. Load skill assets
3. Build the core `Core`
4. Register LLM backends
5. Load tool modules
6. Load agent blueprints
7. Attach the execution graph

This means:

- tools must be importable before an agent can execute them
- the graph is bound last
- if any step fails, the swarm never enters the runtime registry

## Example `swarm.toml`

```toml
[swarm]
name = "deepseek_demo"
graph_file = "graph.py"
agent_files = ["agents/planner.py", "agents/reviewer.py"]
skill_files = ["skills/planner.prompt.md", "skills/reviewer.prompt.md"]
tool_files = ["tools.echo_tool", "tools.file_writer_tool"]
default_backend = "deepseek"

[llm.default]
name = "deepseek"
provider = "openai"
api_url = "https://api.deepseek.com"
api_key = "YOUR_DEEPSEEK_API_KEY"
model = "deepseek-reasoner"
```

## `[swarm]` Fields

Common fields:

- `name`: swarm name
- `graph_file`: execution graph entry file
- `agent_files`: list of agent definition files
- `skill_files`: list of skill files
- `tool_files`: list of tool modules
- `default_backend`: default backend name

Notes:

- `graph_file` and `agent_files` are required
- `skill_files` and `tool_files` are optional
- `default_backend` is most useful when multiple backends exist

## Agent Files

Each agent file should export one mapping, using one of:

- `AGENT`
- `AGENT_SPEC`
- `AGENTS`

Differences:

- `AGENT`: single agent definition
- `AGENT_SPEC`: same intent as `AGENT`
- `AGENTS`: list of agent definitions

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
- `workspace_mode`
- `workspace_root`
- `tools`

Recommended usage:

- `agent_id` should be stable and unique
- `character_prompt` is for role, responsibility, and working style
- `skill_name` / `prompt_file` / `prompt_text` define where the prompt contract comes from
- `workspace_mode` declares whether the agent is restricted to its workspace or allowed `full_access`
- `workspace_root` sets the workspace root, usually as a path relative to the repository root
- `tools` declares the tools this agent may use

## Skill Files

Each skill file may be:

- `.md` or `.txt` prompt content
- `.toml` with a `[skill]` table

Skills work best as reusable capability fragments:

- good for role constraints, input/output requirements, preconditions, and postconditions
- not ideal for package-specific implementation details

## Tool Modules

Each tool module should export one of:

- `TOOL`
- `TOOLS`

If a tool needs extra third-party dependencies, place a `tool_requirements.txt` file next to that tool module. The runtime will preinstall those requirements before loading the tool.

### Where to put tools

Tools can live in either location:

- inside a swarm package, if they are package-specific
- in the top-level `tools/` package, if multiple swarms reuse them

If you are unsure, keep the tool inside the package first and promote it later when reuse becomes obvious.

## Common Pitfalls

- More than one `.toml` file in the package directory
- `agent_files` pointing to missing files
- `graph_file` listed in the manifest but not actually present
- forgetting to export `AGENT` / `AGENT_SPEC` / `AGENTS`
- missing `tool_requirements.txt` for tool dependencies
- name mismatches between directory name and `swarm.name`, which make reload/debugging harder

## A Simple Sanity Check

When you author a swarm package, ask:

- can runtime discover this directory on its own?
- does `swarm.toml` fully describe the package?
- does the agent stay focused on role and boundaries?
- does the skill stay focused on prompt contract?
- does the tool stay focused on executable capability?
- does the graph stay focused on nodes and transitions?

If those boundaries are clear, the package is usually easy to maintain.
