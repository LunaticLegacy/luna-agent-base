"""Graph execution engine.

``GraphExecutor`` walks an ``ExecutionGraph`` starting from the entry node,
dispatching agent rounds and tool calls, handling branching with retries,
and emitting structured ``ExecutionEvent`` records via an optional event sink.

Key responsibilities:
    * Contract validation before the run starts.
    * Per-node execution (AgentNode → LLM round, ToolNode → tool execution).
    * Routing resolution (next_node_id, branch labels, control patches).
    * Failure classification and regulation.
    * Branch parallelisation with semaphore-limited concurrency and retry.
    * Stop-event handling (hard stop aborts immediately; soft stop after node).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from ..cognitive import CognitiveEdge, CognitiveNode, CognitiveNodeType, CognitiveRelationType
from ..errors import RequiredToolFailedError, ToolContractError
from ..failure_classifier import classify_failure
from ..fault_tolerance import FailureEvent
from ..policy import AgentNode, ExecutionGraph, ExecutionStep, ToolNode
from ..results import ExecutionEvent, ExecutionState
from ..toodefl import ToolContext
from ..tool_contract import ToolContractValidator
from .protocol import ExecutionProtocolMixin

if TYPE_CHECKING:
    from ..core import Core


class GraphExecutor(ExecutionProtocolMixin):
    """Execute an execution graph against a runtime core."""

    # ------------------------------------------------------------------
    # Event emission (inlined from former ExecutionEventMixin)
    # ------------------------------------------------------------------
    def _emit(
        self,
        event_sink: Optional[Callable[[ExecutionEvent], None]],
        event: ExecutionEvent,
    ) -> None:
        """Forward *event* to *event_sink* if one is attached."""
        if event_sink is not None:
            event_sink(event)

    # ------------------------------------------------------------------
    # Cognitive context injection (inlined from former CognitiveContextMixin)
    # ------------------------------------------------------------------
    def _inject_cognitive_context(self, core: "Core", node: AgentNode) -> Optional[str]:
        """Build a cognitive-context string for *node* from the shared graph.

        Tries agent-specific exports first, then falls back to the global
        cognitive graph export.  Returns None if nothing useful is available.
        """
        global_context = ""
        try:
            build_globals = getattr(core, "build_global_context_export", None)
            if callable(build_globals):
                global_context = build_globals(agent_id=node.agent_id)
        except Exception:
            global_context = ""

        try:
            build_context = getattr(core, "build_thought_context_export", None)
            if callable(build_context):
                cg_export = build_context(
                    agent_id=node.agent_id,
                    query=f"{node.node_name} {node.additional_prompt or ''}",
                    purpose=f"Support execution node {node.node_name}",
                    max_nodes=None,
                )
            else:
                cg_export = core.get_cognitive_graph_export(max_nodes=12)
        except Exception:
            return global_context or None
        if global_context and cg_export:
            return f"{global_context}\n\n{cg_export}"
        if global_context:
            return global_context
        if not cg_export or cg_export.endswith("nodes=0, edges=0):"):
            return None
        return cg_export

    async def execute(
        self,
        graph: ExecutionGraph,
        core: "Core",
        initial_payload: Any,
        *,
        rounds: int = 0,
        run_id: Optional[str] = None,
        swarm_name: Optional[str] = None,
        event_sink: Optional[Callable[[ExecutionEvent], None]] = None,
    ) -> ExecutionState:
        """Execute *graph* starting from its entry node.

        Steps:
            1. Validate tool contracts.
            2. Register stop event and initialise state.
            3. Walk nodes via ``_execute_from_node``.
            4. Emit completion / failure / stop events.
            5. Clean up transient nodes and stop event.

        Args:
            graph: The ExecutionGraph to run.
            core: Runtime core providing agents, tools, and policy.
            initial_payload: Starting payload passed to the entry node.
            rounds: Starting round counter.
            run_id: Optional run identifier (auto-generated if omitted).
            swarm_name: Swarm context for event tagging.
            event_sink: Optional callback for ExecutionEvent emission.

        Returns:
            The final ExecutionState.

        Raises:
            ToolContractError: If pre-run tool contract validation fails.
            Exception: Re-raised from node execution after emitting failure events.
        """
        if graph.entry_node_id is None:
            raise ValueError("Graph entry node is not set.")

        contract_validator = getattr(core, "tool_contract_validator", None) or ToolContractValidator()
        contract_report = contract_validator.validate(core, graph)
        if not contract_report.ok:
            record = getattr(core, "record_runtime_change", None)
            if callable(record):
                record(
                    action="tool.contract_validation_failed",
                    subject_kind="graph",
                    subject_id=getattr(graph, "graph_name", None),
                    detail=contract_report.to_dict(),
                )
            raise ToolContractError(contract_report)

        effective_run_id = run_id or uuid.uuid4().hex
        set_current_run_id = getattr(core, "set_current_run_id", None)
        if callable(set_current_run_id):
            set_current_run_id(effective_run_id)

        # Register stop event for this run
        register_stop = getattr(core, "register_stop_event", None)
        if callable(register_stop):
            register_stop(effective_run_id)

        state = ExecutionState(payload=initial_payload, rounds=rounds)
        self._emit(
            event_sink,
            ExecutionEvent(
                run_id=effective_run_id,
                swarm_name=swarm_name,
                event_type="run.started",
                rounds=state.rounds,
                status="running",
                data={
                    "entry_node_id": graph.entry_node_id,
                    "entry_node_name": graph.nodes[graph.entry_node_id].node_name,
                    "state_snapshot": state.snapshot(),
                },
            ),
        )
        try:
            try:
                result = await self._execute_from_node(
                    graph,
                    core,
                    state,
                    graph.entry_node_id,
                    run_id=effective_run_id,
                    swarm_name=swarm_name,
                    event_sink=event_sink,
                )
            except Exception as exc:
                classification = classify_failure(exc)
                failure = FailureEvent(
                    run_id=effective_run_id,
                    swarm_name=swarm_name or "",
                    graph_revision=self._graph_revision(core),
                    failure_scope="run",
                    failure_kind=classification.failure_kind,
                    message=str(exc),
                    state_snapshot=state.snapshot(),
                    recoverable=classification.recoverable,
                    retryable=classification.retryable,
                    suggested_action=classification.suggested_action,
                    detail=classification.detail or {},
                )
                regulate_failure = getattr(core, "regulate_failure", None)
                regulation = None
                if callable(regulate_failure):
                    try:
                        regulation = regulate_failure(failure, graph=graph)
                    except Exception:
                        regulation = None
                self._emit(
                    event_sink,
                    ExecutionEvent(
                        run_id=effective_run_id,
                        swarm_name=swarm_name,
                        event_type="run.failed",
                        rounds=state.rounds,
                        status="failed",
                        data={
                            "error": str(exc),
                            "state_snapshot": state.snapshot(),
                            "failure": failure.to_dict(),
                            "regulation": regulation.to_dict() if regulation is not None else None,
                        },
                    ),
                )
                raise

            stop_type = getattr(core, "check_stop", lambda _: None)(effective_run_id) if core else None
            if stop_type:
                self._emit(
                    event_sink,
                    ExecutionEvent(
                        run_id=effective_run_id,
                        swarm_name=swarm_name,
                        event_type="run.stopped",
                        rounds=result.rounds,
                        status="stopped",
                        data={
                            "stop_type": stop_type,
                            "state_snapshot": result.snapshot(),
                        },
                    ),
                )
            else:
                self._emit(
                    event_sink,
                    ExecutionEvent(
                        run_id=effective_run_id,
                        swarm_name=swarm_name,
                        event_type="run.completed",
                        rounds=result.rounds,
                        status="completed",
                        data={
                            "state_snapshot": result.snapshot(),
                        },
                    ),
                )
            return result
        finally:
            clear_stop = getattr(core, "clear_stop", None)
            if callable(clear_stop):
                clear_stop(effective_run_id)
            cleanup = getattr(core, "cleanup_transient_execution_nodes", None)
            if callable(cleanup):
                try:
                    cleanup(graph=graph)
                except Exception:
                    pass

    async def _execute_from_node(
        self,
        graph: ExecutionGraph,
        core: "Core",
        state: ExecutionState,
        current_node_id: Optional[int],
        *,
        run_id: Optional[str] = None,
        swarm_name: Optional[str] = None,
        event_sink: Optional[Callable[[ExecutionEvent], None]] = None,
    ) -> ExecutionState:
        """Main execution loop: walk from *current_node_id* until no next target.

        This orchestrator delegates every stage of node execution to focused
        helpers so that the loop itself fits on a single screen.
        """
        while current_node_id is not None:
            # 1. Hard stop -------------------------------------------------
            hard_stop = self._check_hard_stop(core, run_id, current_node_id, state, event_sink, swarm_name)
            if hard_stop:
                return state

            node = graph.nodes[current_node_id]
            input_payload = state.payload

            # 2. Skip / quarantine -----------------------------------------
            skip_target = self._handle_node_skip(graph, node, state, event_sink, run_id, swarm_name)
            if skip_target is not None:
                current_node_id = skip_target
                continue

            # 3. Emit node.started -----------------------------------------
            self._emit_node_started(node, state, event_sink, run_id, swarm_name, input_payload)

            # 4. Run node + resolve routing --------------------------------
            try:
                routing = await self._run_node_and_resolve_routing(
                    graph, core, node, state, input_payload, event_sink, run_id, swarm_name
                )
            except Exception as exc:
                self._handle_node_error(exc, graph, core, node, state, input_payload, event_sink, run_id, swarm_name)
                raise

            next_targets = routing["next_targets"]
            output_payload = routing["output_payload"]
            llm_input = routing.get("llm_input")
            node_completion_status = routing.get("node_completion_status", "ok")

            # 5. Terminal node ---------------------------------------------
            if not next_targets:
                self._emit_node_completed(
                    node, state, event_sink, run_id, swarm_name,
                    node_completion_status, output_payload=output_payload, llm_input=llm_input,
                )
                return state

            # 6. Soft stop -------------------------------------------------
            soft_stop = self._check_soft_stop(core, run_id, node, state, event_sink, swarm_name)
            if soft_stop:
                return state

            # 7. Route to next node(s) -------------------------------------
            current_node_id = await self._route_to_next(
                graph, core, node, state, next_targets,
                output_payload, llm_input, node_completion_status,
                event_sink, run_id, swarm_name,
            )
            if current_node_id is None:
                return state

        return state

    def _check_hard_stop(
        self,
        core: "Core",
        run_id: Optional[str],
        current_node_id: int,
        state: ExecutionState,
        event_sink: Optional[Callable[[ExecutionEvent], None]],
        swarm_name: Optional[str],
    ) -> bool:
        """Return True if a hard stop is requested and emit the stop event."""
        stop_type = getattr(core, "check_stop", lambda _: None)(run_id) if core else None
        if stop_type == "hard":
            self._emit(
                event_sink,
                ExecutionEvent(
                    run_id=run_id or "",
                    swarm_name=swarm_name,
                    event_type="run.stopped",
                    node_id=current_node_id,
                    rounds=state.rounds,
                    status="stopped",
                    data={"stop_type": "hard", "reason": "hard stop requested"},
                ),
            )
            return True
        return False

    def _handle_node_skip(
        self,
        graph: ExecutionGraph,
        node: Any,
        state: ExecutionState,
        event_sink: Optional[Callable[[ExecutionEvent], None]],
        run_id: Optional[str],
        swarm_name: Optional[str],
    ) -> Optional[int]:
        """Check whether *node* is quarantined and return the next node to jump to.

        Returns:
            The fallback / next node ID if the node should be skipped,
            or ``None`` when the node is runnable.
        """
        skip_target, skip_reason = self._node_skip_target(graph, node)
        if skip_reason is None:
            return None

        self._emit(
            event_sink,
            ExecutionEvent(
                run_id=run_id or "",
                swarm_name=swarm_name,
                event_type="node.skipped",
                node_id=node.node_id,
                node_name=node.node_name,
                node_type=node.__class__.__name__,
                rounds=state.rounds,
                status="skipped",
                data={
                    "reason": skip_reason,
                    "fallback_node_id": skip_target,
                    "state_snapshot": state.snapshot(),
                },
            ),
        )

        if skip_target is not None:
            return skip_target

        next_targets = list(node.next_node_ids)
        if next_targets:
            return next_targets[0]

        # No viable fallback — signal termination by returning a sentinel
        # that the caller interprets as "end of execution".
        return None

    def _emit_node_started(
        self,
        node: Any,
        state: ExecutionState,
        event_sink: Optional[Callable[[ExecutionEvent], None]],
        run_id: Optional[str],
        swarm_name: Optional[str],
        input_payload: Any,
    ) -> None:
        """Emit the ``node.started`` event."""
        self._emit(
            event_sink,
            ExecutionEvent(
                run_id=run_id or "",
                swarm_name=swarm_name,
                event_type="node.started",
                node_id=node.node_id,
                node_name=node.node_name,
                node_type=node.__class__.__name__,
                rounds=state.rounds,
                status="running",
                data={
                    "input_payload": input_payload,
                    "state_snapshot": state.snapshot(),
                },
            ),
        )

    async def _run_node_and_resolve_routing(
        self,
        graph: ExecutionGraph,
        core: "Core",
        node: Any,
        state: ExecutionState,
        input_payload: Any,
        event_sink: Optional[Callable[[ExecutionEvent], None]],
        run_id: Optional[str],
        swarm_name: Optional[str],
    ) -> Dict[str, Any]:
        """Dispatch *node* execution and resolve its outgoing targets.

        Returns a dict with keys:
            - ``next_targets`` (list[int])
            - ``output_payload``
            - ``llm_input`` (Optional[dict])
            - ``node_completion_status`` (str)
        """
        output_payload = input_payload
        routing_payload = input_payload
        next_node_override: Optional[int] = None
        llm_input: Optional[Dict[str, Any]] = None
        node_completion_status = "ok"

        if isinstance(node, AgentNode):
            agent_result = await self._run_agent_node(graph, core, node, state, input_payload, event_sink, run_id, swarm_name)
            output_payload = agent_result["output_payload"]
            routing_payload = agent_result["routing_payload"]
            next_node_override = agent_result.get("next_node_override")
            llm_input = agent_result.get("llm_input")
            node_completion_status = agent_result.get("node_completion_status", "ok")
        elif isinstance(node, ToolNode):
            tool_result = await self._run_tool_node(core, graph, node, state, input_payload)
            output_payload = tool_result["output_payload"]
            routing_payload = tool_result["routing_payload"]
            next_node_override = tool_result.get("next_node_override")
        else:
            # Unknown node type — pass payload straight through.
            output_payload = state.payload
            routing_payload = state.payload

        next_targets = self._resolve_next_targets(
            graph, node, routing_payload, next_node_override, metadata=state.metadata
        )
        self._validate_next_targets(graph, node, next_targets)

        state.trace.append(
            ExecutionStep(
                node_id=node.node_id,
                node_name=node.node_name,
                node_type=node.__class__.__name__,
                input_payload=input_payload,
                output_payload=output_payload,
            ).__dict__
        )

        return {
            "next_targets": next_targets,
            "output_payload": output_payload,
            "llm_input": llm_input,
            "node_completion_status": node_completion_status,
        }

    async def _run_agent_node(
        self,
        graph: ExecutionGraph,
        core: "Core",
        node: AgentNode,
        state: ExecutionState,
        input_payload: Any,
        event_sink: Optional[Callable[[ExecutionEvent], None]],
        run_id: Optional[str],
        swarm_name: Optional[str],
    ) -> Dict[str, Any]:
        """Execute an :class:`AgentNode` and return its routing artefacts.

        Handles both ``external`` and ``internal`` tool execution modes,
        agent instance lifecycle (acquire / release), and post-round
        cognitive-graph merging.
        """
        blueprint_ref = node.blueprint_ref
        acquire_agent_instance = getattr(core, "acquire_agent_instance", None)
        parallel_context = state.metadata.get("branch_index") is not None
        if callable(acquire_agent_instance):
            agent = acquire_agent_instance(
                blueprint_ref,
                instance_policy=node.instance_policy,
                parallel_context=parallel_context,
            )
        else:
            agent = core.get_agent(node.agent_id)

        # Allow graph node to override agent tool execution mode.
        if node.metadata.get("tool_execution_mode"):
            agent.tool_execution_mode = node.metadata["tool_execution_mode"]

        state.rounds += 1
        agent_input = (
            state.payload
            if isinstance(state.payload, str)
            else json.dumps(state.payload, ensure_ascii=False)
            if state.payload is not None
            else ""
        )
        cognitive_prompt = self._inject_cognitive_context(core, node)
        combined_prompt = node.additional_prompt
        if cognitive_prompt:
            combined_prompt = (
                f"{combined_prompt}\n\n{cognitive_prompt}"
                if combined_prompt
                else cognitive_prompt
            )

        tool_execution_mode = getattr(agent, "tool_execution_mode", "internal")
        result = None
        node_result = None

        try:
            if tool_execution_mode == "external":
                ext_result = await self._run_agent_external_mode(
                    agent, node, core, graph, state, agent_input, combined_prompt,
                    event_sink, run_id, swarm_name, input_payload,
                )
                result = ext_result["result"]
                node_result = ext_result["node_result"]
            else:
                int_result = await self._run_agent_internal_mode(
                    agent, node, state, agent_input, combined_prompt, input_payload,
                )
                result = int_result["result"]
                node_result = int_result["node_result"]

            output_payload = node_result.output_payload
            routing_payload = node_result.routing_payload
            next_node_override = node_result.next_node_override
            llm_input = getattr(result, "llm_input", None)

            # Preserve outputs and patches in state metadata.
            state.metadata.setdefault("outputs", {})
            state.metadata["outputs"][str(node.node_id)] = (
                node_result.output_payload
                if node_result.output_payload is not None
                else node_result.state_payload
            )
            if node_result.metadata_patch:
                state.metadata.setdefault("node_metadata", {})
                state.metadata["node_metadata"][str(node.node_id)] = node_result.metadata_patch
            if node_result.control_patch:
                state.metadata.setdefault("control", {})
                state.metadata["control"][str(node.node_id)] = node_result.control_patch

            merge_delta = getattr(core, "merge_agent_cognitive_delta", None)
            if callable(merge_delta):
                merge_delta(blueprint_ref, getattr(result, "cognitive_graph_delta", None))
            else:
                core.merge_agent_cognitive_graph(node.agent_id)
        finally:
            release_agent_instance = getattr(core, "release_agent_instance", None)
            if callable(release_agent_instance):
                release_agent_instance(blueprint_ref)

        return {
            "output_payload": output_payload,
            "routing_payload": routing_payload,
            "next_node_override": next_node_override,
            "llm_input": llm_input,
            "node_completion_status": "ok",
        }

    async def _run_agent_external_mode(
        self,
        agent: Any,
        node: AgentNode,
        core: "Core",
        graph: ExecutionGraph,
        state: ExecutionState,
        agent_input: str,
        combined_prompt: Optional[str],
        event_sink: Optional[Callable[[ExecutionEvent], None]],
        run_id: Optional[str],
        swarm_name: Optional[str],
        input_payload: Any,
    ) -> Dict[str, Any]:
        """Run an agent in ``external`` tool-execution mode with repair / fallback.

        The agent may issue tool calls via a :class:`ToolScheduler`.  If a
        required tool fails, the method attempts policy / argument repair
        for a configurable number of rounds before falling back or raising.
        """
        remaining_input = agent_input
        tool_round = 0
        tool_policy_repair_rounds = 0
        result = None
        node_result = None

        while True:
            result = await agent.round_call(
                rounds=state.rounds,
                user_message=remaining_input,
                additional_prompt=combined_prompt,
            )

            tool_requests = getattr(result, "tool_requests", None) or []
            if not tool_requests:
                node_result = self._normalize_agent_node_result(
                    state, node, result, input_payload=input_payload,
                )
                break

            tool_scheduler_factory = getattr(core, "get_tool_scheduler", None)
            if tool_scheduler_factory is None:
                raise RuntimeError(
                    "ToolScheduler not available but agent is in external tool mode"
                )

            tool_scheduler = tool_scheduler_factory()
            get_capabilities = getattr(core, "get_tool_capabilities", None)
            tool_caps: set = set()
            for t in getattr(agent, "tools", []) or []:
                tname = getattr(t, "tool_name", None)
                if tname and callable(get_capabilities):
                    tool_caps.update(get_capabilities(tname) or set())
            tool_context = ToolContext(
                agent_id=node.agent_id,
                node_id=node.node_id,
                rounds=state.rounds,
                workspace_mode=getattr(core, "workspace_mode", "workspace"),
                workspace_root=getattr(core, "workspace_root", None),
                metadata=dict(state.metadata),
                core=core,
                graph=graph,
                capabilities=tool_caps,
            )

            batch_result = await tool_scheduler.execute_batch(
                tool_requests,
                node_id=node.node_id,
                agent_id=node.agent_id,
                tool_round=tool_round,
                context=tool_context,
            )

            if (getattr(batch_result, "summary", {}) or {}).get("failed_required"):
                failure_policy = (
                    node.metadata.get("failure_policy")
                    if isinstance(node.metadata, dict)
                    else {}
                )
                all_policy_denied = self._all_failed_tools_are_policy_denied(batch_result)
                all_argument_errors = self._all_failed_tools_have_failure_kind(
                    batch_result, "tool_argument_error",
                )
                allow_policy_repair = bool(
                    isinstance(failure_policy, dict)
                    and failure_policy.get("allow_tool_policy_repair")
                )
                allow_tool_call_repair = bool(
                    isinstance(failure_policy, dict)
                    and failure_policy.get("allow_tool_call_repair")
                )
                max_repair_rounds = self._safe_int(
                    failure_policy.get("max_tool_repair_rounds")
                    if isinstance(failure_policy, dict)
                    else None,
                    1,
                )
                can_repair_policy = all_policy_denied and allow_policy_repair
                can_repair_args = all_argument_errors and allow_tool_call_repair

                if (can_repair_policy or can_repair_args) and tool_policy_repair_rounds < max_repair_rounds:
                    remaining_input = self._format_tool_repair_result(batch_result)
                    if can_repair_policy:
                        combined_prompt = (
                            "Your previous tool call was denied by command_runner safety policy. "
                            "Rewrite the tool call at most once using safe single-command calls only. "
                            "Do not use shell metacharacters or redirects: ; && || | > < ` $() . "
                            "If workspace probing is not essential, stop calling tools and continue from explicit assumptions."
                        )
                    else:
                        combined_prompt = (
                            "Your previous tool call had invalid or missing arguments. "
                            "Rewrite the tool call at most once using the exact tool schema. "
                            "For file_writer, include both path and content. "
                            "For file_editor, include path and operation plus the needed edit fields."
                        )
                    tool_policy_repair_rounds += 1
                    tool_round += 1
                    continue

                allow_fallback = bool(
                    isinstance(failure_policy, dict)
                    and failure_policy.get("allow_toolless_fallback")
                )
                if allow_fallback:
                    degraded_reason = (
                        "tool_policy_denied"
                        if all_policy_denied
                        else "tool_argument_error"
                        if all_argument_errors
                        else "required_tool_failed"
                    )
                    state.metadata.setdefault("degraded_nodes", {})[str(node.node_id)] = {
                        "reason": degraded_reason,
                        "tool_batch_summary": getattr(batch_result, "summary", {}),
                    }
                    self._emit_node_degraded(node, state, event_sink, run_id, swarm_name, degraded_reason, batch_result)
                    self._record_runtime_change(core, "node.degraded", "node", str(node.node_id), {
                        "node_id": node.node_id,
                        "failure_kind": degraded_reason,
                        "tool_batch_summary": getattr(batch_result, "summary", {}),
                    })
                    state.metadata["degraded_reason"] = degraded_reason

                    if all_policy_denied:
                        original_mode = getattr(agent, "tool_execution_mode", "external")
                        try:
                            agent.tool_execution_mode = "disabled"
                            result = await agent.round_call(
                                rounds=state.rounds,
                                user_message=self._format_tool_policy_repair_result(batch_result),
                                additional_prompt=(
                                    "Tool policy denied workspace probing. Continue without tools. "
                                    "Produce the best requirement analysis/plan from the user request, "
                                    "and explicitly mark any assumptions."
                                ),
                            )
                        finally:
                            agent.tool_execution_mode = original_mode
                    else:
                        result.assistant_message = self._format_tool_batch_result(batch_result)

                    node_result = self._normalize_agent_node_result(
                        state, node, result, input_payload=input_payload,
                    )
                    break

                raise RequiredToolFailedError(batch_result)

            remaining_input = self._format_tool_batch_result(batch_result)
            combined_prompt = (
                "Do not repeat already-executed tools. "
                "Use the tool results provided above."
            )
            tool_round += 1

        return {"result": result, "node_result": node_result}

    async def _run_agent_internal_mode(
        self,
        agent: Any,
        node: AgentNode,
        state: ExecutionState,
        agent_input: str,
        combined_prompt: Optional[str],
        input_payload: Any,
    ) -> Dict[str, Any]:
        """Run an agent in ``internal`` tool-execution mode.

        The agent handles tool calls internally; no external scheduler loop
        is required.
        """
        result = await agent.round_call(
            rounds=state.rounds,
            user_message=agent_input,
            additional_prompt=combined_prompt,
        )
        node_result = self._normalize_agent_node_result(
            state, node, result, input_payload=input_payload,
        )
        return {"result": result, "node_result": node_result}

    async def _run_tool_node(
        self,
        core: "Core",
        graph: ExecutionGraph,
        node: ToolNode,
        state: ExecutionState,
        input_payload: Any,
    ) -> Dict[str, Any]:
        """Execute a :class:`ToolNode` and return its routing artefacts."""
        tool_name = self._resolve_tool_alias(core, node.tool_name)
        tool = core.get_tool(tool_name)
        get_capabilities = getattr(core, "get_tool_capabilities", None)
        capabilities = get_capabilities(tool_name) if callable(get_capabilities) else set()
        tool_context = ToolContext(
            node_id=node.node_id,
            rounds=state.rounds,
            workspace_mode=getattr(core, "workspace_mode", "workspace"),
            workspace_root=getattr(core, "workspace_root", None),
            metadata=dict(state.metadata),
            core=core,
            graph=graph,
            capabilities=capabilities,
        )
        arguments = self._build_tool_arguments(node, state)
        output_payload = await tool.execute(arguments, context=tool_context)
        node_result = self._normalize_tool_node_result(
            state, output_payload, input_payload=input_payload,
        )

        # Preserve the full tool output in metadata.
        state.metadata.setdefault("outputs", {})
        state.metadata["outputs"][str(node.node_id)] = node_result.output_payload

        return {
            "output_payload": node_result.output_payload,
            "routing_payload": node_result.routing_payload,
            "next_node_override": node_result.next_node_override,
        }

    def _handle_node_error(
        self,
        exc: Exception,
        graph: ExecutionGraph,
        core: "Core",
        node: Any,
        state: ExecutionState,
        input_payload: Any,
        event_sink: Optional[Callable[[ExecutionEvent], None]],
        run_id: Optional[str],
        swarm_name: Optional[str],
    ) -> None:
        """Classify a node-level exception, record it, emit events, and augment state.

        Note:
            This helper **does not raise** — it prepares state and events so
            that the caller can re-raise the original exception.
        """
        if isinstance(node, AgentNode):
            release_agent_instance = getattr(core, "release_agent_instance", None)
            if callable(release_agent_instance):
                release_agent_instance(node.blueprint_ref)

        classification = classify_failure(exc)
        record = getattr(core, "record_runtime_change", None)
        if callable(record) and classification.failure_kind == "output_parse_error":
            record(
                action="node.output_parse_error",
                subject_kind="node",
                subject_id=str(node.node_id),
                detail={
                    "node_id": node.node_id,
                    "node_name": node.node_name,
                    "failure_kind": classification.failure_kind,
                    "detail": classification.detail or {},
                },
            )

        failure = FailureEvent(
            run_id=run_id or "",
            swarm_name=swarm_name or "",
            graph_revision=self._graph_revision(core),
            failure_scope="node",
            failure_kind=classification.failure_kind,
            node_id=node.node_id,
            node_name=node.node_name,
            node_type=node.__class__.__name__,
            message=str(exc),
            state_snapshot=state.snapshot(),
            recoverable=classification.recoverable,
            retryable=classification.retryable,
            suggested_action=classification.suggested_action,
            detail=classification.detail or {},
        )
        regulate_failure = getattr(core, "regulate_failure", None)
        regulation = None
        if callable(regulate_failure):
            try:
                regulation = regulate_failure(failure, graph=graph)
            except Exception:
                regulation = None

        state.trace.append(
            ExecutionStep(
                node_id=node.node_id,
                node_name=node.node_name,
                node_type=node.__class__.__name__,
                input_payload=input_payload,
                output_payload=None,
                status="error",
                error=str(exc),
            ).__dict__
        )

        self._emit(
            event_sink,
            ExecutionEvent(
                run_id=run_id or "",
                swarm_name=swarm_name,
                event_type="node.failed",
                node_id=node.node_id,
                node_name=node.node_name,
                node_type=node.__class__.__name__,
                rounds=state.rounds,
                status="failed",
                data={
                    "error": str(exc),
                    "state_snapshot": state.snapshot(),
                    "failure": failure.to_dict(),
                    "regulation": regulation.to_dict() if regulation is not None else None,
                },
            ),
        )

    def _check_soft_stop(
        self,
        core: "Core",
        run_id: Optional[str],
        node: Any,
        state: ExecutionState,
        event_sink: Optional[Callable[[ExecutionEvent], None]],
        swarm_name: Optional[str],
    ) -> bool:
        """Return True if a soft stop is requested and emit the stop event."""
        stop_type = getattr(core, "check_stop", lambda _: None)(run_id) if core else None
        if stop_type == "soft":
            self._emit(
                event_sink,
                ExecutionEvent(
                    run_id=run_id or "",
                    swarm_name=swarm_name,
                    event_type="run.stopped",
                    node_id=node.node_id,
                    node_name=node.node_name,
                    node_type=node.__class__.__name__,
                    rounds=state.rounds,
                    status="stopped",
                    data={"stop_type": "soft", "reason": "soft stop requested after node completion"},
                ),
            )
            return True
        return False

    def _emit_node_completed(
        self,
        node: Any,
        state: ExecutionState,
        event_sink: Optional[Callable[[ExecutionEvent], None]],
        run_id: Optional[str],
        swarm_name: Optional[str],
        status: str,
        *,
        output_payload: Any = None,
        llm_input: Optional[Dict[str, Any]] = None,
        branch: Optional[str] = None,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit the ``node.completed`` (or branch completion) event."""
        data: Dict[str, Any] = extra_data.copy() if extra_data else {}
        data.setdefault("state_snapshot", state.snapshot())
        if output_payload is not None and "output_payload" not in data and "input_payload" not in data:
            data["output_payload"] = output_payload
        if llm_input is not None:
            data["llm_input"] = llm_input
        self._emit(
            event_sink,
            ExecutionEvent(
                run_id=run_id or "",
                swarm_name=swarm_name,
                event_type="node.completed",
                node_id=node.node_id,
                node_name=node.node_name,
                node_type=node.__class__.__name__,
                branch=branch,
                rounds=state.rounds,
                status=status,
                data=data,
            ),
        )

    def _emit_node_degraded(
        self,
        node: Any,
        state: ExecutionState,
        event_sink: Optional[Callable[[ExecutionEvent], None]],
        run_id: Optional[str],
        swarm_name: Optional[str],
        degraded_reason: str,
        batch_result: Any,
    ) -> None:
        """Emit the ``node.degraded`` event."""
        self._emit(
            event_sink,
            ExecutionEvent(
                run_id=run_id or "",
                swarm_name=swarm_name,
                event_type="node.degraded",
                node_id=node.node_id,
                node_name=node.node_name,
                node_type=node.__class__.__name__,
                rounds=state.rounds,
                status="degraded_ok",
                data={
                    "degraded_reason": degraded_reason,
                    "tool_batch_summary": getattr(batch_result, "summary", {}),
                    "state_snapshot": state.snapshot(),
                },
            ),
        )

    @staticmethod
    def _record_runtime_change(
        core: "Core",
        action: str,
        subject_kind: str,
        subject_id: Optional[str] = None,
        detail: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Safely call ``core.record_runtime_change`` if it exists."""
        record = getattr(core, "record_runtime_change", None)
        if callable(record):
            record(action=action, subject_kind=subject_kind, subject_id=subject_id, detail=detail or {})

    async def _route_to_next(
        self,
        graph: ExecutionGraph,
        core: "Core",
        node: Any,
        state: ExecutionState,
        next_targets: List[int],
        output_payload: Any,
        llm_input: Optional[Dict[str, Any]],
        node_completion_status: str,
        event_sink: Optional[Callable[[ExecutionEvent], None]],
        run_id: Optional[str],
        swarm_name: Optional[str],
    ) -> Optional[int]:
        """Route execution from *node* to its successor(s).

        Returns:
            The next node ID to execute, or ``None`` when execution should
            terminate (e.g. after parallel branches with no join node).
        """
        # Single target — simplest path.
        if len(next_targets) == 1:
            self._emit_node_completed(
                node, state, event_sink, run_id, swarm_name,
                node_completion_status, output_payload=output_payload, llm_input=llm_input,
            )
            return next_targets[0]

        # Parallel branches ------------------------------------------------
        route_policy = str(node.metadata.get("route_policy", "first")).strip().lower()
        if route_policy == "all":
            return await self._execute_parallel_branches(
                graph, core, node, state, next_targets,
                output_payload, llm_input, node_completion_status,
                event_sink, run_id, swarm_name,
            )

        # Default: first target --------------------------------------------
        self._emit_node_completed(
            node, state, event_sink, run_id, swarm_name,
            node_completion_status, output_payload=output_payload, llm_input=llm_input,
        )
        return next_targets[0]

    async def _execute_parallel_branches(
        self,
        graph: ExecutionGraph,
        core: "Core",
        node: Any,
        state: ExecutionState,
        next_targets: List[int],
        output_payload: Any,
        llm_input: Optional[Dict[str, Any]],
        node_completion_status: str,
        event_sink: Optional[Callable[[ExecutionEvent], None]],
        run_id: Optional[str],
        swarm_name: Optional[str],
    ) -> Optional[int]:
        """Execute *next_targets* in parallel with retry, then merge results.

        Returns:
            The ``join_node_id`` if one is configured, otherwise ``None``
            to signal termination.
        """
        runtime_config = getattr(core, "runtime_config", {})
        branch_retry = (
            getattr(runtime_config, "branch_retry", {})
            if hasattr(runtime_config, "branch_retry")
            else {}
        )
        if isinstance(branch_retry, dict):
            max_retries = branch_retry.get("max_retries", 2)
            backoff_ms = branch_retry.get("backoff_ms", 1000)
            backoff_multiplier = branch_retry.get("backoff_multiplier", 2.0)
        else:
            max_retries = getattr(branch_retry, "max_retries", 2)
            backoff_ms = getattr(branch_retry, "backoff_ms", 1000)
            backoff_multiplier = getattr(branch_retry, "backoff_multiplier", 2.0)

        limiter = getattr(core, "limiter", None)
        max_parallel_branches = getattr(limiter, "max_parallel_branches", 3) if limiter else 3
        branch_semaphore = asyncio.Semaphore(max_parallel_branches)

        branch_tasks = [
            self._run_branch_with_retry(
                graph, core, branch_index, branch_node_id, node, state,
                run_id, swarm_name, event_sink, branch_semaphore,
                max_retries, backoff_ms, backoff_multiplier,
            )
            for branch_index, branch_node_id in enumerate(next_targets)
        ]
        branch_outcomes = await asyncio.gather(*branch_tasks)

        branch_results: List[Dict[str, Any]] = []
        for outcome in branch_outcomes:
            branch_index = outcome["branch_index"]
            branch_node_id = outcome["branch_node_id"]
            if outcome["status"] == "success":
                branch_results.append({
                    "branch_index": branch_index,
                    "branch_node_id": branch_node_id,
                    "branch_name": outcome["branch_name"],
                    "status": "success",
                    "payload": outcome["payload"],
                    "rounds": outcome["rounds"],
                    "metadata": outcome["metadata"],
                    "trace": outcome["trace"],
                })
                state.trace.append(
                    ExecutionStep(
                        node_id=branch_node_id,
                        node_name=graph.nodes[branch_node_id].node_name,
                        node_type="BranchResult",
                        input_payload=state.payload,
                        output_payload=outcome["payload"],
                        branch=str(branch_index),
                    ).__dict__
                )
                self._emit(
                    event_sink,
                    ExecutionEvent(
                        run_id=run_id or "",
                        swarm_name=swarm_name,
                        event_type="branch.completed",
                        node_id=branch_node_id,
                        node_name=graph.nodes[branch_node_id].node_name,
                        node_type="BranchResult",
                        branch=str(branch_index),
                        rounds=outcome["rounds"],
                        status="ok",
                        data={
                            "source_node_id": node.node_id,
                            "branch_index": branch_index,
                            "state_snapshot": {
                                "payload": ExecutionState._summarize_payload(outcome["payload"]),
                                "rounds": outcome["rounds"],
                                "metadata": ExecutionState._summarize_metadata(outcome["metadata"]),
                                "trace": [ExecutionState._summarize_step(s) for s in outcome["trace"]],
                                "branch_results": {},
                            },
                        },
                    ),
                )
            else:
                branch_results.append({
                    "branch_index": branch_index,
                    "branch_node_id": branch_node_id,
                    "branch_name": outcome["branch_name"],
                    "status": "failed",
                    "error": outcome.get("error"),
                    "rounds": outcome.get("rounds", state.rounds),
                    "metadata": outcome.get("metadata", {}),
                    "trace": outcome.get("trace", []),
                    "retries_exhausted": True,
                })
                state.trace.append(
                    ExecutionStep(
                        node_id=branch_node_id,
                        node_name=graph.nodes[branch_node_id].node_name,
                        node_type="BranchResult",
                        input_payload=state.payload,
                        output_payload=None,
                        status="error",
                        error=outcome.get("error"),
                        branch=str(branch_index),
                    ).__dict__
                )

        state.branch_results[str(node.node_id)] = branch_results
        branch_merge_payload = {
            "type": "branch_merge",
            "source_node_id": node.node_id,
            "branches": branch_results,
        }
        state.metadata.setdefault("outputs", {})
        state.metadata["outputs"][str(node.node_id)] = branch_merge_payload
        state.rounds = max([state.rounds] + [br["rounds"] for br in branch_results])

        join_node_id = node.metadata.get("join_node_id")
        if join_node_id is None:
            self._emit_node_completed(
                node, state, event_sink, run_id, swarm_name, node_completion_status,
                output_payload=output_payload, llm_input=llm_input,
                extra_data={"input_payload": state.payload, "output_payload": output_payload},
            )
            return None

        join_node_id = int(join_node_id)
        self._ensure_node_exists(graph, join_node_id, current_node_id=node.node_id, label="join_node_id")
        self._emit_node_completed(
            node, state, event_sink, run_id, swarm_name, node_completion_status,
            output_payload=output_payload, llm_input=llm_input,
        )
        return join_node_id

    async def _run_branch_with_retry(
        self,
        graph: ExecutionGraph,
        core: "Core",
        branch_index: int,
        branch_node_id: int,
        source_node: Any,
        state: ExecutionState,
        run_id: Optional[str],
        swarm_name: Optional[str],
        event_sink: Optional[Callable[[ExecutionEvent], None]],
        branch_semaphore: asyncio.Semaphore,
        max_retries: int,
        backoff_ms: int,
        backoff_multiplier: float,
    ) -> Dict[str, Any]:
        """Execute a single branch with semaphore-limited concurrency and retry.

        Returns a dict describing the outcome (success or failure).
        """
        last_error = None
        last_rounds = state.rounds
        for attempt in range(max_retries + 1):
            async with branch_semaphore:
                branch_state = state.clone()
                branch_state.metadata["branch_index"] = branch_index
                branch_state.metadata["branch_source_node_id"] = source_node.node_id

                event_type = "branch.retry.started" if attempt > 0 else "branch.started"
                self._emit(
                    event_sink,
                    ExecutionEvent(
                        run_id=run_id or "",
                        swarm_name=swarm_name,
                        event_type=event_type,
                        node_id=branch_node_id,
                        node_name=graph.nodes[branch_node_id].node_name,
                        node_type=graph.nodes[branch_node_id].__class__.__name__,
                        branch=str(branch_index),
                        rounds=branch_state.rounds,
                        status="running",
                        data={
                            "source_node_id": source_node.node_id,
                            "branch_index": branch_index,
                            "attempt": attempt,
                            "state_snapshot": branch_state.snapshot(),
                        },
                    ),
                )

                try:
                    branch_state = await self._execute_from_node(
                        graph,
                        core,
                        branch_state,
                        branch_node_id,
                        run_id=run_id,
                        swarm_name=swarm_name,
                        event_sink=event_sink,
                    )
                    return {
                        "branch_index": branch_index,
                        "branch_node_id": branch_node_id,
                        "branch_name": graph.nodes[branch_node_id].node_name,
                        "status": "success",
                        "payload": branch_state.payload,
                        "rounds": branch_state.rounds,
                        "metadata": dict(branch_state.metadata),
                        "trace": list(branch_state.trace),
                        "retries": attempt,
                    }
                except Exception as exc:
                    last_error = exc
                    last_rounds = branch_state.rounds
                    if attempt < max_retries:
                        backoff = backoff_ms * (backoff_multiplier ** attempt) / 1000.0
                        self._emit(
                            event_sink,
                            ExecutionEvent(
                                run_id=run_id or "",
                                swarm_name=swarm_name,
                                event_type="branch.retry.scheduled",
                                node_id=branch_node_id,
                                node_name=graph.nodes[branch_node_id].node_name,
                                node_type=graph.nodes[branch_node_id].__class__.__name__,
                                branch=str(branch_index),
                                rounds=branch_state.rounds,
                                status="retrying",
                                data={
                                    "source_node_id": source_node.node_id,
                                    "branch_index": branch_index,
                                    "attempt": attempt + 1,
                                    "max_retries": max_retries,
                                    "backoff_ms": backoff * 1000,
                                    "error": str(exc),
                                    "state_snapshot": branch_state.snapshot(),
                                },
                            ),
                        )
                        await asyncio.sleep(backoff)
                    else:
                        classification = classify_failure(exc)
                        failure = FailureEvent(
                            run_id=run_id or "",
                            swarm_name=swarm_name or "",
                            graph_revision=self._graph_revision(core),
                            failure_scope="branch",
                            failure_kind=classification.failure_kind,
                            node_id=branch_node_id,
                            node_name=graph.nodes[branch_node_id].node_name,
                            node_type=graph.nodes[branch_node_id].__class__.__name__,
                            message=str(exc),
                            state_snapshot=branch_state.snapshot(),
                            branch=str(branch_index),
                            recoverable=classification.recoverable,
                            retryable=classification.retryable,
                            suggested_action=classification.suggested_action,
                            detail=classification.detail or {},
                        )
                        regulate_failure = getattr(core, "regulate_failure", None)
                        regulation = None
                        if callable(regulate_failure):
                            try:
                                regulation = regulate_failure(failure, graph=graph)
                            except Exception:
                                regulation = None
                        self._emit(
                            event_sink,
                            ExecutionEvent(
                                run_id=run_id or "",
                                swarm_name=swarm_name,
                                event_type="branch.failed",
                                node_id=branch_node_id,
                                node_name=graph.nodes[branch_node_id].node_name,
                                node_type=graph.nodes[branch_node_id].__class__.__name__,
                                branch=str(branch_index),
                                rounds=branch_state.rounds,
                                status="failed",
                                data={
                                    "source_node_id": source_node.node_id,
                                    "branch_index": branch_index,
                                    "error": str(exc),
                                    "state_snapshot": branch_state.snapshot(),
                                    "failure": failure.to_dict(),
                                    "regulation": regulation.to_dict() if regulation is not None else None,
                                },
                            ),
                        )

        return {
            "branch_index": branch_index,
            "branch_node_id": branch_node_id,
            "branch_name": graph.nodes[branch_node_id].node_name,
            "status": "failed",
            "error": str(last_error) if last_error else "Unknown error",
            "rounds": last_rounds,
            "metadata": {},
            "trace": [],
            "retries_exhausted": True,
            "retries": max_retries,
        }


    def _node_skip_target(self, graph: ExecutionGraph, node: Any) -> tuple[Optional[int], Optional[str]]:
        """Check if *node* is quarantined and should be skipped.

        Returns:
            (fallback_node_id, reason) if skipped, else (None, None).
        """
        metadata = node.metadata if isinstance(getattr(node, "metadata", None), dict) else {}
        fault_state = metadata.get("fault_tolerance") if isinstance(metadata.get("fault_tolerance"), dict) else {}
        if not fault_state.get("quarantined"):
            return None, None
        fallback = fault_state.get("fallback_node_id")
        if fallback is not None:
            try:
                fallback_id = int(fallback)
                if fallback_id in graph.nodes and fallback_id != getattr(node, "node_id", None):
                    return fallback_id, str(fault_state.get("last_failure_message") or "quarantined")
            except Exception:
                pass
        next_nodes = list(getattr(node, "next_node_ids", []) or [])
        if next_nodes:
            next_target = int(next_nodes[0])
            if next_target != getattr(node, "node_id", None):
                return next_target, str(fault_state.get("last_failure_message") or "quarantined")
        return None, str(fault_state.get("last_failure_message") or "quarantined")

    @staticmethod
    def _graph_revision(core: Any) -> int:
        """Return the current graph revision from the core, or 0."""
        state_getter = getattr(core, "get_graph_runtime_state", None)
        if callable(state_getter):
            try:
                state = state_getter()
                return int(state.get("revision") or 0)
            except Exception:
                return 0
        return 0

    @staticmethod
    def _classify_failure_kind(exc: Exception) -> str:
        """Shorthand for the failure classifier."""
        return classify_failure(exc).failure_kind

    @staticmethod
    def _format_tool_batch_result(batch_result: Any) -> str:
        """Format a ToolBatchResult as a rich text block for the LLM context."""
        results = []
        for r in getattr(batch_result, "results", []):
            results.append({
                "request_id": getattr(r, "request_id", None),
                "tool": getattr(r, "tool", None),
                "status": getattr(r, "status", None),
                "output": getattr(r, "output", None),
                "error": getattr(r, "error", None),
                "duration_ms": getattr(r, "duration_ms", 0),
            })
        data = {
            "type": "tool_batch_result",
            "node_id": getattr(batch_result, "node_id", None),
            "agent_id": getattr(batch_result, "agent_id", None),
            "tool_round": getattr(batch_result, "tool_round", 0),
            "results": results,
            "summary": getattr(batch_result, "summary", {}),
        }
        return (
            f"[TOOL BATCH RESULT - Round {getattr(batch_result, 'tool_round', 0)}]\n"
            f"{json.dumps(data, ensure_ascii=False, indent=2)}\n"
            "[/TOOL BATCH RESULT]"
        )

    @staticmethod
    def _format_tool_policy_repair_result(batch_result: Any) -> str:
        return GraphExecutor._format_tool_repair_result(batch_result)

    @staticmethod
    def _format_tool_repair_result(batch_result: Any) -> str:
        """Format a repair-required message for the LLM after tool failure."""
        data = {
            "type": "tool_call_repair_required",
            "message": "A required tool call failed in a recoverable way.",
            "repair_instruction": (
                "Rewrite the failed tool call once using the exact tool schema. "
                "For command_runner policy denials, use safe single-command calls only. "
                "For file_writer, include path and content."
            ),
            "results": [
                {
                    "request_id": getattr(result, "request_id", None),
                    "tool": getattr(result, "tool", None),
                    "status": getattr(result, "status", None),
                    "error": getattr(result, "error", None),
                }
                for result in getattr(batch_result, "results", []) or []
            ],
            "summary": getattr(batch_result, "summary", {}),
        }
        return (
            "[TOOL POLICY DENIED]\n"
            f"{json.dumps(data, ensure_ascii=False, indent=2)}\n"
            "[/TOOL POLICY DENIED]"
        )

    @staticmethod
    def _all_failed_tools_are_policy_denied(batch_result: Any) -> bool:
        return GraphExecutor._all_failed_tools_have_failure_kind(batch_result, "tool_policy_denied")

    @staticmethod
    def _all_failed_tools_have_failure_kind(batch_result: Any, failure_kind: str) -> bool:
        """Return True if every failed result in *batch_result* has *failure_kind*."""
        failed = [
            result
            for result in getattr(batch_result, "results", []) or []
            if getattr(result, "status", None) == "failed"
        ]
        if not failed:
            return False
        return all(
            isinstance(getattr(result, "error", None), dict)
            and getattr(result, "error", {}).get("failure_kind") == failure_kind
            for result in failed
        )

    @staticmethod
    def _safe_int(raw: Any, default: int) -> int:
        """Safe int coercion with fallback."""
        try:
            return int(raw)
        except Exception:
            return default

    @staticmethod
    def _resolve_tool_alias(core: Any, tool_name: str) -> str:
        """Delegate alias resolution to the core's contract validator, if any."""
        validator = getattr(core, "tool_contract_validator", None)
        resolver = getattr(validator, "resolve_alias", None)
        if callable(resolver):
            return resolver(tool_name)
        return str(tool_name or "").strip()
