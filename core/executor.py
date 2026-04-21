from __future__ import annotations

from typing import Any, Dict, Optional, TYPE_CHECKING

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
        current_node_id: Optional[int] = graph.entry_node_id

        while current_node_id is not None:
            node = graph.nodes[current_node_id]
            input_payload = state.payload
            output_payload = input_payload

            try:
                if isinstance(node, AgentNode):
                    agent = core.get_agent(node.agent_id)
                    state.rounds += 1
                    result = await agent.round_call(
                        rounds=state.rounds,
                        user_message=str(state.payload),
                        additional_prompt=node.additional_prompt,
                    )
                    output_payload = result
                    if getattr(result, "assistant_message", None):
                        state.payload = result.assistant_message
                    elif getattr(result, "raw_response", None) is not None:
                        state.payload = result.raw_response
                    else:
                        state.payload = result
                elif isinstance(node, ToolNode):
                    tool = core.get_tool(node.tool_name)
                    tool_context = ToolContext(
                        node_id=node.node_id,
                        rounds=state.rounds,
                        metadata=dict(state.metadata),
                    )
                    arguments = self._build_tool_arguments(node, state.payload)
                    output_payload = await tool.execute(arguments, context=tool_context)
                    state.payload = output_payload
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

            current_node_id = node.next_node_ids[0] if node.next_node_ids else None

        return state

    def _build_tool_arguments(self, node: ToolNode, payload: Any) -> Dict[str, Any]:
        if isinstance(payload, dict):
            base_arguments = dict(payload)
        else:
            base_arguments = {"input": payload}
        base_arguments.update(node.input_mapping)
        return base_arguments
