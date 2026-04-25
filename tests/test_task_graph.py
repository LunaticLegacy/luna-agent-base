from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from core.task_graph import Task, TaskGraph
from web.task_store import TaskStore


TEST_TMP_ROOT = Path(__file__).resolve().parent / ".artifacts"
TEST_TMP_ROOT.mkdir(exist_ok=True)


def make_test_dir(name: str) -> Path:
    path = (TEST_TMP_ROOT / name).resolve()
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


class TaskGraphTest(unittest.TestCase):
    def test_task_graph_semantics(self) -> None:
        graph = TaskGraph(graph_id="tasks_demo")
        root = graph.add_task(Task(task_id="root", name="root", status="success"))
        child = graph.add_task(Task(task_id="child", name="child", dependencies=["root"]))
        leaf = graph.add_task(Task(task_id="leaf", name="leaf", dependencies=["child"]))
        graph.link_tasks("child", "leaf")

        self.assertEqual(root.status, "success")
        self.assertEqual([task.task_id for task in graph.ready_tasks()], ["child"])
        self.assertEqual([task.task_id for task in graph.blocked_tasks()], ["leaf"])

        graph.transition_task("child", status="running", agent_id="planner")
        graph.transition_task("child", status="success", output={"ok": True})
        self.assertEqual(graph.get_task("child").completed_count, 1)
        self.assertTrue(graph.get_task("child").is_terminal())
        self.assertEqual([task.task_id for task in graph.ready_tasks()], ["leaf"])

        snapshot = graph.snapshot()
        self.assertEqual(snapshot["summary"]["task_count"], 3)
        self.assertEqual(snapshot["summary"]["edge_count"], 2)
        self.assertIn("leaf", snapshot["summary"]["ready_task_ids"])
        self.assertIn({"from_task_id": "child", "to_task_id": "leaf"}, snapshot["edges"])

        with self.assertRaises(ValueError):
            graph.transition_task("child", status="running")

    def test_task_store_claims_ready_tasks(self) -> None:
        data_dir = make_test_dir("task_store_claims_ready")
        store = TaskStore(data_dir=data_dir)
        graph = store.get_graph("demo")
        graph.add_task(Task(task_id="a", name="a", status="success", swarm_name="demo"))
        graph.add_task(Task(task_id="b", name="b", swarm_name="demo", dependencies=["a"]))
        claimed = store.claim_ready_tasks("demo", agent_id="planner")

        self.assertEqual([task.task_id for task in claimed], ["b"])
        self.assertEqual(store.get_task("demo", "b").status, "running")
        graph_snapshot = store.get_graph_snapshot("demo")
        self.assertEqual(graph_snapshot["summary"]["status_counts"]["running"], 1)
        shutil.rmtree(data_dir)


if __name__ == "__main__":
    unittest.main()
