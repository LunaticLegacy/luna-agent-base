"""Declarative architecture patch manager.

``ArchitectureManager`` validates and applies ``ArchitecturePatch`` objects
to an ``ExecutionGraph`` under a configurable policy.  It supports:
    * Pre-flight validation (structural, policy, and graph-level checks).
    * Transactional application via ``GraphTransaction``.
    * Rollback to pre-patch state.
    * Automatic generation of output-repairer patches for parse failures.

The default policy limits graph size and disables dangerous capabilities
such as prompt mutation or tool permission escalation unless explicitly
allowed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .architecture_patch import ArchitecturePatch, SUPPORTED_ARCHITECTURE_OPS
from .errors import ArchitecturePatchError
from .graph_transaction import GraphMutationRecord, GraphTransaction
from .policy import AgentNode, ExecutionGraph, ToolNode


DEFAULT_ARCHITECTURE_POLICY = {
    "dynamic": True,
    "max_agents": 12,
    "max_edges": 32,
    "max_depth": 6,
    "max_rewrites_per_run": 3,
    "allow_prompt_mutation": False,
    "allow_tool_permission_escalation": False,
    "allow_runtime_mutation": False,
}


@dataclass
class PatchValidationResult:
    """Outcome of validating an architecture patch.

    Attributes:
        ok: Whether the patch passed all checks.
        errors: Blocking issues.
        warnings: Non-blocking issues.
        patch: The parsed ArchitecturePatch (available even if validation failed).
    """

    ok: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    patch: Optional[ArchitecturePatch] = None


@dataclass
class PatchApplyResult:
    """Outcome of applying an architecture patch.

    Attributes:
        ok: Whether the patch was committed.
        patch_id: Identifier of the patch.
        graph: The mutated ExecutionGraph (same object identity).
        errors: Blocking issues that prevented application.
        applied_operations: Serialised record of what changed.
    """

    ok: bool
    patch_id: str
    graph: Optional[ExecutionGraph] = None
    errors: List[str] = field(default_factory=list)
    applied_operations: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class PatchRollbackResult:
    """Outcome of rolling back an architecture patch.

    Attributes:
        ok: Whether the rollback succeeded.
        patch_id: Identifier of the patch.
        errors: Issues that prevented rollback.
    """

    ok: bool
    patch_id: str
    errors: List[str] = field(default_factory=list)


class ArchitectureManager:
    """Validate and transactionally apply declarative architecture patches.

    Attributes:
        core: Back-reference to the runtime Core.
        rollback_records: Mapping from patch_id to pre-patch snapshot data.
    """

    def __init__(self, core: Any) -> None:
        self.core = core
        self.rollback_records: Dict[str, Dict[str, Any]] = {}

    def policy(self) -> Dict[str, Any]:
        """Return the merged architecture policy (defaults + core overrides)."""
        raw = getattr(self.core, "architecture_policy", None)
        result = dict(DEFAULT_ARCHITECTURE_POLICY)
        if isinstance(raw, dict):
            result.update(raw)
        return result

    def validate_patch(self, patch: Any, graph: Optional[ExecutionGraph] = None) -> PatchValidationResult:
        """Run all validation layers against *patch*.

        Checks performed:
            1. Structural (patch_id, scope, operations presence).
            2. Policy (dynamic enabled, size limits).
            3. Per-operation semantics (unknown agents, duplicate IDs, etc.).
            4. Trial application + graph validation.
            5. Reachability and depth constraints.

        Args:
            patch: Raw dict or ArchitecturePatch instance.
            graph: Optional graph to validate against; defaults to core's graph.

        Returns:
            PatchValidationResult with errors/warnings populated.
        """
        # 1. Parse and pre-flight checks -------------------------------------
        parsed, errors, warnings, target_graph = self._parse_and_preflight(patch, graph)
        if parsed is None:
            return PatchValidationResult(ok=False, errors=errors, warnings=warnings)
        if target_graph is None:
            return PatchValidationResult(ok=False, errors=errors, warnings=warnings, patch=parsed)
        if errors:
            return PatchValidationResult(ok=False, errors=errors, warnings=warnings, patch=parsed)

        # 2. Per-operation semantics -----------------------------------------
        errors, warnings, created_agents = self._validate_operation_semantics(
            parsed, target_graph, errors, warnings
        )

        # 3. Global policy limits --------------------------------------------
        policy = self.policy()
        errors = self._check_graph_policy_limits(created_agents, target_graph, policy, errors)

        if errors:
            return PatchValidationResult(ok=False, errors=errors, warnings=warnings, patch=parsed)

        # 4. Trial application + graph-level validation ----------------------
        errors, warnings = self._trial_apply_and_validate(
            parsed, target_graph, policy, created_agents, errors, warnings
        )

        return PatchValidationResult(ok=not errors, errors=errors, warnings=warnings, patch=parsed)

    def _parse_and_preflight(
        self,
        patch: Any,
        graph: Optional[ExecutionGraph],
    ) -> tuple:
        """Coerce *patch* to an ArchitecturePatch and run structural pre-flight checks.

        Args:
            patch: Raw dict or ArchitecturePatch instance.
            graph: Optional graph to validate against.

        Returns:
            A tuple of *(parsed, errors, warnings, target_graph)*.
            *parsed* is ``None`` when coercion fails.
            *target_graph* is ``None`` when no graph is attached.
        """
        try:
            parsed = ArchitecturePatch.coerce(patch)
        except Exception as exc:
            return None, [str(exc)], [], None

        errors: List[str] = []
        warnings: List[str] = []
        if not parsed.patch_id:
            errors.append("patch_id is required.")
        if parsed.scope != "package":
            errors.append("Only package-scoped architecture patches are supported.")
        if not parsed.operations:
            errors.append("operations must not be empty.")

        policy = self.policy()
        if not policy.get("dynamic", True):
            errors.append("Dynamic architecture patches are disabled by policy.")

        target_graph = graph or self.core.get_execution_graph()
        if target_graph is None:
            errors.append("No execution graph attached.")

        return parsed, errors, warnings, target_graph

    def _validate_operation_semantics(
        self,
        parsed: ArchitecturePatch,
        target_graph: ExecutionGraph,
        errors: List[str],
        warnings: List[str],
    ) -> tuple:
        """Validate every operation in *parsed* against *target_graph* semantics.

        Tracks ``created_agents`` so that trial-application errors referencing
        not-yet-created agents can be filtered later.

        Args:
            parsed: The coerced ArchitecturePatch.
            target_graph: The graph to validate against.
            errors: Accumulated error list (mutated in-place).
            warnings: Accumulated warning list (mutated in-place).

        Returns:
            A tuple of *(errors, warnings, created_agents)*.
        """
        created_agents: set[str] = set()
        created_node_refs: set[str] = set()
        working = target_graph.clone()

        for operation in parsed.operations:
            if operation.op not in SUPPORTED_ARCHITECTURE_OPS:
                errors.append(f"Unsupported architecture op: {operation.op}")
                continue
            payload = operation.payload
            if operation.op == "add_agent":
                agent_id = str(payload.get("agent_id") or "").strip()
                if not agent_id:
                    errors.append("add_agent requires agent_id.")
                if payload.get("workspace_mode") == "full_access":
                    errors.append("add_agent cannot escalate workspace_mode to full_access.")
                if payload.get("tools"):
                    errors.append("add_agent via architecture_patch cannot grant tools in this stage.")
                created_agents.add(agent_id)
            elif operation.op in {"add_agent_node", "add_tool_node"}:
                node_ref = str(payload.get("node_name") or payload.get("node_ref") or "").strip()
                if node_ref:
                    created_node_refs.add(node_ref)
                node_id = payload.get("node_id")
                if node_id not in (None, "auto"):
                    try:
                        int_node_id = int(node_id)
                    except Exception:
                        errors.append(f"{operation.op} node_id must be int or auto.")
                    else:
                        if int_node_id in working.nodes:
                            errors.append(f"Duplicate node_id {int_node_id}.")
                if operation.op == "add_agent_node":
                    agent_id = str(payload.get("agent_id") or payload.get("blueprint_ref") or "").strip()
                    if agent_id not in created_agents and not self._agent_exists(agent_id):
                        errors.append(f"add_agent_node references unknown agent '{agent_id}'.")
                else:
                    tool_name = str(payload.get("tool_name") or "").strip()
                    if tool_name not in getattr(self.core, "tools", {}):
                        errors.append(f"add_tool_node references unknown tool '{tool_name}'.")
            elif operation.op in {"remove_node", "update_node_metadata", "update_route", "update_retry_policy", "update_output_mode"}:
                node_id = self._payload_node_id(payload)
                if node_id not in working.nodes:
                    errors.append(f"{operation.op} references missing node {node_id}.")
            elif operation.op == "insert_after":
                target_node_id = self._int_or_none(payload.get("target_node_id"))
                if target_node_id not in working.nodes:
                    errors.append(f"insert_after references missing target_node_id {target_node_id}.")
                new_ref = str(payload.get("new_node_ref") or "").strip()
                if new_ref not in created_node_refs and not self._node_ref_exists(working, new_ref):
                    errors.append(f"insert_after references unknown new_node_ref '{new_ref}'.")
            elif operation.op in {"add_edge", "remove_edge", "replace_next"}:
                from_id = self._int_or_none(payload.get("from_node_id"))
                if from_id not in working.nodes:
                    errors.append(f"{operation.op} references missing from_node_id {from_id}.")
                ids = payload.get("to_node_ids") if operation.op == "replace_next" else [payload.get("to_node_id")]
                for raw_id in ids or []:
                    to_id = self._int_or_none(raw_id)
                    if to_id not in working.nodes:
                        errors.append(f"{operation.op} references missing to_node_id {to_id}.")

        return errors, warnings, created_agents

    def _check_graph_policy_limits(
        self,
        created_agents: set[str],
        working_graph: ExecutionGraph,
        policy: Dict[str, Any],
        errors: List[str],
    ) -> List[str]:
        """Enforce global policy limits (max_agents, max_edges).

        Args:
            created_agents: Agent IDs that would be created by the patch.
            working_graph: A cloned graph reflecting the patch's node changes.
            policy: Merged architecture policy.
            errors: Accumulated error list (mutated in-place).

        Returns:
            The updated *errors* list.
        """
        if len(getattr(self.core, "agents", {}) or {}) + len(created_agents) > int(policy.get("max_agents", 12)):
            errors.append("Patch would exceed max_agents policy.")
        if len(working_graph.edges) > int(policy.get("max_edges", 32)):
            errors.append("Graph already exceeds max_edges policy.")
        return errors

    def _trial_apply_and_validate(
        self,
        parsed: ArchitecturePatch,
        target_graph: ExecutionGraph,
        policy: Dict[str, Any],
        created_agents: set[str],
        errors: List[str],
        warnings: List[str],
    ) -> tuple:
        """Trial-apply the patch to a cloned graph and run graph-level validation.

        Checks reachability, depth, cycles, and edge count after mutation.
        Errors mentioning agents that the patch itself creates are filtered
        out because those agents do not exist during validation.

        Args:
            parsed: The coerced ArchitecturePatch.
            target_graph: The original graph (cloned before trial application).
            policy: Merged architecture policy.
            created_agents: Agent IDs created by the patch.
            errors: Accumulated error list (mutated in-place).
            warnings: Accumulated warning list (mutated in-place).

        Returns:
            A tuple of *(errors, warnings)*.
        """
        try:
            trial = target_graph.clone()
            self._apply_operations_to_graph(parsed, trial, commit_agents=False)
            graph_validation = trial.validate(self.core)
            if not graph_validation.is_valid:
                for error in graph_validation.errors:
                    if any(f"'{agent_id}'" in error for agent_id in created_agents):
                        continue
                    errors.append(error)
            warnings.extend(graph_validation.warnings)
            if len(trial.edges) > int(policy.get("max_edges", 32)):
                errors.append("Patch would exceed max_edges policy.")
            if not self._entry_reaches_nodes(trial):
                errors.append("Patch would leave graph with a dead or unreachable entry.")
            if self._max_depth(trial) > int(policy.get("max_depth", 6)):
                errors.append("Patch would exceed max_depth policy.")
            if self._has_cycle(trial):
                errors.append("Patch would create an uncontrolled cycle.")
        except Exception as exc:
            errors.append(str(exc))
        return errors, warnings


    async def apply_patch(self, patch: Any, graph: Optional[ExecutionGraph] = None, *, author: Optional[str] = None) -> PatchApplyResult:
        """Asynchronously apply a validated patch via GraphTransaction."""
        return await self._apply_patch(patch, graph=graph, author=author)

    def apply_patch_sync(self, patch: Any, graph: Optional[ExecutionGraph] = None, *, author: Optional[str] = None) -> PatchApplyResult:
        """Synchronous wrapper that routes to the appropriate event loop path.

        If called from inside a running event loop (e.g. within the executor),
        it bypasses asyncio.run and applies the mutation directly to avoid
        nested-loop errors.
        """
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._apply_patch(patch, graph=graph, author=author))
        if loop.is_running():
            # Synchronous regulation path inside executor: apply graph mutation directly.
            return self._apply_patch_direct(patch, graph=graph, author=author)
        return loop.run_until_complete(self._apply_patch(patch, graph=graph, author=author))

    async def rollback_patch(self, patch_id: str, graph: Optional[ExecutionGraph] = None) -> PatchRollbackResult:
        """Async alias for rollback_patch_sync."""
        return self.rollback_patch_sync(patch_id, graph=graph)

    def rollback_patch_sync(self, patch_id: str, graph: Optional[ExecutionGraph] = None) -> PatchRollbackResult:
        """Restore the graph to its pre-patch state and destroy any agents created by the patch."""
        record = self.rollback_records.get(patch_id)
        if record is None:
            return PatchRollbackResult(ok=False, patch_id=patch_id, errors=["Unknown patch_id."])
        target_graph = graph or self.core.get_execution_graph()
        if target_graph is None:
            return PatchRollbackResult(ok=False, patch_id=patch_id, errors=["No execution graph attached."])
        previous = record["graph"]
        GraphTransaction._copy_graph_state(target_graph, previous)
        for agent_id in record.get("created_agents", []):
            if agent_id in getattr(self.core, "agents", {}):
                self.core.destroy_agent(agent_id)
        self.core.record_runtime_change(
            action="architecture.patch_rolled_back",
            subject_kind="graph",
            subject_id=target_graph.graph_name,
            detail={"patch_id": patch_id},
        )
        return PatchRollbackResult(ok=True, patch_id=patch_id)

    def propose_output_repair_patch(self, failure: Any, graph: Optional[ExecutionGraph] = None) -> ArchitecturePatch:
        """Generate a standard output-repairer patch for a structured-output parse failure.

        The patch inserts a transient ``output_repairer`` node immediately
        after the failing node so that malformed JSON can be corrected
        without restarting the run.
        """
        node_id = getattr(failure, "node_id", None)
        return ArchitecturePatch.from_dict({
            "patch_id": f"patch-output-repairer-{node_id or 'unknown'}",
            "reason": getattr(failure, "message", "") or "structured output parse failed",
            "scope": "package",
            "operations": [
                {
                    "op": "add_agent",
                    "agent_id": "output_repairer",
                    "name": "Output Repairer",
                    "character_prompt": "Repair malformed structured outputs. Do not execute tools.",
                    "tools": [],
                    "tool_execution_mode": "disabled",
                },
                {
                    "op": "add_agent_node",
                    "node_id": "auto",
                    "node_name": "output_repairer_node",
                    "agent_id": "output_repairer",
                    "persistence": "transient",
                    "lifetime_policy": "run",
                    "metadata": {"output_mode": "json_optional"},
                },
                {
                    "op": "insert_after",
                    "target_node_id": node_id,
                    "new_node_ref": "output_repairer_node",
                    "preserve_downstream": True,
                },
            ],
            "rollback": {"action": "revert_patch"},
        })

    async def _apply_patch(self, patch: Any, graph: Optional[ExecutionGraph], author: Optional[str]) -> PatchApplyResult:
        target_graph = graph or self.core.get_execution_graph()
        validation = self.validate_patch(patch, graph=target_graph)
        parsed = validation.patch or ArchitecturePatch.coerce(patch)
        self._record("architecture.patch_validated" if validation.ok else "architecture.patch_rejected", target_graph, parsed, {"errors": validation.errors, "warnings": validation.warnings})
        if not validation.ok:
            return PatchApplyResult(ok=False, patch_id=parsed.patch_id, graph=target_graph, errors=validation.errors)
        assert target_graph is not None
        previous = target_graph.clone()
        created_agents = self._created_agents(parsed)
        transaction = GraphTransaction(target_graph, core=self.core)
        transaction.prepare(
            GraphMutationRecord(action="architecture_patch", detail=parsed.to_dict(), author=author or "architecture_manager", reason=parsed.reason),
            lambda working: self._apply_operations_to_graph(parsed, working, commit_agents=True),
        )
        await transaction.commit()
        self.rollback_records[parsed.patch_id] = {"graph": previous, "created_agents": created_agents}
        self._record("architecture.patch_applied", target_graph, parsed, {"operations": [op.to_dict() for op in parsed.operations]})
        return PatchApplyResult(ok=True, patch_id=parsed.patch_id, graph=target_graph, applied_operations=[op.to_dict() for op in parsed.operations])

    def _apply_patch_direct(self, patch: Any, graph: Optional[ExecutionGraph], author: Optional[str]) -> PatchApplyResult:
        """Direct (non-transactional) path used when asyncio is already running.

        Skips GraphTransaction.commit() to avoid deadlock inside the executor.
        """
        target_graph = graph or self.core.get_execution_graph()
        validation = self.validate_patch(patch, graph=target_graph)
        parsed = validation.patch or ArchitecturePatch.coerce(patch)
        self._record("architecture.patch_validated" if validation.ok else "architecture.patch_rejected", target_graph, parsed, {"errors": validation.errors})
        if not validation.ok or target_graph is None:
            return PatchApplyResult(ok=False, patch_id=parsed.patch_id, graph=target_graph, errors=validation.errors)
        previous = target_graph.clone()
        self._apply_operations_to_graph(parsed, target_graph, commit_agents=True)
        self.rollback_records[parsed.patch_id] = {"graph": previous, "created_agents": self._created_agents(parsed)}
        self._record("architecture.patch_applied", target_graph, parsed, {"operations": [op.to_dict() for op in parsed.operations]})
        return PatchApplyResult(ok=True, patch_id=parsed.patch_id, graph=target_graph, applied_operations=[op.to_dict() for op in parsed.operations])

    def _apply_operations_to_graph(self, patch: ArchitecturePatch, graph: ExecutionGraph, *, commit_agents: bool) -> None:
        """Execute every operation in *patch* against *graph*.

        When *commit_agents* is False (validation trial run), agent creation
        is skipped so that the trial does not mutate core state.
        """
        node_refs: Dict[str, int] = {}
        for operation in patch.operations:
            p = operation.payload
            if operation.op == "add_agent":
                if commit_agents and not self._agent_exists(str(p.get("agent_id"))):
                    self._create_patch_agent(p)
            elif operation.op == "remove_agent":
                if commit_agents:
                    self.core.destroy_agent(str(p.get("agent_id")))
            elif operation.op == "add_agent_node":
                node_id = self._resolve_new_node_id(graph, p.get("node_id"))
                metadata = self._node_lifecycle_metadata(p)
                metadata.update(dict(p.get("metadata", {}) or {}))
                node = AgentNode(
                    node_id=node_id,
                    node_name=str(p.get("node_name") or f"agent_{node_id}"),
                    blueprint_ref=str(p.get("agent_id") or p.get("blueprint_ref") or ""),
                    additional_prompt=p.get("additional_prompt"),
                    metadata=metadata,
                )
                graph.add_node(node)
                node_refs[node.node_name] = node_id
            elif operation.op == "add_tool_node":
                node_id = self._resolve_new_node_id(graph, p.get("node_id"))
                metadata = self._node_lifecycle_metadata(p)
                metadata.update(dict(p.get("metadata", {}) or {}))
                node = ToolNode(
                    node_id=node_id,
                    node_name=str(p.get("node_name") or f"tool_{node_id}"),
                    tool_name=str(p.get("tool_name") or ""),
                    input_mapping=dict(p.get("input_mapping", {}) or {}),
                    metadata=metadata,
                )
                graph.add_node(node)
                node_refs[node.node_name] = node_id
            elif operation.op == "insert_after":
                target_id = int(p.get("target_node_id"))
                new_id = node_refs.get(str(p.get("new_node_ref"))) or self._node_ref_id(graph, str(p.get("new_node_ref")))
                if new_id is None:
                    raise ArchitecturePatchError(f"Unknown new_node_ref {p.get('new_node_ref')}")
                downstream = list(graph.nodes[target_id].next_node_ids)
                graph.replace_next(target_id, [new_id])
                if p.get("preserve_downstream", True):
                    graph.replace_next(new_id, [node_id for node_id in downstream if node_id != new_id])
            elif operation.op == "remove_node":
                graph.remove_node(int(p.get("node_id")))
            elif operation.op == "add_edge":
                graph.add_edge(int(p.get("from_node_id")), int(p.get("to_node_id")), label=p.get("label"), condition=p.get("condition"), priority=int(p.get("priority", 0) or 0))
            elif operation.op == "remove_edge":
                graph.remove_edge(int(p.get("from_node_id")), int(p.get("to_node_id")))
            elif operation.op in {"replace_next", "update_route"}:
                graph.replace_next(int(p.get("from_node_id") or p.get("node_id")), [int(item) for item in p.get("to_node_ids", []) or []])
            elif operation.op in {"update_node_metadata", "update_retry_policy"}:
                node = graph.nodes[int(p.get("node_id"))]
                node.metadata.update(dict(p.get("metadata", {}) or p.get("retry_policy", {}) or {}))
            elif operation.op == "update_output_mode":
                graph.nodes[int(p.get("node_id"))].metadata["output_mode"] = str(p.get("output_mode"))

    def _record(self, action: str, graph: Optional[ExecutionGraph], patch: ArchitecturePatch, detail: Dict[str, Any]) -> None:
        """Emit a runtime audit record via the core hook, if available."""
        record = getattr(self.core, "record_runtime_change", None)
        if callable(record):
            payload = {"patch_id": patch.patch_id, "reason": patch.reason, **detail}
            record(action=action, subject_kind="graph", subject_id=getattr(graph, "graph_name", None), detail=payload)

    def _create_patch_agent(self, payload: Dict[str, Any]) -> None:
        """Instantiate a minimal agent from an ``add_agent`` payload.

        Tries the core's ``create_agent`` hook first; falls back to direct
        insertion into ``core.agents`` and ``core.agent_blueprints``.
        """
        agent_id = str(payload.get("agent_id"))
        creator = getattr(self.core, "create_agent", None)
        if callable(creator):
            try:
                creator(
                    agent_id=agent_id,
                    name=str(payload.get("name") or agent_id),
                    character_prompt=str(payload.get("character_prompt") or ""),
                    tools=[],
                    tool_execution_mode=str(payload.get("tool_execution_mode") or "disabled"),
                )
                return
            except Exception:
                pass
        agent = _PatchAgent(
            agent_id=agent_id,
            name=str(payload.get("name") or agent_id),
            character_prompt=str(payload.get("character_prompt") or ""),
            tool_execution_mode=str(payload.get("tool_execution_mode") or "disabled"),
        )
        add_agent = getattr(self.core, "add_agent", None)
        register = getattr(self.core, "register_agent_blueprint", None)
        if callable(add_agent):
            add_agent(agent)
        else:
            self.core.agents[agent_id] = agent
        if callable(register):
            register(agent_id, agent)
        else:
            self.core.agent_blueprints[agent_id] = agent

    def _created_agents(self, patch: ArchitecturePatch) -> List[str]:
        """Return the list of agent_ids created by ``add_agent`` operations."""
        return [str(op.payload.get("agent_id")) for op in patch.operations if op.op == "add_agent"]

    def _agent_exists(self, agent_id: str) -> bool:
        """Check whether an agent blueprint is already known to the core."""
        has_agent = getattr(self.core, "has_agent_blueprint", None)
        return bool(has_agent(agent_id)) if callable(has_agent) else agent_id in getattr(self.core, "agents", {})

    def _node_ref_exists(self, graph: ExecutionGraph, ref: str) -> bool:
        """Check whether *ref* resolves to an existing node in *graph*."""
        return self._node_ref_id(graph, ref) is not None

    def _node_ref_id(self, graph: ExecutionGraph, ref: str) -> Optional[int]:
        """Resolve a node reference (numeric string or node_name) to an ID."""
        if ref.isdigit() and int(ref) in graph.nodes:
            return int(ref)
        for node in graph.nodes.values():
            if node.node_name == ref:
                return node.node_id
        return None

    def _payload_node_id(self, payload: Dict[str, Any]) -> Optional[int]:
        """Extract a node_id from a payload dict, tolerating missing values."""
        return self._int_or_none(payload.get("node_id") or payload.get("from_node_id"))

    def _int_or_none(self, raw: Any) -> Optional[int]:
        """Safe int coercion with None passthrough."""
        try:
            if raw is None:
                return None
            return int(raw)
        except Exception:
            return None

    def _resolve_new_node_id(self, graph: ExecutionGraph, raw: Any) -> int:
        """Allocate a fresh node ID, or parse an explicit one.

        Auto-allocation scans upward from max(existing IDs) + 1 to avoid
        collisions with deleted nodes.
        """
        if raw is None or str(raw).strip().lower() == "auto":
            candidate = max(graph.nodes.keys(), default=0) + 1
            while candidate in graph.nodes:
                candidate += 1
            return candidate
        return int(raw)

    def _node_lifecycle_metadata(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Derive standard lifecycle flags from payload keys like ``persistence``."""
        persistence = str(payload.get("persistence") or "transient").strip().lower()
        transient = persistence in {"transient", "temporary", "ephemeral"}
        lifetime = str(payload.get("lifetime_policy") or ("run" if transient else "manual")).strip().lower()
        return {
            "runtime_transient": transient,
            "persistence": "transient" if transient else "persistent",
            "lifetime_policy": lifetime,
            "node_lifecycle": {
                "runtime_transient": transient,
                "persistence": "transient" if transient else "persistent",
                "lifetime_policy": lifetime,
            },
        }

    def _entry_reaches_nodes(self, graph: ExecutionGraph) -> bool:
        """Return True if the entry node can reach at least one other node."""
        if graph.entry_node_id is None or graph.entry_node_id not in graph.nodes:
            return False
        seen: set[int] = set()
        stack = [graph.entry_node_id]
        while stack:
            node_id = stack.pop()
            if node_id in seen:
                continue
            seen.add(node_id)
            stack.extend([item for item in graph.nodes[node_id].next_node_ids if item not in seen])
        return bool(seen)

    def _max_depth(self, graph: ExecutionGraph) -> int:
        """Compute the longest path length from entry to any reachable node."""
        if graph.entry_node_id is None or graph.entry_node_id not in graph.nodes:
            return 0
        max_depth = 0
        stack: list[tuple[int, int, set[int]]] = [(graph.entry_node_id, 1, set())]
        seen_depth: Dict[int, int] = {}
        while stack:
            node_id, depth, path = stack.pop()
            if node_id in path:
                continue
            if depth <= seen_depth.get(node_id, 0):
                continue
            seen_depth[node_id] = depth
            max_depth = max(max_depth, depth)
            next_path = set(path)
            next_path.add(node_id)
            for next_id in graph.nodes[node_id].next_node_ids:
                if next_id in graph.nodes:
                    stack.append((next_id, depth + 1, next_path))
        return max_depth

    def _has_cycle(self, graph: ExecutionGraph) -> bool:
        """Detect cycles using a classic DFS three-colour algorithm."""
        visiting: set[int] = set()
        visited: set[int] = set()

        def visit(node_id: int) -> bool:
            if node_id in visiting:
                return True
            if node_id in visited:
                return False
            visiting.add(node_id)
            for next_id in graph.nodes[node_id].next_node_ids:
                if next_id in graph.nodes and visit(next_id):
                    return True
            visiting.remove(node_id)
            visited.add(node_id)
            return False

        return any(visit(node_id) for node_id in graph.nodes if node_id not in visited)


class _PatchAgent:
    """Minimal agent stub created when the core lacks a proper create_agent hook."""

    def __init__(self, *, agent_id: str, name: str, character_prompt: str, tool_execution_mode: str) -> None:
        self.agent_id = agent_id
        self.name = name
        self.character_prompt = character_prompt
        self.tool_execution_mode = tool_execution_mode
        self.tools: list[Any] = []

    async def round_call(self, *, rounds: int, user_message: str, additional_prompt: Optional[str] = None):
        from .results import AgentRoundResult

        return AgentRoundResult(
            rounds=rounds,
            user_message=user_message,
            assistant_message=user_message,
            additional_prompt=additional_prompt,
        )

    def reset_context(self) -> None:
        return None
