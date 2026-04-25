"""Meta-execution runtime for Angelus.

The MetaExecutor wraps GraphExecutor execution into an iterative,
self-driving loop.  After each pass it inspects the swarm cognitive graph
for unresolved issues (unsupported claims, conflicts, open questions) and
automatically re-injects a follow-up mission until the graph converges or
a max-iteration limit is hit.

This is the "dynamic execution runtime" layer: the graph defines the
pipeline, but the MetaExecutor decides when the pipeline has truly finished.
"""

from __future__ import annotations

import copy
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from .cognitive import CognitiveNodeType, CognitiveRelationType, CognitiveNode, CognitiveEdge
from .results import ExecutionEvent, ExecutionState

if TYPE_CHECKING:
    from .core import Core
    from .policy import ExecutionGraph


class MetaExecutor:
    """Iterative meta-executor that drives a swarm until cognitive convergence."""

    def __init__(
        self,
        max_iterations: int = 5,
        convergence_threshold: int = 0,
    ) -> None:
        self.max_iterations = max(max_iterations, 1)
        self.convergence_threshold = convergence_threshold

    async def run(
        self,
        graph: "ExecutionGraph",
        core: "Core",
        initial_payload: Any,
        *,
        rounds: int = 0,
        run_id: Optional[str] = None,
        swarm_name: Optional[str] = None,
        event_sink: Optional[Callable[[ExecutionEvent], None]] = None,
    ) -> ExecutionState:
        """Execute the graph iteratively until cognitive convergence.

        Each iteration runs the full execution graph from entry to exit.
        After each iteration the swarm cognitive graph is inspected:
        - Unsupported claims (claims/hypotheses with no evidence)
        - Logical conflicts (A supports B AND A opposes B)
        - Open questions (QUESTION nodes)

        If any issue remains, a follow-up mission is constructed and the
        graph is executed again.  The original payload is preserved and
        enriched with iteration history.
        """
        from .executor import GraphExecutor

        current_payload = self._normalize_payload(initial_payload)
        last_state: Optional[ExecutionState] = None

        for iteration in range(1, self.max_iterations + 1):
            # Tag the payload with iteration metadata
            current_payload["_meta_iteration"] = iteration
            current_payload["_meta_max_iterations"] = self.max_iterations

            self._emit_meta_event(
                event_sink,
                run_id=run_id or "",
                swarm_name=swarm_name,
                iteration=iteration,
                event_type="meta.iteration.started",
                detail={"payload_keys": list(current_payload.keys())},
            )

            executor = GraphExecutor()
            state = await executor.execute(
                graph,
                core,
                current_payload,
                rounds=rounds,
                run_id=f"{run_id or ''}_iter{iteration}" if run_id else f"iter{iteration}",
                swarm_name=swarm_name,
                event_sink=event_sink,
            )
            last_state = state

            # Snapshot cognitive graph state
            cg = core.swarm_cognitive_graph
            unsupported = cg.find_unsupported_claims()
            conflicts = cg.find_conflicts()
            open_questions = [
                n for n in cg.nodes.values()
                if n.node_type == CognitiveNodeType.QUESTION
            ]

            issue_count = len(unsupported) + len(conflicts) + len(open_questions)

            self._emit_meta_event(
                event_sink,
                run_id=run_id or "",
                swarm_name=swarm_name,
                iteration=iteration,
                event_type="meta.iteration.completed",
                detail={
                    "issue_count": issue_count,
                    "unsupported_claims": len(unsupported),
                    "conflicts": len(conflicts),
                    "open_questions": len(open_questions),
                    "total_nodes": len(cg.nodes),
                    "total_edges": len(cg.edges),
                },
            )

            # Convergence check
            if issue_count <= self.convergence_threshold:
                self._emit_meta_event(
                    event_sink,
                    run_id=run_id or "",
                    swarm_name=swarm_name,
                    iteration=iteration,
                    event_type="meta.converged",
                    detail={"reason": "cognitive_graph_stable", "issue_count": issue_count},
                )
                break

            if iteration >= self.max_iterations:
                self._emit_meta_event(
                    event_sink,
                    run_id=run_id or "",
                    swarm_name=swarm_name,
                    iteration=iteration,
                    event_type="meta.max_iterations_reached",
                    detail={"issue_count": issue_count},
                )
                break

            # Build follow-up mission for next iteration
            current_payload = self._build_follow_up_payload(
                current_payload,
                state,
                cg,
                unsupported,
                conflicts,
                open_questions,
                iteration,
            )

        # Ensure we return a non-None state
        if last_state is None:
            raise RuntimeError("MetaExecutor failed to produce any execution state.")

        # Tag final state with meta summary
        last_state.metadata["_meta_executed"] = True
        last_state.metadata["_meta_final_iteration"] = iteration
        last_state.metadata["_meta_converged"] = issue_count <= self.convergence_threshold

        return last_state

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _normalize_payload(payload: Any) -> Dict[str, Any]:
        if isinstance(payload, dict):
            return dict(payload)
        return {"input": payload}

    def _build_follow_up_payload(
        self,
        previous_payload: Dict[str, Any],
        state: ExecutionState,
        cg: Any,
        unsupported: List[Any],
        conflicts: List[Any],
        open_questions: List[Any],
        iteration: int,
    ) -> Dict[str, Any]:
        """Construct the payload for the next meta-iteration."""
        payload = copy.deepcopy(previous_payload)

        # Preserve original user input
        if "input" not in payload and "text" in payload:
            payload["input"] = payload["text"]

        # Build focus prompt for the next research wave
        focus_lines: List[str] = []

        if open_questions:
            focus_lines.append("Open questions that need answers:")
            for q in open_questions[:5]:
                focus_lines.append(f"  - {q.content}")

        if unsupported:
            focus_lines.append("Claims that lack supporting evidence:")
            for c in unsupported[:5]:
                focus_lines.append(f"  - {c.content}")

        if conflicts:
            focus_lines.append("Logical conflicts detected:")
            for a, b, _edges in conflicts[:3]:
                focus_lines.append(f"  - '{a.content}' vs '{b.content}'")

        focus_text = "\n".join(focus_lines) if focus_lines else "Continue deepening the research."

        # Inject follow-up instructions
        payload["_meta_follow_up"] = {
            "iteration": iteration + 1,
            "previous_output": state.payload if isinstance(state.payload, str) else str(state.payload)[:800],
            "focus": focus_text,
            "cognitive_summary": {
                "total_nodes": len(cg.nodes),
                "total_edges": len(cg.edges),
                "open_questions": len(open_questions),
                "unsupported_claims": len(unsupported),
                "conflicts": len(conflicts),
            },
        }

        return payload

    def _emit_meta_event(
        self,
        event_sink: Optional[Callable[[ExecutionEvent], None]],
        *,
        run_id: str,
        swarm_name: Optional[str],
        iteration: int,
        event_type: str,
        detail: Dict[str, Any],
    ) -> None:
        if event_sink is None:
            return
        event_sink(
            ExecutionEvent(
                run_id=run_id,
                swarm_name=swarm_name,
                event_type=event_type,
                node_id=-1,
                node_name="meta_executor",
                node_type="MetaExecutor",
                rounds=iteration,
                status="running",
                data=detail,
            )
        )
