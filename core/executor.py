from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .policy import AgentNode, ExecutionGraph, ExecutionStep, ToolNode
from .results import ExecutionState
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
    ) -> ExecutionState:
        validation = graph.validate(core)
        if not validation.is_valid:
            raise ValueError("; ".join(validation.errors))
        if graph.entry_node_id is None:
            raise ValueError("Graph entry node is not set.")

        state = ExecutionState(payload=initial_payload, rounds=rounds)
        return await self._execute_from_node(graph, core, state, graph.entry_node_id)

    async def _execute_from_node(
        self,
        graph: ExecutionGraph,
        core: "Core",
        state: ExecutionState,
        current_node_id: Optional[int],
    ) -> ExecutionState:
        while current_node_id is not None:
            node = graph.nodes[current_node_id]
            input_payload = state.payload
            output_payload = input_payload
            next_node_override: Optional[int] = None

            try:
                if isinstance(node, AgentNode):
                    agent = core.get_agent(node.agent_id)
                    state.rounds += 1
                    agent_input = self._format_agent_input(state.payload, node)
                    result = await agent.round_call(
                        rounds=state.rounds,
                        user_message=agent_input,
                        additional_prompt=node.additional_prompt,
                    )
                    output_payload = result
                    if getattr(result, "assistant_message", None):
                        state.payload = result.assistant_message
                    elif getattr(result, "raw_response", None) is not None:
                        state.payload = result.raw_response
                    else:
                        state.payload = result
                    next_node_override = self._extract_next_node_id(state.payload)
                elif isinstance(node, ToolNode):
                    tool = core.get_tool(node.tool_name)
                    tool_context = ToolContext(
                        node_id=node.node_id,
                        rounds=state.rounds,
                        metadata=dict(state.metadata),
                        core=core,
                        graph=graph,
                    )
                    arguments = self._build_tool_arguments(node, state.payload)
                    output_payload = await tool.execute(arguments, context=tool_context)
                    state.payload = output_payload
                    next_node_override = self._extract_next_node_id(output_payload)
                else:
                    output_payload = state.payload

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
                raise

            next_targets = self._resolve_next_targets(graph, node, state.payload, next_node_override)
            if not next_targets:
                return state

            if len(next_targets) == 1:
                current_node_id = next_targets[0]
                continue

            route_policy = str(node.metadata.get("route_policy", "first")).strip().lower()
            if route_policy == "all":
                branch_results = []
                for branch_index, branch_node_id in enumerate(next_targets):
                    branch_state = state.clone()
                    branch_state.metadata["branch_index"] = branch_index
                    branch_state.metadata["branch_source_node_id"] = node.node_id
                    branch_state = await self._execute_from_node(
                        graph,
                        core,
                        branch_state,
                        branch_node_id,
                    )
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
                    return state
                current_node_id = int(join_node_id)
                continue

            current_node_id = next_targets[0]

        return state

    def _build_tool_arguments(self, node: ToolNode, payload: Any) -> Dict[str, Any]:
        if isinstance(payload, dict):
            base_arguments = dict(payload)
        else:
            base_arguments = {"input": payload}
        base_arguments.update(node.input_mapping)
        return base_arguments

    def _extract_next_node_id(self, payload: Any) -> Optional[int]:
        if not isinstance(payload, dict):
            return None
        next_node_id = payload.get("next_node_id")
        if next_node_id is None:
            return None
        return int(next_node_id)

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
