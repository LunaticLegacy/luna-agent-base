# Next Plan

This file captures the next round of work so the project can continue without relying on the full conversation context.

## Current State

- The backend, frontend, docs, and demo swarm are in place.
- The dynamic graph editing protocol is documented in:
  - `docs/dynamic_graph_protocol.md`
  - `docs/en/dynamic_graph_protocol.md`
- The main remaining risk is the runtime mutation protocol:
  - stale `next_node_id` values
  - graph edits and next-hop resolution being too tightly coupled
  - cleanup steps reusing stale control metadata

## Immediate Fixes

1. Tighten the graph-editing protocol.
   - Ensure only the node insertion step may emit a next hop.
   - Ensure agent creation and deletion never emit `next_node_id`.
   - Ensure node removal never inherits stale routing metadata.

2. Harden runtime mutation safety.
   - Clear stale control keys from metadata after cleanup.
   - Add a local consistency check after every mutation.
   - Validate that the chosen next node still exists before continuing execution.

3. Make the demo graph safer.
   - Revisit temporary node IDs.
   - Ensure the dynamic node insertion point is explicit and stable.
   - Ensure the cleanup path always routes to the intended publisher node.

## Execution Order

1. Fix `tools/graph_editor_tool.py`
2. Fix `tools/agent_manager_tool.py`
3. Re-run the demo swarm
4. Confirm the runtime trace no longer jumps to deleted or not-yet-inserted nodes
5. Update docs if the protocol changes again

## Expected Outcome

- Temporary agent creation will only create agents.
- Graph insertion will own the next-hop decision.
- Cleanup will not leak old `next_node_id` values.
- The demo should complete the full flow:
  - planner
  - spawn auditor
  - insert auditor node
  - auditor output
  - delete auditor
  - remove auditor node
  - publish final output
  - write to `outputs/deepseek_demo_final.txt`

## Notes for the Next Session

- Check `agents/deepseek_demo/runtime_info/events.jsonl` when debugging mutation order.
- Check `core/executor.py` for next-hop precedence.
- Check `tools/graph_editor_tool.py` for any accidental `next_node_id` leakage.
- Check `tools/agent_manager_tool.py` for cleanup-time metadata reuse.

