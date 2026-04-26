from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict, Optional

from ..config import AgentConfig
from ..fault_tolerance import ArchitectureRegulation, ArchitectureRegulator, FailureEvent
from ..runtime_info import RuntimeInfoManager
from ..task_graph import TaskGraph
from ..cognitive import CognitiveGraph
from ..policy import ExecutionGraph
from ..swarm_spec import GlobalVariablesConfig
from .cognitive_state import CognitiveRuntimeMixin
from .graph_state import ExecutionGraphStateMixin
from .registry import AgentInstancePool, RuntimeRegistryMixin


class Core(RuntimeRegistryMixin, ExecutionGraphStateMixin, CognitiveRuntimeMixin):
    """Runtime container for agents, tools, execution graphs, and shared state."""

    def __init__(
        self,
        agent_name: str,
        agent_config: AgentConfig,
        workspace_root: Optional[Path] = None,
        limiter: Optional[Any] = None,
    ) -> None:
        self.agent_name = agent_name
        self.agent_config = agent_config
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()
        self.workspace_mode = "workspace"
        self.agents = {}
        self.agent_blueprints = {}
        self.agent_instance_pool = AgentInstancePool(self)
        self.tools = {}
        self.apis = {}
        self.api_sources = {}
        self.tool_capabilities = {}
        self.skills = {}
        self.global_variables = GlobalVariablesConfig()
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
        self.limiter = limiter
        self._tool_scheduler = None
        self._stop_events: Dict[str, threading.Event] = {}
        self._stop_types: Dict[str, str] = {}

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
                "api_count": 0,
                "native_api_count": 0,
                "package_api_count": 0,
                "global_variables": {"values": {}, "visibility": {}},
            }
        state = self._runtime_info.get_graph_state(core=self)
        state["global_variables"] = self.get_global_variables_snapshot()
        state["api_count"] = len(self.apis)
        state["native_api_count"] = sum(
            1 for metadata in self.api_sources.values() if str(metadata.get("origin", "")).strip().lower() == "native"
        )
        state["package_api_count"] = sum(
            1 for metadata in self.api_sources.values() if str(metadata.get("origin", "")).strip().lower() == "package"
        )
        return state

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

    def get_tool_scheduler(self) -> Any:
        """Return or create the ToolScheduler for this core."""
        if self._tool_scheduler is None:
            from core.executor_parts.tool_scheduler import ToolScheduler
            self._tool_scheduler = ToolScheduler(self, self.limiter)
        return self._tool_scheduler

    def register_stop_event(self, run_id: str) -> threading.Event:
        """Register a stop event for a run. Returns the event object."""
        event = threading.Event()
        self._stop_events[run_id] = event
        return event

    def request_stop(self, run_id: str, stop_type: str) -> bool:
        """Request a stop for the given run. stop_type is 'soft' or 'hard'."""
        event = self._stop_events.get(run_id)
        if event is not None:
            self._stop_types[run_id] = stop_type
            event.set()
            return True
        return False

    def check_stop(self, run_id: Optional[str]) -> Optional[str]:
        """Check if a stop has been requested for the run. Returns 'soft', 'hard', or None."""
        if run_id is None:
            return None
        event = self._stop_events.get(run_id)
        if event is not None and event.is_set():
            return self._stop_types.get(run_id)
        return None

    def clear_stop(self, run_id: str) -> None:
        """Clear the stop event for a run."""
        self._stop_events.pop(run_id, None)
        self._stop_types.pop(run_id, None)

    def cleanup_transient_execution_nodes(self, *, graph: Optional[ExecutionGraph] = None) -> list[int]:
        target_graph = graph or self.get_execution_graph()
        if target_graph is None:
            return []
        removed = target_graph.purge_transient_nodes()
        if removed:
            self.record_runtime_change(
                action="graph_remove_node",
                subject_kind="graph",
                subject_id=getattr(target_graph, "graph_name", self.agent_name),
                detail={
                    "graph_node_ids": list(removed),
                    "reason": "transient_cleanup",
                },
            )
            persist = getattr(self, "persist_execution_graph", None)
            if callable(persist):
                persist()
        return removed
