from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from web.catalog_parts.observability import build_log_catalog
from web.runstore.record import RunRecord


class RunPersistenceTest(unittest.TestCase):
    def test_run_record_persists_events_and_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage_dir = Path(tmp_dir) / "runtime_info" / "runs" / "run-123"
            record = RunRecord(run_id="run-123", swarm_name="demo")
            record.bind_storage_dir(storage_dir)

            record.append_event(
                {
                    "run_id": "run-123",
                    "swarm_name": "demo",
                    "event_type": "run.started",
                    "timestamp": "2026-04-24T00:00:00Z",
                    "rounds": 1,
                    "data": {"state_snapshot": {"step": "start"}},
                }
            )
            record.append_event(
                {
                    "run_id": "run-123",
                    "swarm_name": "demo",
                    "event_type": "run.completed",
                    "timestamp": "2026-04-24T00:00:01Z",
                    "rounds": 1,
                    "data": {"state_snapshot": {"step": "done"}},
                }
            )

            events_path = storage_dir / "events.jsonl"
            snapshot_path = storage_dir / "current.json"
            self.assertTrue(events_path.exists())
            self.assertTrue(snapshot_path.exists())

            events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(len(events), 2)
            self.assertEqual(events[-1]["event_type"], "run.completed")

            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            self.assertEqual(snapshot["status"], "completed")
            self.assertEqual(snapshot["event_count"], 2)

    def test_log_catalog_includes_persisted_run_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            package_path = Path(tmp_dir) / "demo"
            events_path = package_path / "runtime_info" / "runs" / "run-abc" / "events.jsonl"
            events_path.parent.mkdir(parents=True, exist_ok=True)
            events_path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "run_id": "run-abc",
                                "swarm_name": "demo",
                                "event_type": "run.started",
                                "timestamp": "2026-04-24T00:00:00Z",
                                "rounds": 1,
                                "data": {"state_snapshot": {"step": "start"}},
                            },
                            ensure_ascii=False,
                        )
                    ]
                ),
                encoding="utf-8",
            )

            registry = SimpleNamespace(
                swarms={
                    "demo": SimpleNamespace(
                        manifest=SimpleNamespace(swarm_name="demo"),
                        package_path=package_path,
                    )
                },
                runs=SimpleNamespace(list_runs=lambda swarm_name=None: []),
            )

            payload = build_log_catalog(registry)
            self.assertEqual(payload["total"], 1)
            item = payload["items"][0]
            self.assertEqual(item["service"], "demo")
            self.assertEqual(item["raw"]["raw_event"]["run_id"], "run-abc")
            self.assertTrue(str(item["raw"]["file"]).endswith("events.jsonl"))


if __name__ == "__main__":
    unittest.main()
