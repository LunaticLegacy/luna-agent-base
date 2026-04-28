"""Angelus runtime core package.

Re-exports the primary :class:`Core` class so that consumers can simply
``from core.runtime import Core``.

Exports:
    - :class:`Core`
"""

from .core_runtime import Core

__all__ = ["Core"]
