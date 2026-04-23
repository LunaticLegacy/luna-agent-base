from __future__ import annotations

from typing import Callable, Optional

from ..results import ExecutionEvent


class ExecutionEventMixin:
    """Event emission helper for graph execution."""

    def _emit(
        self,
        event_sink: Optional[Callable[[ExecutionEvent], None]],
        event: ExecutionEvent,
    ) -> None:
        if event_sink is not None:
            event_sink(event)

