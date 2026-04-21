from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from .cognitive import CognitiveEdge, CognitiveNode, CognitiveNodeType, CognitiveRelationType
from .policy import AgentNode, ExecutionGraph, ExecutionStep, ToolNode
from .results import ExecutionEvent, ExecutionState
from .toodefl import ToolContext

if TYPE_CHECKING:
    from .core import Core


class GraphExecutor:
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

        state = ExecutionState(payload=initial_payload, rounds=rounds)
        self._emit(
            event_sink,
            ExecutionEvent(
                run_id=run_id or "",
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
            result = await self._execute_from_node(
                graph,
                core,
                state,
                graph.entry_node_id,
                run_id=run_id,
                swarm_name=swarm_name,
                event_sink=event_sink,
            )
        except Exception as exc:
            self._emit(
                event_sink,
                ExecutionEvent(
                    run_id=run_id or "",
                    swarm_name=swarm_name,
                    event_type="run.failed",
                    rounds=state.rounds,
                    status="failed",
                    data={
                        "error": str(exc),
                        "state_snapshot": state.snapshot(),
                    },
                ),
            )
            raise

        self._emit(
            event_sink,
            ExecutionEvent(
                run_id=run_id or "",
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
            input_payload = state.payload
            output_payload = input_payload
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
                    output_payload = result
                    parsed_agent_output = self._parse_structured_agent_output(result.assistant_message)
                    if getattr(result, "assistant_message", None):
                        state.payload = result.assistant_message
                    elif getattr(result, "raw_response", None) is not None:
                        state.payload = result.raw_response
                    else:
                        state.payload = result
                    if parsed_agent_output is not None:
                        output_payload = parsed_agent_output
                        if isinstance(parsed_agent_output, dict):
                            self._apply_metadata_updates(state.metadata, parsed_agent_output)
                            for key, value in parsed_agent_output.items():
                                if key in {
                                    "content",
                                    "metadata_patch",
                                    "metadata_clear",
                                    "next_node_id",
                                    "next_node_ids",
                                    "branch",
                                    "branches",
                                    "status",
                                    "error",
                                }:
                                    continue
                                state.metadata[key] = value
                            if "content" in parsed_agent_output:
                                state.payload = parsed_agent_output["content"]
                            else:
                                state.payload = parsed_agent_output
                            next_node_override = self._extract_next_node_id(parsed_agent_output)
                        elif isinstance(parsed_agent_output, str):
                            state.payload = parsed_agent_output
                    else:
                        next_node_override = self._extract_next_node_id(state.payload)

                    # Merge agent's private cognitive graph into swarm shared graph
                    core.merge_agent_cognitive_graph(node.agent_id)

                    # Record execution trace in cognitive graph
                    core.swarm_cognitive_graph.add_node(
                        CognitiveNode(
                            node_type=CognitiveNodeType.EXECUTION_TRACE,
                            content=f"Agent '{node.agent_id}' executed node '{node.node_name}' (round {state.rounds})",
                            source=node.agent_id,
                            metadata={"execution_node_id": node.node_id, "rounds": state.rounds},
                        )
                    )
                elif isinstance(node, ToolNode):
                    tool = core.get_tool(node.tool_name)
                    tool_context = ToolContext(
                        node_id=node.node_id,
                        rounds=state.rounds,
                        metadata=dict(state.metadata),
                        core=core,
                        graph=graph,
                    )
                    arguments = self._build_tool_arguments(node, state.payload, state.metadata)
                    output_payload = await tool.execute(arguments, context=tool_context)
                    if isinstance(output_payload, dict):
                        self._apply_metadata_updates(state.metadata, output_payload)
                        if "content" in output_payload:
                            state.payload = output_payload["content"]
                        else:
                            state.payload = output_payload
                    else:
                        state.payload = output_payload
                    next_node_override = self._extract_next_node_id(output_payload)
                else:
                    output_payload = state.payload

                next_targets = self._resolve_next_targets(graph, node, state.payload, next_node_override)
                self._validate_next_targets(graph, node.node_id, next_targets)

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
                        },
                    ),
                )
                raise

            next_targets = self._resolve_next_targets(graph, node, state.payload, next_node_override)
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
                state.rounds = max(
                    [state.rounds] + [branch_result["rounds"] for branch_result in branch_results]
                )
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

    def _emit(
        self,
        event_sink: Optional[Callable[[ExecutionEvent], None]],
        event: ExecutionEvent,
    ) -> None:
        if event_sink is not None:
            event_sink(event)

    def _apply_metadata_updates(self, target_metadata: Dict[str, Any], payload: Dict[str, Any]) -> None:
        metadata_patch = payload.get("metadata_patch")
        if isinstance(metadata_patch, dict):
            target_metadata.update(metadata_patch)

        metadata_clear = payload.get("metadata_clear")
        for key in self._coerce_metadata_keys(metadata_clear):
            target_metadata.pop(key, None)

    def _coerce_metadata_keys(self, raw: Any) -> List[str]:
        if raw is None:
            return []
        if isinstance(raw, str):
            return [raw]
        if isinstance(raw, list):
            return [str(item) for item in raw if item is not None]
        return [str(raw)]

    def _build_tool_arguments(self, node: ToolNode, payload: Any, runtime_metadata: Dict[str, Any]) -> Dict[str, Any]:
        if isinstance(payload, dict):
            base_arguments = dict(payload)
        else:
            base_arguments = {"input": payload}
        base_arguments.update(node.input_mapping)
        base_arguments.setdefault("runtime_metadata", dict(runtime_metadata))
        return base_arguments

    def _extract_next_node_id(self, payload: Any) -> Optional[int]:
        if not isinstance(payload, dict):
            return None
        next_node_id = payload.get("next_node_id")
        if next_node_id is None:
            return None
        return int(next_node_id)

    def _validate_next_targets(
        self,
        graph: ExecutionGraph,
        current_node_id: int,
        next_targets: List[int],
    ) -> None:
        for next_node_id in next_targets:
            self._ensure_node_exists(
                graph,
                next_node_id,
                current_node_id=current_node_id,
                label="next_node_id",
            )

    def _ensure_node_exists(
        self,
        graph: ExecutionGraph,
        node_id: int,
        *,
        current_node_id: int,
        label: str,
    ) -> None:
        if node_id not in graph.nodes:
            raise ValueError(
                f"Node {current_node_id} resolved {label} {node_id}, but that node does not exist."
            )

    def _parse_structured_agent_output(self, assistant_message: Optional[str]) -> Any:
        if not isinstance(assistant_message, str):
            return None
        candidate = assistant_message.strip()
        if not candidate:
            return None
        if candidate.startswith("```"):
            candidate = self._strip_code_fence(candidate)
        if not candidate.startswith("{") and not candidate.startswith("["):
            return None
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            return None

    def _strip_code_fence(self, text: str) -> str:
        lines = text.splitlines()
        if len(lines) >= 2 and lines[0].strip().startswith("```") and lines[-1].strip().startswith("```"):
            inner = lines[1:-1]
            if inner and inner[0].strip().lower() == "json":
                inner = inner[1:]
            return "\n".join(inner).strip()
        return text.strip()

    def _resolve_next_targets(
        self,
        graph: ExecutionGraph,
        node: Any,
        payload: Any,
        next_node_override: Optional[int],
    ) -> List[int]:
        if next_node_override is not None:
            return [next_node_override]

        if isinstance(payload, dict):
            next_node_ids = payload.get("next_node_ids")
            if isinstance(next_node_ids, list) and next_node_ids:
                return [int(item) for item in next_node_ids]

            branch = payload.get("branch")
            if branch is not None:
                matched = self._match_branch_targets(graph, node.node_id, branch)
                if matched:
                    return matched

            branches = payload.get("branches")
            if isinstance(branches, list) and branches:
                resolved: List[int] = []
                for item in branches:
                    resolved.extend(self._match_branch_targets(graph, node.node_id, item))
                if resolved:
                    return list(dict.fromkeys(resolved))

        outgoing = graph.outgoing_edges(node.node_id)
        if outgoing:
            return [edge.to_node_id for edge in outgoing]
        return list(node.next_node_ids)

    def _match_branch_targets(
        self,
        graph: ExecutionGraph,
        node_id: int,
        branch_value: Any,
    ) -> List[int]:
        branch_label = str(branch_value).strip()
        if not branch_label:
            return []
        if branch_label.isdigit():
            return [int(branch_label)]

        matched = [
            edge.to_node_id
            for edge in graph.outgoing_edges(node_id)
            if edge.label == branch_label or edge.condition == branch_label
        ]
        return list(dict.fromkeys(matched))

    def _format_agent_input(self, payload: Any, node: AgentNode) -> str:
        if isinstance(payload, dict):
            if "input" in payload and len(payload) == 1:
                return str(payload["input"])
            return str(payload)
        if node.additional_prompt:
            return f"{payload}\n\n{node.additional_prompt}"
        return str(payload)

    def _inject_cognitive_context(self, core: "Core", node: AgentNode) -> Optional[str]:
        """Build an additional_prompt snippet that feeds the swarm cognitive graph into the agent."""
        try:
            cg_export = core.get_cognitive_graph_export(max_nodes=12)
        except Exception:
            return None
        if not cg_export or cg_export.endswith("nodes=0, edges=0):"):
            return None
        return (
            "## Swarm Cognitive Context\n\n"
            "The following is a summary of what the swarm has thought about so far. "
            "Use it to avoid redundant work and build upon existing reasoning:\n\n"
            f"{cg_export}\n"
        )
