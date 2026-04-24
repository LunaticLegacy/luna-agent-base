# Next Plan

This file is the current implementation plan. It intentionally replaces the
previous thought-graph completion checklist with the workflow hardening thread.

## Status

- Planning completed and the core hardening batch is implemented.
- Detailed repair plan is documented in `docs/backend/workflow-hardening.md`.
- Remaining work is concentrated in frontend exposure for auth/CORS and the
  finer split between runtime-only graph edits and persistent graph commits.
- Existing dirty runtime artifacts under `agents/*/runtime_info/` should be
  treated as generated state unless explicitly committed.

## Goal

Harden the current swarm workflow so it is safe against:

- cross-run context pollution
- unauthenticated management API use
- arbitrary swarm package loading
- path traversal from manifests
- unrestricted tool capability use
- graph mutation persistence hazards
- unsafe file writes
- publisher output contract mismatch
- metadata control leakage
- sensitive runtime-info persistence
- brittle test discovery

## Current Highest-Risk Findings

### 1. Private Workspace Pollution

Private agent artifacts are stored under `.angelus_private/<agent_id>/` and are
injected into future prompts. `reset_runtime_state()` does not clear them.

Required fix:

- make private workspace data run-scoped
- inject only the current run's private artifacts by default
- treat durable memory as explicit opt-in state

### 2. Unauthenticated High-Risk API

Management routes can load/reload/unload swarms, start runs, update settings,
write content, and call agents without authentication.

Required fix:

- add API token auth for mutating/high-risk routes
- narrow CORS
- keep only health/readiness public by default

### 3. Unsafe Swarm Loading

`load_swarm` can resolve arbitrary existing directories and execute Python files
from manifests. Manifest path fields are not consistently constrained to the
package root.

Required fix:

- restrict package loading to `swarm_root`
- canonicalize and validate all manifest paths
- remove arbitrary installed-module import fallback for tools
- disable automatic dependency installation during normal runtime loading

### 4. Tool Capability Gaps

`agent_manager`, `graph_editor`, and `file_writer` are high-risk tools. Current
checks are mostly tool-local and configuration-driven.

Required fix:

- introduce central tool capability policy
- gate graph mutation, agent lifecycle, file write, network, and config write
- prevent spawned agents from escalating workspace or tool permissions

### 5. Dynamic Graph Mutation Is Not Transactional

`graph_editor` mutates the live graph before validation and persistence.

Required fix:

- clone graph
- apply edit to clone
- validate clone
- persist
- atomically commit or rollback

### 6. Publisher Contract Mismatch

Some publishers put the full report in `final_answer` while `content` is only a
status string.

Required fix:

- standardize `final_report`
- support `final_answer` as a promoted report field
- ensure `file_writer` receives the full report text

### 7. Tool Loop Context Break

`Agent.round_call()` appends tool results but then rebuilds `prev_messages` using
`[:-1]`, dropping the newest tool result from the next LLM call.

Required fix:

- include tool results in the next model call
- add a regression test proving the second model call can see tool output

### 8. Workspace Root Depends On `cwd`

Relative workspace roots are resolved from process working directory, not the
swarm package or manifest location.

Required fix:

- resolve relative workspace roots against the swarm package root
- add a test proving stable resolution when started from another directory

### 9. Runtime Info May Persist Sensitive Data

Runtime events can include prompts, content, graph edits, metadata, and paths.

Required fix:

- sanitize runtime-info detail
- redact secrets
- truncate large prompt/content fields

### 10. Test Discovery Is Brittle

`python -m unittest discover` can import optional modules and fail when optional
dependencies are absent.

Required fix:

- make optional modules lazy-import dependencies
- document and enforce canonical test command

## Implementation Order

### Phase 1: Stop State Pollution And Broken Output

- [x] Make private workspace run-scoped.
- [x] Pass `run_id` into execution and agent workspace context.
- [x] Do not inject durable private files unless explicitly enabled.
- [x] Promote `final_answer` into `final_report`.
- [x] Ensure publish file nodes write complete report text.
- [x] Fix tool loop message replay.
- [x] Fix workspace root resolution.
- [x] Add targeted regression tests.

### Phase 2: Add API Guardrails

- [x] Add API token settings.
- [x] Protect mutating/high-risk routes.
- [x] Narrow CORS origins.
- [x] Restrict package loading to `swarm_root`.
- [x] Validate package-local manifest paths.
- [x] Remove arbitrary module import fallback.
- [x] Disable automatic pip install during normal runtime loading.

### Phase 3: Add Tool Capability Policy

- [x] Define capability taxonomy.
- [x] Parse capabilities from `swarm.toml`.
- [x] Add capabilities to `ToolContext`.
- [x] Enforce capabilities in high-risk tools.
- [x] Prevent runtime workspace/tool permission escalation.

### Phase 4: Make Graph Editing Safe

- [x] Convert graph editing to clone-validate-commit.
- [ ] Split runtime-only graph edits from persistent commits.
- [ ] Require explicit capability for persistence.
- [x] Add rollback tests.

### Phase 5: Sanitize Runtime Info

- [x] Redact secret-like values.
- [x] Truncate prompts/content.
- [x] Avoid storing full spawned agent prompts.
- [x] Add tests for sanitized event data.

### Phase 6: Stabilize Verification

- [x] Fix optional dependency imports for test discovery.
- [x] Document canonical test commands.
- [x] Run focused backend tests.
- [ ] Run frontend build if API contract changes affect frontend types.
- [ ] Add frontend controls for `require_auth`, token env name, and CORS origins if browser editing is desired.

## Acceptance Criteria

- [x] New runs cannot see previous run private workspace artifacts by default.
- [x] Mutating API routes reject unauthorized requests when auth is enabled.
- [x] CORS is configurable and no longer globally open by default.
- [x] Swarm loading cannot escape `swarm_root`.
- [x] Manifest file references cannot escape the package root.
- [x] High-risk tools require explicit capabilities.
- [x] Spawned agents cannot escalate permissions.
- [x] Graph edits are transactional.
- [x] Publisher/file_writer writes full reports, not status text.
- [x] Tool-call agents can see tool results in the next LLM turn.
- [x] Runtime info does not persist full prompts or secrets.
- [x] Canonical tests pass without optional service dependencies.
