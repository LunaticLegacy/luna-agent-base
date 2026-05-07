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
    apis/
      metrics_api.py
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
- `apis/*`: package-specific API modules, or `native:` imports that point to framework-native APIs

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
6. Load API modules
7. Load agent blueprints
8. Attach the execution graph

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
- `api_files`: list of API modules. By default entries are resolved as package-local files; use `native:module.path` to reference a framework-native API
- `default_backend`: default backend name

Notes:

- `graph_file` and `agent_files` are required
- `skill_files`, `tool_files`, and `api_files` are optional
- `default_backend` is most useful when multiple backends exist

Note:

- `llm.default` no longer needs a `name` field; the runtime derives the backend identifier from the swarm/package name

## Workspace Configuration

`workspace` should live in `swarm.toml` as a swarm-level policy for filesystem access.

Common fields:

- `default_mode`: default workspace mode, either `workspace` or `full_access`
- `default_root`: default workspace root, resolved relative to the current swarm's `workspace/` directory
- `agents.<agent_id>.mode`: per-agent mode override
- `agents.<agent_id>.root`: per-agent root override

Recommended usage:

- most agents should use `workspace`
- only trusted system agents should use `full_access`
- file tools such as `file_writer` should enforce this boundary

## Global Variables Configuration

`globals` is a swarm-level config block for framework-managed variables that selected agents can read at runtime.

Common use cases:

- project-wide constants shared by multiple nodes
- runtime flags that should be injected into prompts
- configuration that should live inside the framework instead of environment variables

Example:

```toml
[globals]
project_name = "angelus"
release_channel = "beta"

[globals.visibility]
release_channel = ["orchestrator", "planner", "reviewer"]
```

Rules:

- Keys under `[globals]` define variable values
- `[globals.visibility]` restricts which agents can see a given variable
- If a variable is not listed in `visibility`, it is visible to all agents in the swarm
- Visible variables are injected into the agent runtime prompt

Recommended usage:

- stable constants, project name, execution mode, feature flags, release tags
- avoid storing secrets here; secrets should still use environment variables or a stricter secret mechanism

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
- `tools`

Recommended usage:

- `agent_id` should be stable and unique
- `character_prompt` is for role, responsibility, and working style
- `skill_name` / `prompt_file` / `prompt_text` define where the prompt contract comes from
- `tools` declares the tools this agent may use
- workspace boundaries should be declared in `swarm.toml`, not in agent Python files

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

## API Modules

Each API module is imported during swarm loading and registered in the runtime API registry. API sources are split into two classes:

- `package`: API modules declared by the swarm package
- `native`: framework-native APIs referenced explicitly with a `native:` prefix

Example `swarm.toml` snippet:

```toml
[swarm]
api_files = ["apis/metrics_api.py", "native:web.routes.health"]
```

Recommendations:

- keep package APIs under `apis/` so they stay visually distinct from tools and prompts
- if an API needs extra third-party dependencies, place an `api_requirements.txt` file next to it
- if you are unsure whether a capability is a tool or an API, prefer a tool first; APIs are best for framework-level imports and registrations

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
