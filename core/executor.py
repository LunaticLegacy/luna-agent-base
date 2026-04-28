"""Executor module — re-exports the graph executor entry-point.

GraphExecutor is the primary orchestrator that walks an ExecutionGraph,
dispatches agent rounds, handles branches, and emits execution events.
The concrete implementation lives in ``core.executor_parts.engine``.
"""

from __future__ import annotations

from .executor_parts.engine import GraphExecutor

__all__ = ["GraphExecutor"]
