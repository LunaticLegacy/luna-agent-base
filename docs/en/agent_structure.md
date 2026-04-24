# Agent Structure

This document summarizes the structure of `agents/` swarm packages and the current `deepseek_demo` package.

## 1. Overall Layers

The agent-related structure has four layers:

- `core/`: runtime and orchestration kernel
- `agents/`: business swarm packages
- `tools/`: default runtime tools
- `web/`: HTTP access layer

## 2. Swarm Package Layout

The current `agents/deepseek_demo/` package contains:

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

### `swarm.toml`

The index file declares:

- `graph_file`
- `agent_files`
- `skill_files`
- `tool_files`
- default LLM backend configuration

### `agents/*.py`

Each agent file defines an `AGENT` dictionary only, such as:

- `agent_id`
- `name`
- `skill_name`
- `backend_name`

These files are agent blueprints, not behavior implementations.

### `skills/*.prompt.md` and `skills/*.prompt.toml`

The skill is split into two parts:

- `*.prompt.md`: plain prompt text
- `*.prompt.toml`: contract metadata, including inputs, outputs, dependencies, preconditions, and postconditions

## 3. Current Demo Roles

### `planner`

- reads the user request
- generates a structured control plan
- identifies tasks that can run in parallel
- serves as the branch source

### `researcher`

- gathers evidence, assumptions, and risks
- supports the writer and reviewer
- focuses on information collection

### `writer`

- turns planning and research into a draft
- focuses on content generation

### `reviewer`

- reviews the draft and the branch outputs
- decides whether to continue, rewrite, or publish
- emits graph-edit instructions

### `publisher`

- produces the final user-facing text
- hides internal routing details

## 4. Current Working Graph

The demo graph is a "parallel + merge + review + dynamic edit + publish" flow.

### Main flow

1. `planner`
2. parallel branch to:
   - `researcher`
   - `writer`
3. merge into `reviewer`
4. `reviewer` uses `graph_editor`
5. `publisher`
6. `file_writer`

### Key points

- `route_policy = "all"` enables the parallel branch
- `join_node_id = 4` merges the branch results back into `reviewer`
- `graph_editor` lets the swarm edit the live graph during execution
- transient nodes are marked with `runtime_transient = true`
- persistent nodes should be marked with `persistence = "persistent"` and retained as long-lived swarm structure
- `file_writer` writes the final output to `outputs/deepseek_demo_final.txt`

## 5. Default Tools

The demo currently depends on:

- `echo`
- `file_writer`
- `graph_editor`

### `graph_editor`

The most important runtime tool in the demo. It can:

- add nodes
- remove nodes
- add edges
- remove edges
- replace a node's next hop
- set the entry node
- set the exit node

This means the graph in the file is only the initial graph; runtime execution can keep evolving it.

Newly created nodes now have explicit lifecycle semantics:

- `transient`: use-and-discard runtime nodes
- `persistent`: long-lived nodes that remain until they are explicitly removed, disabled, or replaced

The runtime also records structured `node_lifecycle` metadata:

- `runtime_transient`
- `persistence`
- `lifetime_policy`

By default, newly inserted nodes are transient unless the mutation explicitly marks them as persistent.

### `file_writer`

Writes the result to disk.

## 6. Skill Contract Purpose

The skill contract turns a prompt file into a verifiable capability description.

It currently includes:

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

## 7. Design Position

Current conceptual mapping:

- `agent` is an execution role
- `skill` is a capability contract plus prompt asset
- `graph` is the orchestration structure
- `tool` is a runtime capability extension
- `core` is the runtime interpreter

## 8. Future Direction

Future improvements may include:

- a dedicated router node
- explicit aggregation nodes
- stricter skill contract validation
- tool classification and permissions
- more detailed graph-edit audit logs
