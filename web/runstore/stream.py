from __future__ import annotations

import json
from typing import Iterator

from .record import RunRecord


def stream_run_events(record: RunRecord, *, after: int = 0) -> Iterator[str]:
    """Create an SSE stream for one run record."""
    yield f"event: run.snapshot\n"
    yield f"data: {json.dumps(record.snapshot(), ensure_ascii=False)}\n\n"
    yield from record.stream_events(after=after)
