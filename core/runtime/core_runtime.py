from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from ..config import AgentConfig
from ..fault_tolerance import ArchitectureRegulation, ArchitectureRegulator, FailureEvent
from ..runtime_info import RuntimeInfoManager
from ..task_graph import TaskGraph
from ..cognitive import CognitiveGraph
from .cognitive_state import CognitiveRuntimeMixin
from .graph_state import ExecutionGraphStateMixin
from .registry import RuntimeRegistryMixin


class Core(RuntimeRegistryMixin, ExecutionGraphStateMixin, CognitiveRuntimeMixin):
    """Runtime container for agents, tools, execution graphs, and shared state."""

    def __init__(
        self,
        agent_name: str,
        agent_config: AgentConfig,
        workspace_root: Optional[Path] = None,
    ) -> None:
        self.agent_name = agent_name
        self.agent_config = agent_config
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()
        self.workspace_mode = "workspace"
        self.agents = {}
        self.tools = {}
        self.tool_capabilities = {}
        self.skills = {}
        self._execution_graph = None
        self._execution_graph_source_path = None
        self._execution_graph_backup_path = None
        self._runtime_info: Optional[RuntimeInfoManager] = None
        self._runtime_info_dir: Optional[Path] = None
        self.architecture_regulator = ArchitectureRegulator()
        self.swarm_cognitive_graph = CognitiveGraph(graph_id=f"swarm_{agent_name}")
        self.active_thought_subgraphs = {}
        self.current_run_id: Optional[str] = None
        self.task_graph: Optional[TaskGraph] = None
        self._task_graph_path: Optional[Path] = None

    async def init(self) -> None:
        if self._execution_graph is not None:
            self.check_execution_graph_complete()

    def set_runtime_info_dir(self, runtime_dir: Path) -> None:
        self._runtime_info_dir = Path(runtime_dir)
        self._runtime_info = RuntimeInfoManager(runtime_dir=runtime_dir, agent_name=self.agent_name)
        self._record_runtime_change(
            action="runtime_info_initialized",
            subject_kind="runtime",
            subject_id=self.agent_name,
            detail={"runtime_dir": str(runtime_dir)},
        )

    def get_runtime_info_dir(self) -> Optional[Path]:
        return self._runtime_info_dir

    def set_task_graph(self, task_graph: TaskGraph, *, persist_path: Optional[Path] = None) -> None:
        self.task_graph = task_graph
        self._task_graph_path = persist_path
        self._record_runtime_change(
            action="set_task_graph",
            subject_kind="task_graph",
            subject_id=task_graph.graph_id,
            detail={"task_count": len(task_graph.tasks)},
        )

    def persist_task_graph(self) -> None:
        if self.task_graph is not None and self._task_graph_path is not None:
            self.task_graph.save(self._task_graph_path)

    def get_task_graph(self) -> Optional[TaskGraph]:
        return self.task_graph

    def _record_runtime_change(
        self,
        *,
        action: str,
        subject_kind: str,
        subject_id: Optional[str] = None,
        detail: Optional[Dict[str, Any]] = None,
    ) -> None:
        if self._runtime_info is None:
            return
        self._runtime_info.record(
            action=action,
            subject_kind=subject_kind,
            subject_id=subject_id,
            detail=detail,
            core=self,
        )

    def record_runtime_change(
        self,
        *,
        action: str,
        subject_kind: str,
        subject_id: Optional[str] = None,
        detail: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._record_runtime_change(
            action=action,
            subject_kind=subject_kind,
            subject_id=subject_id,
            detail=detail,
        )

    def get_runtime_info_snapshot(self) -> Optional[Dict[str, Any]]:
        if self._runtime_info is None:
            return None
        return self._runtime_info._build_snapshot(core=self)  # noqa: SLF001

    def get_graph_runtime_state(self) -> Dict[str, Any]:
        if self._runtime_info is None:
            return {
                "graph_name": None,
                "entry_node_id": None,
                "exit_node_id": None,
                "node_count": 0,
                "edge_count": 0,
                "nodes": [],
                "edges": [],
                "revision": 0,
                "hash": "",
                "updated_at": "",
                "last_change": None,
            }
        return self._runtime_info.get_graph_state(core=self)

    def get_graph_runtime_events(self, *, since_revision: int = 0) -> list[Dict[str, Any]]:
        if self._runtime_info is None:
            return []
        return self._runtime_info.get_graph_events(since_revision=since_revision)

    def get_graph_runtime_diff(self, *, since_revision: int) -> Dict[str, Any]:
        if self._runtime_info is None:
            return {
                "base_revision": since_revision,
                "current_revision": 0,
                "graph_id": None,
                "is_gap_free": True,
                "operations": [],
                "last_change": None,
            }
        return self._runtime_info.get_graph_diff(since_revision=since_revision, core=self)

    def register_architecture_regulator(self, regulator: ArchitectureRegulator) -> None:
        self.architecture_regulator = regulator

    def regulate_failure(
        self,
        failure: FailureEvent,
        *,
        graph: Optional[Any] = None,
    ) -> ArchitectureRegulation:
        regulator = getattr(self, "architecture_regulator", None)
        if regulator is None:
            regulator = ArchitectureRegulator()
            self.architecture_regulator = regulator
        regulation = regulator.regulate(failure, graph=graph or self.get_execution_graph())
        subject_kind = "graph" if failure.failure_scope in {"node", "branch", "graph", "swarm"} else "runtime"
        subject_id = str(failure.node_id) if failure.node_id is not None else failure.run_id or self.agent_name
        self.record_runtime_change(
            action="architecture_adjusted",
            subject_kind=subject_kind,
            subject_id=subject_id,
            detail={
                "failure": failure.to_dict(),
                "regulation": regulation.to_dict(),
            },
        )
        return regulation
