"""Executor sub-package — graph execution engine components.

Exports the main GraphExecutor that drives an ExecutionGraph through
the runtime.  Protocol and scheduling helpers are internal details.
"""

from .engine import GraphExecutor

__all__ = ["GraphExecutor"]
