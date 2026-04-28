"""External tool scheduler for Tool Request Protocol v1.

``ToolScheduler`` executes batches of ``ToolRequest`` objects respecting
DAG dependencies (via ``depends_on``) and write-conflict grouping so that
file-writing tools do not race against each other.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

from core.failure_classifier import classify_failure
from core.results import ToolBatchResult, ToolRequest, ToolResult
from core.toodefl import ToolContext


class ToolScheduler:
    """External tool scheduler for Tool Request Protocol v1.

    Attributes:
        core: Runtime core providing tool registry and optional rate limiter.
        limiter: Optional concurrency limiter (``acquire_tool`` / ``release_tool``).
    """

    def __init__(self, core: Any, limiter: Any = None) -> None:
        self.core = core
        self.limiter = limiter

    async def execute_batch(
        self,
        tool_requests: List[ToolRequest],
        *,
        node_id: Optional[int] = None,
        agent_id: Optional[str] = None,
        tool_round: int = 0,
        context: Optional[ToolContext] = None,
    ) -> ToolBatchResult:
        """Execute a batch of tool requests respecting DAG and resource conflicts.

        Args:
            tool_requests: The requested tool calls (may include dependencies).
            node_id: Execution graph node that initiated the batch.
            agent_id: Agent that initiated the batch.
            tool_round: Which ReAct tool iteration this is.
            context: Execution context passed through to each tool.

        Returns:
            A ToolBatchResult containing individual ToolResults and a summary.
        """
        execution_plan = self._build_execution_plan(tool_requests)
        results: List[ToolResult] = []
        completed: Dict[str, ToolResult] = {}

        for level in execution_plan:
            groups = self._group_by_conflicts(level)
            for group in groups:
                if len(group) == 1:
                    result = await self._execute_single(group[0], context=context)
                    results.append(result)
                    completed[group[0].id] = result
                else:
                    coros = [self._execute_single(req, context=context) for req in group]
                    batch_results = await asyncio.gather(*coros, return_exceptions=True)
                    for req, res in zip(group, batch_results):
                        if isinstance(res, Exception):
                            tr = ToolResult(
                                request_id=req.id,
                                tool=req.tool,
                                status="failed",
                                error={
                                    "type": type(res).__name__,
                                    "message": str(res),
                                    "recoverable": True,
                                    "retryable": True,
                                },
                                duration_ms=0,
                            )
                        else:
                            tr = res
                        results.append(tr)
                        completed[req.id] = tr

        failed_required = any(
            r.status == "failed" and req.required
            for req, r in (
                (req, completed.get(req.id))
                for req in tool_requests
            )
            if r is not None
        )

        return ToolBatchResult(
            node_id=node_id,
            agent_id=agent_id,
            tool_round=tool_round,
            results=results,
            summary={
                "status": "failed" if failed_required else "success",
                "failed_required": failed_required,
                "skipped": [],
            },
        )

    def _build_execution_plan(self, requests: List[ToolRequest]) -> List[List[ToolRequest]]:
        """Topological sort into levels.

        Each level contains requests whose dependencies have already been
        placed in earlier levels.  If a cycle is detected, the remaining
        requests are flushed as a final level to avoid infinite loops.
        """
        req_map = {r.id: r for r in requests}
        pending = set(req_map.keys())
        plan: List[List[ToolRequest]] = []
        while pending:
            level = [
                req_id
                for req_id in list(pending)
                if all(d not in pending for d in req_map[req_id].depends_on)
            ]
            if not level:
                # Circular or broken dependency: flush remaining.
                level = list(pending)
                pending.clear()
            else:
                for req_id in level:
                    pending.discard(req_id)
            plan.append([req_map[r] for r in level if r in req_map])
        return plan

    def _group_by_conflicts(self, requests: List[ToolRequest]) -> List[List[ToolRequest]]:
        """Group requests so that conflicting ones are in separate groups (serialized)."""
        groups: List[List[ToolRequest]] = []
        for req in requests:
            placed = False
            for group in groups:
                if not any(self._conflict(req, other) for other in group):
                    group.append(req)
                    placed = True
                    break
            if not placed:
                groups.append([req])
        return groups

    def _conflict(self, a: ToolRequest, b: ToolRequest) -> bool:
        """Return True if two requests cannot safely run in parallel.

        Conflict is defined as touching the same resource ID with at least
        one write mode.
        """
        res_a = self._infer_resources(a)
        res_b = self._infer_resources(b)
        for ra in res_a:
            for rb in res_b:
                if ra.get("id") == rb.get("id") and ra.get("type") == rb.get("type"):
                    if "write" in (ra.get("mode", ""), rb.get("mode", "")):
                        return True
        return False

    def _infer_resources(self, req: ToolRequest) -> List[Dict[str, Any]]:
        """Derive resources from tool args, falling back to agent-declared resources."""
        if req.resources:
            return req.resources
        if req.tool in {"file_writer", "file_append", "file_delete"}:
            path = req.args.get("path", "")
            return [{"type": "file", "id": str(path), "mode": "write"}]
        if req.tool == "file_reader":
            path = req.args.get("path", "")
            return [{"type": "file", "id": str(path), "mode": "read"}]
        return []

    async def _execute_single(
        self, req: ToolRequest, *, context: Optional[ToolContext] = None
    ) -> ToolResult:
        """Execute one tool request and return a ToolResult."""
        started = time.time()
        try:
            if self.limiter is not None:
                await self.limiter.acquire_tool()
            tool_name = self._resolve_tool_alias(req.tool)
            if tool_name == "recall_context":
                result = self._execute_recall_context(req, context=context)
            else:
                tool = self.core.get_tool(tool_name)
                result = await tool.execute(req.args, context=context)
            duration = int((time.time() - started) * 1000)
            if self.limiter is not None:
                self.limiter.release_tool()
            if tool_name == "command_runner" and isinstance(result, dict) and int(result.get("returncode", 0) or 0) != 0:
                return ToolResult(
                    request_id=req.id,
                    tool=tool_name,
                    status="failed",
                    output=result,
                    error={
                        "type": "CommandFailed",
                        "failure_kind": "runtime_exception",
                        "tool_name": tool_name,
                        "message": result.get("error") or result.get("stderr") or f"command exited with {result.get('returncode')}",
                        "returncode": result.get("returncode"),
                        "stderr": result.get("stderr"),
                        "stdout": result.get("stdout"),
                        "recoverable": True,
                        "retryable": False,
                    },
                    duration_ms=duration,
                )
            return ToolResult(
                request_id=req.id,
                tool=tool_name,
                status="success",
                output=result if isinstance(result, dict) else {"result": str(result)},
                duration_ms=duration,
            )
        except Exception as exc:
            duration = int((time.time() - started) * 1000)
            if self.limiter is not None:
                self.limiter.release_tool()
            classification = classify_failure(exc)
            detail = classification.detail or {}
            return ToolResult(
                request_id=req.id,
                tool=req.tool,
                status="failed",
                error={
                    "type": type(exc).__name__,
                    "failure_kind": classification.failure_kind,
                    "tool_name": detail.get("tool_name") or req.tool,
                    "message": str(exc),
                    "recoverable": True,
                    "retryable": classification.retryable,
                    "suggested_action": classification.suggested_action,
                    **detail,
                },
                duration_ms=duration,
            )

    def _resolve_tool_alias(self, tool_name: str) -> str:
        """Delegate alias resolution to the core's contract validator, if any."""
        validator = getattr(self.core, "tool_contract_validator", None)
        resolver = getattr(validator, "resolve_alias", None)
        if callable(resolver):
            return resolver(tool_name)
        return str(tool_name or "").strip()

    def _execute_recall_context(
        self,
        req: ToolRequest,
        *,
        context: Optional[ToolContext] = None,
    ) -> Dict[str, Any]:
        """Built-in recall_context tool: search an agent's archived context."""
        agent_id = (context.agent_id if context is not None else None) or ""
        if not agent_id:
            agent_id = str(getattr(context, "metadata", {}).get("agent_id", "") if context is not None else "")
        agent = self._resolve_agent(agent_id)
        query = str((req.args or {}).get("query") or (req.args or {}).get("input") or "")
        messages = self._recall_from_agent(agent, query)
        return {
            "found": len(messages),
            "messages": messages,
            "query": query,
        }

    def _resolve_agent(self, agent_id: str) -> Any:
        """Look up an agent by ID through core hooks, tolerating missing agents."""
        if not agent_id:
            return None
        get_blueprint = getattr(self.core, "get_agent_blueprint", None)
        if callable(get_blueprint):
            try:
                return get_blueprint(agent_id)
            except Exception:
                pass
        get_agent = getattr(self.core, "get_agent", None)
        if callable(get_agent):
            try:
                return get_agent(agent_id)
            except Exception:
                pass
        return None

    def _recall_from_agent(self, agent: Any, query: str) -> List[Dict[str, Any]]:
        """Query an agent's context archive and normalise results to plain dicts."""
        if agent is None:
            return []
        recall = getattr(agent, "recall_context", None)
        if callable(recall):
            result = recall(query)
            return [dict(item) for item in (result or []) if isinstance(item, dict)]
        managed_context = getattr(agent, "_context", None)
        retrieve = getattr(managed_context, "retrieve", None)
        if callable(retrieve):
            return [dict(item) for item in (retrieve(query) or []) if isinstance(item, dict)]
        return []
