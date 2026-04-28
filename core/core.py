"""Core module — re-exports the canonical Core runtime class.

The actual implementation lives in ``core.runtime.core_runtime`` so that
runtime internals can be versioned independently of this convenience shim.
"""

from __future__ import annotations

from .runtime.core_runtime import Core

__all__ = ["Core"]
