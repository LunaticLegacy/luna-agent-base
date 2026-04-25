from __future__ import annotations

import uuid
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from ..cognitive import CognitiveEdge, CognitiveNode, CognitiveNodeType, CognitiveRelationType
from ..fault_tolerance import FailureEvent
from ..policy import AgentNode, ExecutionGraph, ExecutionStep, ToolNode
from ..results import ExecutionEvent, ExecutionState
from ..toodefl import ToolContext
from .cognitive import CognitiveContextMixin
from .events import ExecutionEventMixin
from .payloads import PayloadHelperMixin
from .routing import RoutingHelperMixin

if TYPE_CHECKING:
    from ..core import Core


class GraphExecutor(
    ExecutionEventMixin,
    PayloadHelperMixin,
    RoutingHelperMixin,
    CognitiveContextMixin,
):
    """Execute an execution graph against a runtime core."""

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
        validation = graph.validate(core)
        if not validation.is_valid:
            raise ValueError("; ".join(validation.errors))
        if graph.entry_node_id is None:
            raise ValueError("Graph entry node is not set.")

        effective_run_id = run_id or uuid.uuid4().hex
        set_current_run_id = getattr(core, "set_current_run_id", None)
        if callable(set_current_run_id):
            set_current_run_id(effective_run_id)

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
                failure = FailureEvent(
                    run_id=effective_run_id,
                    swarm_name=swarm_name or "",
                    graph_revision=self._graph_revision(core),
                    failure_scope="run",
                    failure_kind=self._classify_failure_kind(exc),
                    message=str(exc),
                    state_snapshot=state.snapshot(),
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
        while current_node_id is not None:
            node = graph.nodes[current_node_id]
            skip_target, skip_reason = self._node_skip_target(graph, node)
            if skip_reason is not None:
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
                    current_node_id = skip_target
                    continue
                next_targets = list(node.next_node_ids)
                if next_targets:
                    current_node_id = next_targets[0]
                    continue
                return state

            input_payload = state.payload
            output_payload = input_payload
            routing_payload = input_payload
            next_node_override: Optional[int] = None

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

            try:
                if isinstance(node, AgentNode):
                    blueprint_ref = node.blueprint_ref
                    acquire_agent_instance = getattr(core, "acquire_agent_instance", None)
                    if callable(acquire_agent_instance):
                        agent = acquire_agent_instance(
                            blueprint_ref,
                            instance_policy=node.instance_policy,
                        )
                    else:
                        agent = core.get_agent(node.agent_id)
                    state.rounds += 1
                    agent_input = self._format_agent_input(state.payload, node)
                    cognitive_prompt = self._inject_cognitive_context(core, node)
                    combined_prompt = node.additional_prompt
                    if cognitive_prompt:
                        if combined_prompt:
                            combined_prompt = f"{combined_prompt}\n\n{cognitive_prompt}"
                        else:
                            combined_prompt = cognitive_prompt
                    result = await agent.round_call(
                        rounds=state.rounds,
                        user_message=agent_input,
                        additional_prompt=combined_prompt,
                    )
                    node_result = self._normalize_agent_node_result(
                        state,
                        node,
                        result,
                        input_payload=input_payload,
                    )
                    output_payload = node_result.output_payload
                    routing_payload = node_result.routing_payload
                    state.payload = node_result.state_payload
                    next_node_override = node_result.next_node_override
                    merge_delta = getattr(core, "merge_agent_cognitive_delta", None)
                    if callable(merge_delta):
                        merge_delta(blueprint_ref, getattr(result, "cognitive_graph_delta", None))
                    else:
                        core.merge_agent_cognitive_graph(node.agent_id)
                    release_agent_instance = getattr(core, "release_agent_instance", None)
                    if callable(release_agent_instance):
                        release_agent_instance(blueprint_ref)
                elif isinstance(node, ToolNode):
                    tool = core.get_tool(node.tool_name)
                    get_capabilities = getattr(core, "get_tool_capabilities", None)
                    capabilities = get_capabilities(node.tool_name) if callable(get_capabilities) else set()
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
                    arguments = self._build_tool_arguments(node, state.payload, state.metadata)
                    output_payload = await tool.execute(arguments, context=tool_context)
                    node_result = self._normalize_tool_node_result(
                        state,
                        output_payload,
                        input_payload=input_payload,
                    )
                    routing_payload = node_result.routing_payload
                    state.payload = node_result.state_payload
                    next_node_override = node_result.next_node_override
                else:
                    output_payload = state.payload
                    routing_payload = state.payload

                next_targets = self._resolve_next_targets(graph, node, routing_payload, next_node_override)
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
            except Exception as exc:
                if isinstance(node, AgentNode):
                    release_agent_instance = getattr(core, "release_agent_instance", None)
                    if callable(release_agent_instance):
                        release_agent_instance(node.blueprint_ref)
                failure = FailureEvent(
                    run_id=run_id or "",
                    swarm_name=swarm_name or "",
                    graph_revision=self._graph_revision(core),
                    failure_scope="node",
                    failure_kind=self._classify_failure_kind(exc),
                    node_id=node.node_id,
                    node_name=node.node_name,
                    node_type=node.__class__.__name__,
                    message=str(exc),
                    state_snapshot=state.snapshot(),
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
                            "input_payload": input_payload,
                            "error": str(exc),
                            "state_snapshot": state.snapshot(),
                            "failure": failure.to_dict(),
                            "regulation": regulation.to_dict() if regulation is not None else None,
                        },
                    ),
                )
                raise

            next_targets = self._resolve_next_targets(graph, node, routing_payload, next_node_override)
            if not next_targets:
                self._emit(
                    event_sink,
                    ExecutionEvent(
                        run_id=run_id or "",
                        swarm_name=swarm_name,
                        event_type="node.completed",
                        node_id=node.node_id,
                        node_name=node.node_name,
                        node_type=node.__class__.__name__,
                        branch=None,
                        rounds=state.rounds,
                        status="ok",
                        data={
                            "input_payload": input_payload,
                            "output_payload": output_payload,
                            "state_snapshot": state.snapshot(),
                        },
                    ),
                )
                return state

            if len(next_targets) == 1:
                self._emit(
                    event_sink,
                    ExecutionEvent(
                        run_id=run_id or "",
                        swarm_name=swarm_name,
                        event_type="node.completed",
                        node_id=node.node_id,
                        node_name=node.node_name,
                        node_type=node.__class__.__name__,
                        branch=None,
                        rounds=state.rounds,
                        status="ok",
                        data={
                            "input_payload": input_payload,
                            "output_payload": output_payload,
                            "state_snapshot": state.snapshot(),
                        },
                    ),
                )
                current_node_id = next_targets[0]
                continue

            route_policy = str(node.metadata.get("route_policy", "first")).strip().lower()
            if route_policy == "all":
                branch_results = []
                for branch_index, branch_node_id in enumerate(next_targets):
                    branch_state = state.clone()
                    branch_state.metadata["branch_index"] = branch_index
                    branch_state.metadata["branch_source_node_id"] = node.node_id
                    self._emit(
                        event_sink,
                        ExecutionEvent(
                            run_id=run_id or "",
                            swarm_name=swarm_name,
                            event_type="branch.started",
                            node_id=branch_node_id,
                            node_name=graph.nodes[branch_node_id].node_name,
                            node_type=graph.nodes[branch_node_id].__class__.__name__,
                            branch=str(branch_index),
                            rounds=branch_state.rounds,
                            status="running",
                            data={
                                "source_node_id": node.node_id,
                                "branch_index": branch_index,
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
                    except Exception as exc:
                        failure = FailureEvent(
                            run_id=run_id or "",
                            swarm_name=swarm_name or "",
                            graph_revision=self._graph_revision(core),
                            failure_scope="branch",
                            failure_kind=self._classify_failure_kind(exc),
                            node_id=branch_node_id,
                            node_name=graph.nodes[branch_node_id].node_name,
                            node_type=graph.nodes[branch_node_id].__class__.__name__,
                            message=str(exc),
                            state_snapshot=branch_state.snapshot(),
                            branch=str(branch_index),
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
                                    "source_node_id": node.node_id,
                                    "branch_index": branch_index,
                                    "error": str(exc),
                                    "state_snapshot": branch_state.snapshot(),
                                    "failure": failure.to_dict(),
                                    "regulation": regulation.to_dict() if regulation is not None else None,
                                },
                            ),
                        )
                        raise
                    branch_results.append(
                        {
                            "branch_index": branch_index,
                            "branch_node_id": branch_node_id,
                            "branch_name": graph.nodes[branch_node_id].node_name,
                            "payload": branch_state.payload,
                            "rounds": branch_state.rounds,
                            "metadata": dict(branch_state.metadata),
                            "trace": list(branch_state.trace),
                        }
                    )
                    state.trace.append(
                        ExecutionStep(
                            node_id=branch_node_id,
                            node_name=graph.nodes[branch_node_id].node_name,
                            node_type="BranchResult",
                            input_payload=input_payload,
                            output_payload=branch_state.payload,
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
                            rounds=branch_state.rounds,
                            status="ok",
                            data={
                                "source_node_id": node.node_id,
                                "branch_index": branch_index,
                                "state_snapshot": branch_state.snapshot(),
                            },
                        ),
                    )

                state.branch_results[str(node.node_id)] = branch_results
                state.payload = {
                    "type": "branch_merge",
                    "source_node_id": node.node_id,
                    "branches": branch_results,
                }
                state.rounds = max([state.rounds] + [branch_result["rounds"] for branch_result in branch_results])
                join_node_id = node.metadata.get("join_node_id")
                if join_node_id is None:
                    self._emit(
                        event_sink,
                        ExecutionEvent(
                            run_id=run_id or "",
                            swarm_name=swarm_name,
                            event_type="node.completed",
                            node_id=node.node_id,
                            node_name=node.node_name,
                            node_type=node.__class__.__name__,
                            branch=None,
                            rounds=state.rounds,
                            status="ok",
                            data={
                                "input_payload": input_payload,
                                "output_payload": output_payload,
                                "state_snapshot": state.snapshot(),
                            },
                        ),
                    )
                    return state
                join_node_id = int(join_node_id)
                self._ensure_node_exists(graph, join_node_id, current_node_id=node.node_id, label="join_node_id")
                current_node_id = join_node_id
                self._emit(
                    event_sink,
                    ExecutionEvent(
                        run_id=run_id or "",
                        swarm_name=swarm_name,
                        event_type="node.completed",
                        node_id=node.node_id,
                        node_name=node.node_name,
                        node_type=node.__class__.__name__,
                        branch=None,
                        rounds=state.rounds,
                        status="ok",
                        data={
                            "input_payload": input_payload,
                            "output_payload": output_payload,
                            "state_snapshot": state.snapshot(),
                        },
                    ),
                )
                continue

            self._emit(
                event_sink,
                ExecutionEvent(
                    run_id=run_id or "",
                    swarm_name=swarm_name,
                    event_type="node.completed",
                    node_id=node.node_id,
                    node_name=node.node_name,
                    node_type=node.__class__.__name__,
                    branch=None,
                    rounds=state.rounds,
                    status="ok",
                    data={
                        "input_payload": input_payload,
                        "output_payload": output_payload,
                        "state_snapshot": state.snapshot(),
                    },
                ),
            )
            current_node_id = next_targets[0]

        return state

    def _node_skip_target(self, graph: ExecutionGraph, node: Any) -> tuple[Optional[int], Optional[str]]:
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
        text = f"{exc.__class__.__name__}: {exc}".lower()
        if "timeout" in text:
            return "timeout"
        if "route" in text:
            return "routing_error"
        if "mutation" in text:
            return "mutation_error"
        if "invariant" in text or "assert" in text:
            return "invariant_violation"
        if "tool" in text:
            return "tool_error"
        if "agent" in text:
            return "agent_error"
        return "unknown"
