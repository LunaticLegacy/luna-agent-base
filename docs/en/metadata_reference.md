# Metadata Reference

This document summarizes all `metadata` conventions used in the project.

## 1. Graph Node Metadata

Source:

- `core/policy.py`
- `agents/<swarm>/graph.py`

Current semantic fields:

### `route_policy`

- Type: `string`
- Typical values:
  - `"all"`
  - `"first"`
- Meaning:
  - `"all"` means all downstream nodes should run after branching
  - `"first"` or missing means the default first path is used

### `join_node_id`

- Type: `int`
- Meaning:
  - the join node after a parallel branch
  - often used to return from a fork into a review or aggregation node

### Custom fields

Node metadata may include arbitrary extra keys. The frontend should keep unknown keys and render them as raw JSON.

### `runtime_transient`

- Type: `bool`
- Meaning:
  - marks a node as a runtime temporary node
  - lets the runtime treat a deleted temporary agent as an acceptable transitional state until the node itself is removed
  - this is a compatibility field; new code should prefer `node_lifecycle`

### `persistence`

- Type: `string`
- Typical values:
  - `"transient"`
  - `"persistent"`
- Meaning:
  - `transient` means a use-and-discard node
  - `persistent` means a long-lived node that stays until it is explicitly deleted, disabled, replaced, or rolled back

### `lifetime_policy`

- Type: `string`
- Typical values:
  - `"run"`
  - `"session"`
  - `"swarm"`
  - `"manual"`
- Meaning:
  - describes the lifecycle boundary of the node
  - `run` usually means one-shot lifetime
  - `manual` usually means long-lived retention

### `node_lifecycle`

- Type: `object`
- Meaning:
  - structured lifecycle metadata
  - recommended fields:
    - `runtime_transient`
    - `persistence`
    - `lifetime_policy`
  - frontend and debugging tools should prefer this object over the single boolean flag

## 2. Runtime Metadata

Source:

- `core/results.py`
- `core/executor.py`

Current runtime fields:

### `branch_index`

- Type: `int`
- Meaning:
  - branch number used during parallel execution

### `branch_source_node_id`

- Type: `int`
- Meaning:
  - the source node that created the branch

### `metadata_clear`

- Type: `array[string]` or `string`
- Meaning:
  - tells the executor which old control keys to remove from `state.metadata`
  - useful in cleanup flows to remove stale `next_node_id` and `spawned_agent_*` values

## 3. Agent Context Metadata

Source:

- `core/agent.py`

Current fields:

### `last_round`

- Type: `int`
- Meaning:
  - the most recent round number

### `turns`

- Type: `int`
- Meaning:
  - number of messages currently stored in the agent context

## 4. ToolContext Metadata

Source:

- `core/toodefl.py`
- `core/executor.py`

The tool receives a copy of the current execution metadata. It can read it and use it to decide what to do next.

## 5. Skill Metadata

Source:

- `core/skills.py`

Skill contracts are flattened into metadata fields:

### `contract_version`

- Type: `string`
- Meaning:
  - version of the skill contract

### `capability`

- Type: `string`
- Meaning:
  - capability name or responsibility label

### `description`

- Type: `string`
- Meaning:
  - human-readable skill description

### `input_schema`

- Type: `object`
- Meaning:
  - input structure accepted by the skill

### `output_schema`

- Type: `object`
- Meaning:
  - expected output structure

### `requires_tools`

- Type: `array[string]`
- Meaning:
  - tools required to run the skill

### `requires_skills`

- Type: `array[string]`
- Meaning:
  - other skills required by this skill

### `preconditions`

- Type: `array[string]`
- Meaning:
  - preconditions that must hold before execution

### `postconditions`

- Type: `array[string]`
- Meaning:
  - conditions that should hold after execution

### `failure_policy`

- Type: `string`
- Meaning:
  - how the runtime should behave when the skill fails

### `parallelizable`

- Type: `bool`
- Meaning:
  - whether the skill may run in parallel

## 6. Frontend Parsing Advice

- Preserve all raw metadata
- Do not discard unknown fields
- Treat `route_policy` and `join_node_id` as semantic enrichments
- Treat `branch_index` and `branch_source_node_id` as runtime grouping information
- Render skill metadata in a details panel
- Use `edges` for structural links and `metadata` for semantic hints
