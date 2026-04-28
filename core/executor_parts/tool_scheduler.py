from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

from core.results import ToolBatchResult, ToolRequest, ToolResult
from core.toodefl import ToolContext


class ToolScheduler:
    """External tool scheduler for Tool Request Protocol v1."""

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
        """Execute a batch of tool requests respecting DAG and resource conflicts."""
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
        """Topological sort into levels."""
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
        """Return True if two requests cannot safely run in parallel."""
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
            tool = self.core.get_tool(req.tool)
            result = await tool.execute(req.args, context=context)
            duration = int((time.time() - started) * 1000)
            if self.limiter is not None:
                self.limiter.release_tool()
            return ToolResult(
                request_id=req.id,
                tool=req.tool,
                status="success",
                output=result if isinstance(result, dict) else {"result": str(result)},
                duration_ms=duration,
            )
        except Exception as exc:
            duration = int((time.time() - started) * 1000)
            if self.limiter is not None:
                self.limiter.release_tool()
            return ToolResult(
                request_id=req.id,
                tool=req.tool,
                status="failed",
                error={
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "recoverable": True,
                    "retryable": False,
                },
                duration_ms=duration,
            )
