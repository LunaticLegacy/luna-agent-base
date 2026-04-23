from __future__ import annotations

import asyncio
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from core.results import ExecutionEvent

from .record import RunRecord


@dataclass
class RunRegistry:
    """Thread-safe registry for background graph runs."""

    def __init__(self) -> None:
        self._runs: Dict[str, RunRecord] = {}
        self._lock = threading.RLock()

    def launch_run(
        self,
        *,
        swarm_name: str,
        core,
        graph,
        initial_payload: Any,
        rounds: int = 0,
        meta_mode: bool = False,
    ) -> RunRecord:
        """Create a run record and execute the graph in a daemon thread."""
        run_id = uuid.uuid4().hex
        record = RunRecord(run_id=run_id, swarm_name=swarm_name, rounds=rounds)
        with self._lock:
            self._runs[run_id] = record

        thread = threading.Thread(
            target=self._worker,
            kwargs={
                "record": record,
                "swarm_name": swarm_name,
                "core": core,
                "graph": graph,
                "initial_payload": initial_payload,
                "rounds": rounds,
                "meta_mode": meta_mode,
            },
            daemon=True,
            name=f"angelus-run-{run_id[:8]}",
        )
        thread.start()
        return record

    def get_run(self, run_id: str) -> Optional[RunRecord]:
        """Return a run record by id, if present."""
        with self._lock:
            return self._runs.get(run_id)

    def list_runs(self, swarm_name: Optional[str] = None) -> List[RunRecord]:
        """Return run records in insertion order, optionally filtered by swarm."""
        with self._lock:
            runs = list(self._runs.values())
        if swarm_name is None:
            return runs
        return [record for record in runs if record.swarm_name == swarm_name]

    def snapshot(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Return the JSON-ready snapshot for one run."""
        record = self.get_run(run_id)
        if record is None:
            return None
        return record.snapshot()

    def active_run_count(self, swarm_name: Optional[str] = None) -> int:
        """Return the number of active runs, optionally filtered by swarm."""
        with self._lock:
            return sum(
                1
                for record in self._runs.values()
                if not record._done and (swarm_name is None or record.swarm_name == swarm_name)
            )

    def active_run_ids(self, swarm_name: Optional[str] = None) -> List[str]:
        """Return active run ids, optionally filtered by swarm."""
        with self._lock:
            return [
                record.run_id
                for record in self._runs.values()
                if not record._done and (swarm_name is None or record.swarm_name == swarm_name)
            ]

    def _worker(
        self,
        *,
        record: RunRecord,
        swarm_name: str,
        core,
        graph,
        initial_payload: Any,
        rounds: int,
        meta_mode: bool = False,
    ) -> None:
        async def _execute() -> None:
            if meta_mode:
                from core.meta_executor import MetaExecutor

                meta = MetaExecutor(max_iterations=5)
                await meta.run(
                    graph,
                    core,
                    initial_payload,
                    rounds=rounds,
                    run_id=record.run_id,
                    swarm_name=swarm_name,
                    event_sink=record.append_event,
                )
            else:
                await graph.run(
                    core,
                    initial_payload,
                    rounds=rounds,
                    run_id=record.run_id,
                    swarm_name=swarm_name,
                    event_sink=record.append_event,
                )

        try:
            asyncio.run(_execute())
        except Exception as exc:
            if not record._done:
                record.append_event(
                    ExecutionEvent(
                        run_id=record.run_id,
                        swarm_name=swarm_name,
                        event_type="run.failed",
                        rounds=record.rounds,
                        status="failed",
                        data={
                            "error": str(exc),
                            "state_snapshot": record.current_state,
                        },
                    )
                )
