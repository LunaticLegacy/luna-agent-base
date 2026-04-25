# Dynamic Graph Editing Protocol

This document summarizes how the current dynamic graph editing mechanism works, what is wrong with it today, and what needs to be fixed first.

## 1. Protocol Goal

The goal of the dynamic graph editing protocol is to let the swarm evolve its **Agent graph** at runtime while recording execution separately in an **execution trace graph**:

- create temporary or persistent agent nodes
- insert new agents into the live graph
- change next-hop relationships at runtime
- delete, disable, or archive agent nodes
- record every mutation into `runtime_info`

In other words, the file-based `graph.py` is only the initial Agent graph; the Agent graph may keep evolving during runtime. Tools are no longer graph nodes. They are called orthogonally by agents at runtime.

## 2. Current Execution Mechanism

### 2.1 Planner emits a control plan

The `planner` node emits a structured control payload, usually containing:

- `content`
- `spawn`
- `graph_edit`
- `cleanup`

Where:

- `content` carries the substantive draft or research conclusion
- `spawn` creates a temporary agent
- `graph_edit` mutates the live graph
- `cleanup` removes the temporary agent and temporary node

### 2.2 AgentNode parses structured output

`GraphExecutor` tries to parse the agent's `assistant_message` as JSON.

If parsing succeeds:

- `metadata_patch` is merged into `state.metadata`
- `metadata_clear` removes selected keys from `state.metadata`
- `content` becomes the next payload
- `next_node_id` may be extracted as a next-hop override

### 2.3 ToolNode receives ToolContext

Tool nodes receive:

- `core`
- `graph`
- `rounds`
- `metadata`

So a tool may:

- read runtime state
- mutate the live graph
- mutate the agent registry
- write runtime_info records

### 2.4 Next-hop resolution priority

The current executor resolves the next hop in this order:

1. `next_node_override`
2. `payload.next_node_ids`
3. `payload.branch`
4. `payload.branches`
5. `graph.outgoing_edges(node.node_id)`
6. `node.next_node_ids`

That means any tool or agent that returns `next_node_id` effectively gets scheduling priority. The current implementation now narrows `graph_editor`: graph edits do not return `next_node_id` by default; only insertion actions with `route_after_mutation: true` may return the newly inserted node as the next hop.

### 2.5 runtime_info recording

`Core.record_runtime_change(...)` writes mutations to:

- `agents/<swarm>/runtime_info/current.json`
- `agents/<swarm>/runtime_info/events.jsonl`

This makes graph edits, agent edits, and tool registration changes traceable.

## 3. Known Problems

### 3.1 `next_node_id` semantic pollution

This is the biggest issue.

- `agent_manager` and older `graph_editor` behavior have returned `next_node_id`
- the executor trusts that value first
- this lets tools hijack scheduling

For dynamic graph editing, this is dangerous because the executor may jump to:

- a node that has not been inserted yet
- a node that has already been deleted
- a node that should not be executed yet

Current fix:

- `agent_manager` does not return top-level `next_node_id`
- `graph_editor` does not write `next_node_id` into `metadata_patch`
- `graph_editor` does not route to inserted nodes by default
- only `add_agent_node` / `add_tool_node` with `route_after_mutation: true` may return top-level `next_node_id`
- non-insertion actions reject `route_after_mutation` before mutating the graph

### 3.2 Control plane and data plane are mixed

`content` is the data flow, while `spawn` / `graph_edit` / `cleanup` are the control flow.  
They currently travel in the same runtime state, which makes it easy for later tools to inherit stale control information.

### 3.3 Deletion does not fully clear old control data

After deleting a temporary node, the old `next_node_id` may still remain in metadata.  
That can make the executor jump back to a deleted node.

### 3.4 Graph mutation is not atomic

Insertion, rewiring, next-hop resolution, and runtime-info recording are currently separate steps rather than one transaction.  
If one step diverges from the next hop, the runtime becomes inconsistent.

### 3.5 Node IDs are assigned by upstream protocol

Temporary node IDs depend on planner or tool-provided values.  
If the planner, tool, and graph editor disagree on node IDs, collisions happen:

- jumping to nonexistent nodes
- overwriting old nodes
- deleting the wrong node
- orphaned edges

Current fix:

- `graph_editor` `add_agent_node` / `add_tool_node` may omit `node_id`, or pass `node_id: "auto"`
- automatic IDs use the next available integer in the current graph
- manually supplied IDs are rejected by default if they already exist
- replacement only happens with explicit `replace_existing: true`

### 3.6 `replace_existing` is too strong

Deleting the old node and inserting a new one without automatically reconnecting neighbors can break the graph.

Current fix:

- `replace_existing` still requires an explicit opt-in
- replacement preserves incoming edges
- if no new `next_node_ids` are supplied, the replacement inherits outgoing edges
- if the old node was entry / exit, entry / exit is restored to the replacement

### 3.7 No forced consistency check after mutation

A graph can still be structurally valid before mutation but unsafe after mutation.  
`GraphTransaction.prepare()` now applies the mutation to a working graph and immediately runs `graph.validate(core)`; invalid mutations are rejected before touching the live graph.

### 3.8 Temporary nodes do not have an explicit lifecycle marker

Dynamic insertions need a clear runtime marker such as `runtime_transient` so the runtime can distinguish a safe transitional state from real graph corruption when a temporary agent has already been deleted but its node has not yet been removed.

### 3.9 Newly inserted nodes should support transient and persistent lifecycles

The current protocol focuses on temporary nodes, but a self-evolving swarm also needs to absorb long-lived capabilities.

Recommended lifecycle classes:

- `transient`: use-and-discard, and should be the default
- `persistent`: long-lived and retained until explicitly deleted, disabled, replaced, or rolled back

Recommended structured metadata:

- `runtime_transient`
- `persistence`
- `lifetime_policy`

Where:

- `runtime_transient = true` means a transient node
- `persistence = "persistent"` means a long-lived node
- `lifetime_policy` describes the boundary, e.g. `run`, `session`, `swarm`, `manual`

### 3.10 Agent lifecycle and node lifecycle are not tightly bound

You can end up with:

- an agent created while the node is not yet inserted
- a node deleted while the agent still exists
- a node remaining in the graph after the agent is gone

### 3.11 Branch / join semantics can break after mutation

If a branch target or join target is deleted during runtime, the executor may still try to continue using the old path.

### 3.12 runtime_info is audit data, not scheduling safety

It tells you what happened, but it does not guarantee the next hop is safe.  
So it is traceability, not execution protection.

## 4. Fix Priority

Recommended fix order:

1. Done: create / delete tools do not return `next_node_id` by default
2. Done: only insertion actions with explicit `route_after_mutation` may decide jumps
3. Done: each mutation goes through `GraphTransaction.prepare()` validation
4. Done: deletion clears stale `next_node_id` / `spawned_agent_*` / `deleted_agent_*` metadata
5. Done: dynamic nodes support `node_id: "auto"`, and manual ID collisions are rejected by default
6. Still pending: upgrade `runtime_info` from audit logging to post-mutation verification support

## 5. Summary

The current protocol is:

- the agent emits a structured control plan
- tools mutate the runtime agent / graph state
- the executor continues based on the next hop
- runtime_info records every mutation

It is already a usable prototype, but it is not yet safe enough for arbitrary runtime graph edits.  
The next step is to separate control flow, data flow, and graph mutation responsibilities much more cleanly.
