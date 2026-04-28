"""Runtime container for agents, tools, execution graphs, and shared state.

The :class:`Core` class is the central hub of an Angelus swarm.  It inherits
behaviour from three mixins:

* :class:`RuntimeRegistryMixin` — agent / tool / skill / API registration.
* :class:`ExecutionGraphStateMixin` — execution graph lifecycle and persistence.
* :class:`CognitiveRuntimeMixin` — shared cognitive graph operations.

:class:`Core` also owns:

* The :class:`ArchitectureManager` and :class:`ArchitectureRegulator` for
  self-healing graph mutations.
* The :class:`ToolContractValidator` for pre-flight validation.
* Stop-event management for cooperative run cancellation.

Exports:
    - :class:`Core`
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict, Optional

from ..architecture_manager import ArchitectureManager, DEFAULT_ARCHITECTURE_POLICY
from ..config import AgentConfig
from ..fault_tolerance import ArchitectureRegulation, ArchitectureRegulator, FailureEvent
from ..runtime_info import RuntimeInfoManager
from ..cognitive import CognitiveGraph
from ..policy import ExecutionGraph
from ..swarm_spec import GlobalVariablesConfig
from ..tool_contract import ToolContractValidator
from .cognitive_state import CognitiveRuntimeMixin
from .graph_state import ExecutionGraphStateMixin
from .registry import AgentInstancePool, RuntimeRegistryMixin


class Core:
    """Runtime container for agents, tools, execution graphs, and shared state.

    ``Core`` uses **composition** instead of inheritance.  During construction
    it binds every public callable from three delegate mixins onto the
    instance itself, so the external API surface is unchanged while the
    class hierarchy stays flat.

    Attributes:
        agent_name: Name of the swarm package.
        agent_config: Default LLM configuration for agents.
        workspace_root: Filesystem root for the swarm workspace.
        workspace_mode: Access mode (``"workspace"`` or ``"full_access"``).
        agents: Map ``agent_id -> AgentLike``.
        agent_blueprints: Map ``blueprint_ref -> AgentLike``.
        agent_instance_pool: Pool managing agent lifecycle (quarantine, drain, etc.).
        tools: Map ``tool_name -> ToolDefinition``.
        apis: Map ``api_name -> api object``.
        api_sources: Map ``api_name -> {origin, source}`` metadata.
        tool_capabilities: Map ``tool_name -> {capability, ...}``.
        skills: Map ``skill_name -> SkillAsset``.
        global_variables: Swarm-level :class:`GlobalVariablesConfig`.
        architecture_regulator: Policy-driven failure regulator.
        architecture_manager: Self-healing graph patch manager.
        tool_contract_validator: Pre-flight binding validator.
        swarm_cognitive_graph: Shared :class:`CognitiveGraph`.
        active_thought_subgraphs: Map ``subgraph_id -> descriptor``.
        current_run_id: Active run identifier.
        limiter: Global :class:`ConcurrencyLimiter`.
    """

    def __init__(
        self,
        agent_name: str,
        agent_config: AgentConfig,
        workspace_root: Optional[Path] = None,
        limiter: Optional[Any] = None,
    ) -> None:
        """Initialise the runtime core.

        Args:
            agent_name: Name of the swarm package.
            agent_config: Default LLM configuration.
            workspace_root: Optional workspace root (defaults to CWD).
            limiter: Optional global concurrency limiter.
        """
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
        self.architecture_policy = dict(DEFAULT_ARCHITECTURE_POLICY)
        self.architecture_manager = ArchitectureManager(self)
        self.tool_contract_validator = ToolContractValidator()
        self.swarm_cognitive_graph = CognitiveGraph(graph_id=f"swarm_{agent_name}")
        self.active_thought_subgraphs = {}
        self.current_run_id: Optional[str] = None
        self.limiter = limiter
        self._tool_scheduler = None
        self._stop_events: Dict[str, threading.Event] = {}
        self._stop_types: Dict[str, str] = {}

        # Composition over inheritance: bind mixin capabilities onto this instance.
        self._bind_mixin(RuntimeRegistryMixin)
        self._bind_mixin(ExecutionGraphStateMixin)
        self._bind_mixin(CognitiveRuntimeMixin)

    def _bind_mixin(self, mixin_cls: type) -> None:
        """Bind every callable from *mixin_cls* onto this instance.

        This preserves the exact same runtime behaviour and API surface as
        inheritance, but keeps the class hierarchy flat and makes the
        dependency graph explicit.

        Args:
            mixin_cls: A mixin class whose methods should be bound to *self*.
        """
        for name in dir(mixin_cls):
            # Skip dunder methods and attributes already defined by Core itself.
            if name.startswith("__") and name.endswith("__"):
                continue
            if name in self.__class__.__dict__:
                continue
            attr = getattr(mixin_cls, name)
            if callable(attr):
                bound = attr.__get__(self, self.__class__)
                setattr(self, name, bound)

    async def init(self) -> None:
        """Validate the execution graph and tool contracts after construction.

        Raises:
            ValueError: If the graph is invalid or tool-contract validation fails.
        """
        if self._execution_graph is not None:
            validation = self.check_execution_graph_complete()
            if not validation.is_valid:
                raise ValueError("; ".join(validation.errors))
            report = self.tool_contract_validator.validate(self, self._execution_graph)
            if not report.ok:
                self.record_runtime_change(
                    action="tool.contract_validation_failed",
                    subject_kind="graph",
                    subject_id=getattr(self._execution_graph, "graph_name", None),
                    detail=report.to_dict(),
                )
                report.raise_if_failed()

    def set_runtime_info_dir(self, runtime_dir: Path) -> None:
        """Set the directory where runtime snapshots and events are persisted.

        Args:
            runtime_dir: Path to the runtime info directory.
        """
        self._runtime_info_dir = Path(runtime_dir)
        self._runtime_info = RuntimeInfoManager(runtime_dir=runtime_dir, agent_name=self.agent_name)
        self._record_runtime_change(
            action="runtime_info_initialized",
            subject_kind="runtime",
            subject_id=self.agent_name,
            detail={"runtime_dir": str(runtime_dir)},
        )

    def get_runtime_info_dir(self) -> Optional[Path]:
        """Return the runtime info directory, if set."""
        return self._runtime_info_dir

    def _record_runtime_change(
        self,
        *,
        action: str,
        subject_kind: str,
        subject_id: Optional[str] = None,
        detail: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Internal helper: record a runtime change if the info manager is available."""
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
        """Public wrapper around :meth:`_record_runtime_change`.

        This indirection allows subclasses or mixins to override logging
        behaviour without replacing the internal helper.
        """
        self._record_runtime_change(
            action=action,
            subject_kind=subject_kind,
            subject_id=subject_id,
            detail=detail,
        )

    def get_runtime_info_snapshot(self) -> Optional[Dict[str, Any]]:
        """Return the latest runtime snapshot, or ``None`` if not initialised."""
        if self._runtime_info is None:
            return None
        return self._runtime_info._build_snapshot(core=self)  # noqa: SLF001

    def get_graph_runtime_state(self) -> Dict[str, Any]:
        """Return a JSON-serialisable description of the current graph runtime.

        Includes node/edge counts, entry/exit IDs, revision, hash, and API counts.
        """
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
        """Return graph events newer than *since_revision*.

        Args:
            since_revision: Lower bound (exclusive) for event revision.

        Returns:
            List of event dictionaries.
        """
        if self._runtime_info is None:
            return []
        return self._runtime_info.get_graph_events(since_revision=since_revision)

    def get_graph_runtime_diff(self, *, since_revision: int) -> Dict[str, Any]:
        """Return a structural diff of the graph since *since_revision*.

        Args:
            since_revision: Base revision for the diff.

        Returns:
            Dictionary with ``operations``, ``is_gap_free``, and metadata.
        """
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
        """Replace the default architecture regulator.

        Args:
            regulator: New :class:`ArchitectureRegulator` instance.
        """
        self.architecture_regulator = regulator

    def get_architecture_manager(self) -> ArchitectureManager:
        """Return the architecture manager, creating it lazily if needed."""
        manager = getattr(self, "architecture_manager", None)
        if manager is None:
            manager = ArchitectureManager(self)
            self.architecture_manager = manager
        return manager

    def regulate_failure(
        self,
        failure: FailureEvent,
        *,
        graph: Optional[Any] = None,
    ) -> ArchitectureRegulation:
        """Apply architecture regulation to a runtime failure.

        For ``output_parse_error`` failures on nodes with ``auto_repair`` metadata,
        an automatic output-repair patch is proposed and applied.

        Args:
            failure: The failure event to regulate.
            graph: Optional execution graph to target (defaults to the core's graph).

        Returns:
            The :class:`ArchitectureRegulation` produced by the regulator.
        """
        regulator = getattr(self, "architecture_regulator", None)
        if regulator is None:
            regulator = ArchitectureRegulator()
            self.architecture_regulator = regulator
        regulation = regulator.regulate(failure, graph=graph or self.get_execution_graph())
        if failure.failure_kind == "output_parse_error":
            target_graph = graph or self.get_execution_graph()
            failed_node = target_graph.nodes.get(int(failure.node_id)) if target_graph is not None and failure.node_id is not None else None
            metadata = getattr(failed_node, "metadata", {}) if failed_node is not None else {}
            if isinstance(metadata, dict) and metadata.get("auto_repair"):
                manager = self.get_architecture_manager()
                patch = manager.propose_output_repair_patch(failure, graph=target_graph)
                self.record_runtime_change(
                    action="architecture.patch_proposed",
                    subject_kind="graph",
                    subject_id=getattr(target_graph, "graph_name", None),
                    detail={"patch": patch.to_dict(), "failure": failure.to_dict()},
                )
                apply_result = manager.apply_patch_sync(patch, graph=target_graph, author="architecture_regulator")
                regulation.metadata_patch["architecture_patch"] = {
                    "patch_id": patch.patch_id,
                    "applied": apply_result.ok,
                    "errors": list(apply_result.errors),
                }
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
        """Return or create the ToolScheduler for this core.

        The scheduler is instantiated lazily to avoid import-time side effects.

        Returns:
            A :class:`ToolScheduler` instance.
        """
        if self._tool_scheduler is None:
            from core.executor_parts.tool_scheduler import ToolScheduler
            self._tool_scheduler = ToolScheduler(self, self.limiter)
        return self._tool_scheduler

    def register_stop_event(self, run_id: str) -> threading.Event:
        """Register a stop event for a run.

        Args:
            run_id: The run to register.

        Returns:
            A fresh :class:`threading.Event` that callers can set to request a stop.
        """
        event = threading.Event()
        self._stop_events[run_id] = event
        return event

    def request_stop(self, run_id: str, stop_type: str) -> bool:
        """Request a stop for the given run.

        Args:
            run_id: The run to stop.
            stop_type: ``"soft"`` (finish current node) or ``"hard"`` (abort immediately).

        Returns:
            ``True`` if the event existed and was set.
        """
        event = self._stop_events.get(run_id)
        if event is not None:
            self._stop_types[run_id] = stop_type
            event.set()
            return True
        return False

    def check_stop(self, run_id: Optional[str]) -> Optional[str]:
        """Check if a stop has been requested for the run.

        Args:
            run_id: The run to check.

        Returns:
            ``"soft"``, ``"hard"``, or ``None``.
        """
        if run_id is None:
            return None
        event = self._stop_events.get(run_id)
        if event is not None and event.is_set():
            return self._stop_types.get(run_id)
        return None

    def clear_stop(self, run_id: str) -> None:
        """Clear the stop event for a run.

        Args:
            run_id: The run whose stop state should be reset.
        """
        self._stop_events.pop(run_id, None)
        self._stop_types.pop(run_id, None)

    def cleanup_transient_execution_nodes(self, *, graph: Optional[ExecutionGraph] = None) -> list[int]:
        """Remove transient nodes from the graph and optionally persist.

        Args:
            graph: Optional graph to target (defaults to the core's graph).

        Returns:
            List of removed node IDs.
        """
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
