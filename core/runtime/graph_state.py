from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from ..results import GraphValidationResult

if TYPE_CHECKING:
    from ..policy import ExecutionGraph


class ExecutionGraphStateMixin:
    """Execution graph lifecycle helpers for a runtime core."""

    def set_execution_graph(self, graph: "ExecutionGraph") -> None:
        self._execution_graph = graph
        self._record_runtime_change(
            action="set_execution_graph",
            subject_kind="graph",
            subject_id=getattr(graph, "graph_name", None),
            detail={
                "entry_node_id": getattr(graph, "entry_node_id", None),
                "exit_node_id": getattr(graph, "exit_node_id", None),
            },
        )

    def set_execution_graph_artifacts(self, *, source_path: Path, backup_path: Path) -> None:
        self._execution_graph_source_path = Path(source_path)
        self._execution_graph_backup_path = Path(backup_path)

    def ensure_execution_graph_backup(self, *, overwrite: bool = False) -> Optional[Path]:
        source_path = self._execution_graph_source_path
        backup_path = self._execution_graph_backup_path
        if source_path is None or backup_path is None:
            return None
        if not source_path.exists():
            return None
        if backup_path.exists() and not overwrite:
            return backup_path
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, backup_path)
        return backup_path

    def persist_execution_graph(self) -> Optional[Path]:
        graph = self._execution_graph
        source_path = self._execution_graph_source_path
        if graph is None or source_path is None:
            return None

        self.ensure_execution_graph_backup()
        source_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = source_path.with_suffix(".tmp")
        tmp_path.write_text(graph.to_python_source(), encoding="utf-8")
        tmp_path.replace(source_path)
        return source_path

    def get_execution_graph(self) -> Optional["ExecutionGraph"]:
        return self._execution_graph

    def get_agent_graph(self) -> Optional["ExecutionGraph"]:
        graph = self._execution_graph
        if graph is None:
            return None
        return graph.to_agent_graph()

    def get_agent_graph_snapshot(self) -> dict:
        graph = self.get_agent_graph()
        if graph is None:
            return {
                "graph_name": None,
                "graph_kind": "agent",
                "entry_node_id": None,
                "exit_node_id": None,
                "node_count": 0,
                "edge_count": 0,
                "nodes": [],
                "edges": [],
            }
        from web.runs import serialize_graph_snapshot

        return serialize_graph_snapshot(graph)

    def check_execution_graph_available(self) -> GraphValidationResult:
        if self._execution_graph is None:
            return GraphValidationResult(
                is_valid=False,
                errors=["Execution graph is not attached."],
            )
        return self._execution_graph.validate(self)

    def check_execution_graph_complete(self) -> GraphValidationResult:
        if self._execution_graph is None:
            return GraphValidationResult(
                is_valid=False,
                errors=["Execution graph is not attached."],
            )
        return self._execution_graph.validate(self)
