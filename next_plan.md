# Next Plan

This file is an implementation checklist for the next concrete feature. Keep it version-clean and do not mix older planning threads into it.

## Baseline

- `config.toml` already persists API runtime settings under `[api]`.
- The frontend Settings page already uses a mixed model:
  - API settings go through the backend settings API.
  - UI preferences stay in browser `localStorage`.
- `docs_verifier` has already been migrated to:
  - `provider = "litellm"`
  - `name = "kimi"`
  - Moonshot / Kimi Code API
  - environment-variable based API key resolution

## Implementation Checklist: Agent Workspace Access

### 1. Define the access model

- [ ] Add a filesystem access mode field to agent blueprints.
- [ ] Support exactly these modes:
  - [ ] `workspace`
  - [ ] `full_access`
- [ ] Make `workspace` the default mode.
- [ ] Decide whether `workspace_root` is mandatory for `workspace` mode.
- [ ] Document the intended meaning of both modes in the code comments or docs.

### 2. Extend the agent schema

Target file:

- [ ] [`core/swarm_spec.py`](/run/media/luna/数据和游戏/Codes/Python/angelus/core/swarm_spec.py)

Checklist:

- [ ] Add `workspace_mode` to `AgentBlueprint`.
- [ ] Add `workspace_root` to `AgentBlueprint`.
- [ ] Parse the new fields in `_coerce_agent_blueprint()`.
- [ ] Validate `workspace_mode` values and reject unknown modes.
- [ ] Decide what happens when `workspace_mode = "workspace"` but `workspace_root` is missing.
- [ ] Keep the current agent loading behavior unchanged for agents that do not declare the new fields yet.

### 3. Thread workspace data into runtime

Target files:

- [ ] [`core/core.py`](/run/media/luna/数据和游戏/Codes/Python/angelus/core/core.py)
- [ ] [`core/agent.py`](/run/media/luna/数据和游戏/Codes/Python/angelus/core/agent.py)
- [ ] [`core/toodefl.py`](/run/media/luna/数据和游戏/Codes/Python/angelus/core/toodefl.py)

Checklist:

- [ ] Extend `ToolContext` with filesystem scope metadata.
- [ ] Include the current agent workspace root in `ToolContext`.
- [ ] Include the current access mode in `ToolContext`.
- [ ] Pass the workspace info into agent creation or agent metadata.
- [ ] Make the runtime able to tell whether a tool call is `workspace`-scoped or `full_access`.

### 4. Enforce access in file tools

Target files:

- [ ] [`tools/file_writer_tool.py`](/run/media/luna/数据和游戏/Codes/Python/angelus/tools/file_writer_tool.py)
- [ ] Future file-reading tools

Checklist:

- [ ] Add path normalization before any write.
- [ ] Refuse writes outside the permitted workspace when in `workspace` mode.
- [ ] Allow broader writes only when the agent is explicitly in `full_access` mode.
- [ ] Return a clear error message when a path violates the allowed scope.
- [ ] Add the same access checks to any future file reader tool.
- [ ] Keep tool behavior unchanged for agents that already run with full project access.

### 5. Decide the workspace directory convention

Checklist:

- [ ] Pick one canonical workspace root layout.
- [ ] Prefer a per-swarm or per-agent directory structure.
- [ ] Make the chosen layout easy to audit and easy to clean up.
- [ ] Ensure the layout does not collide with existing swarm package files.
- [ ] Decide whether `workspace_root` is relative to the swarm package or to the repository root.

Suggested shape:

```text
agents/<swarm_name>/workspace/<agent_id>/
```

### 6. Update swarm manifests

Target files:

- [ ] [`agents/docs_verifier/swarm.toml`](/run/media/luna/数据和游戏/Codes/Python/angelus/agents/docs_verifier/swarm.toml)
- [ ] [`agents/deepseek_demo/swarm.toml`](/run/media/luna/数据和游戏/Codes/Python/angelus/agents/deepseek_demo/swarm.toml)
- [ ] Other swarm manifests that should opt in later

Checklist:

- [ ] Add `workspace_mode = "workspace"` to agents that should be sandboxed.
- [ ] Add `workspace_root` where needed.
- [ ] Leave trusted system agents on `full_access` only when necessary.
- [ ] Keep current backend names and model routing unchanged while adding workspace metadata.

### 7. Update agent files

Target files:

- [ ] `agents/*/agents/*.py`

Checklist:

- [ ] Add workspace fields to agent definitions.
- [ ] Keep the existing `AGENT` / `AGENT_SPEC` / `AGENTS` format intact.
- [ ] Avoid changing unrelated prompt or backend configuration while wiring workspace access.

### 8. Add tests

Target files:

- [ ] Existing runtime tests
- [ ] New tests under `tests/`

Checklist:

- [ ] Verify `workspace` mode blocks writes outside the allowed root.
- [ ] Verify `full_access` mode still permits normal writes.
- [ ] Verify invalid `workspace_mode` values are rejected at load time.
- [ ] Verify missing `workspace_root` is handled according to the chosen rule.
- [ ] Verify the new fields survive a normal swarm load cycle.

### 9. Update docs

Target files:

- [ ] [`agents/README.md`](/run/media/luna/数据和游戏/Codes/Python/angelus/agents/README.md)
- [ ] [`agents/readme_en.md`](/run/media/luna/数据和游戏/Codes/Python/angelus/agents/readme_en.md)
- [ ] [`docs/backend/runtime.md`](/run/media/luna/数据和游戏/Codes/Python/angelus/docs/backend/runtime.md)

Checklist:

- [ ] Explain what `workspace` means.
- [ ] Explain what `full_access` means.
- [ ] Explain where workspace roots come from.
- [ ] Explain which tools enforce the boundary.
- [ ] Make clear that this is an agent access model, not an LLM backend setting.

## Secondary Phase: Context Graph System

Keep `plan/pending/context_graph_system.md` as a later-stage memory improvement.

### When to revisit

- [ ] After workspace access is stable.
- [ ] After file tools enforce access boundaries.
- [ ] After the workspace directory convention is settled.

### Why it stays later

- [ ] It improves reasoning and retrieval quality, not safety boundaries.
- [ ] It is not required to implement the workspace model.
- [ ] The project already has a cognitive-graph base, so this can be layered on later.

## Done Criteria

The checklist is complete when:

- [ ] Agents can declare `workspace` or `full_access`.
- [ ] Runtime passes that information into tools.
- [ ] File tools enforce the declared boundary.
- [ ] Tests prove the boundary works.
- [ ] Docs match the implementation.

