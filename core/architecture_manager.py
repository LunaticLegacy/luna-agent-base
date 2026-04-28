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
    ok: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    patch: Optional[ArchitecturePatch] = None


@dataclass
class PatchApplyResult:
    ok: bool
    patch_id: str
    graph: Optional[ExecutionGraph] = None
    errors: List[str] = field(default_factory=list)
    applied_operations: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class PatchRollbackResult:
    ok: bool
    patch_id: str
    errors: List[str] = field(default_factory=list)


class ArchitectureManager:
    """Validate and transactionally apply declarative architecture patches."""

    def __init__(self, core: Any) -> None:
        self.core = core
        self.rollback_records: Dict[str, Dict[str, Any]] = {}

    def policy(self) -> Dict[str, Any]:
        raw = getattr(self.core, "architecture_policy", None)
        result = dict(DEFAULT_ARCHITECTURE_POLICY)
        if isinstance(raw, dict):
            result.update(raw)
        return result

    def validate_patch(self, patch: Any, graph: Optional[ExecutionGraph] = None) -> PatchValidationResult:
        try:
            parsed = ArchitecturePatch.coerce(patch)
        except Exception as exc:
            return PatchValidationResult(ok=False, errors=[str(exc)])
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
            return PatchValidationResult(ok=False, errors=errors, warnings=warnings, patch=parsed)

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

        if len(getattr(self.core, "agents", {}) or {}) + len(created_agents) > int(policy.get("max_agents", 12)):
            errors.append("Patch would exceed max_agents policy.")
        if len(working.edges) > int(policy.get("max_edges", 32)):
            errors.append("Graph already exceeds max_edges policy.")

        if errors:
            return PatchValidationResult(ok=False, errors=errors, warnings=warnings, patch=parsed)

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
        return PatchValidationResult(ok=not errors, errors=errors, warnings=warnings, patch=parsed)

    async def apply_patch(self, patch: Any, graph: Optional[ExecutionGraph] = None, *, author: Optional[str] = None) -> PatchApplyResult:
        return await self._apply_patch(patch, graph=graph, author=author)

    def apply_patch_sync(self, patch: Any, graph: Optional[ExecutionGraph] = None, *, author: Optional[str] = None) -> PatchApplyResult:
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
        return self.rollback_patch_sync(patch_id, graph=graph)

    def rollback_patch_sync(self, patch_id: str, graph: Optional[ExecutionGraph] = None) -> PatchRollbackResult:
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
        record = getattr(self.core, "record_runtime_change", None)
        if callable(record):
            payload = {"patch_id": patch.patch_id, "reason": patch.reason, **detail}
            record(action=action, subject_kind="graph", subject_id=getattr(graph, "graph_name", None), detail=payload)

    def _create_patch_agent(self, payload: Dict[str, Any]) -> None:
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
        return [str(op.payload.get("agent_id")) for op in patch.operations if op.op == "add_agent"]

    def _agent_exists(self, agent_id: str) -> bool:
        has_agent = getattr(self.core, "has_agent_blueprint", None)
        return bool(has_agent(agent_id)) if callable(has_agent) else agent_id in getattr(self.core, "agents", {})

    def _node_ref_exists(self, graph: ExecutionGraph, ref: str) -> bool:
        return self._node_ref_id(graph, ref) is not None

    def _node_ref_id(self, graph: ExecutionGraph, ref: str) -> Optional[int]:
        if ref.isdigit() and int(ref) in graph.nodes:
            return int(ref)
        for node in graph.nodes.values():
            if node.node_name == ref:
                return node.node_id
        return None

    def _payload_node_id(self, payload: Dict[str, Any]) -> Optional[int]:
        return self._int_or_none(payload.get("node_id") or payload.get("from_node_id"))

    def _int_or_none(self, raw: Any) -> Optional[int]:
        try:
            if raw is None:
                return None
            return int(raw)
        except Exception:
            return None

    def _resolve_new_node_id(self, graph: ExecutionGraph, raw: Any) -> int:
        if raw is None or str(raw).strip().lower() == "auto":
            candidate = max(graph.nodes.keys(), default=0) + 1
            while candidate in graph.nodes:
                candidate += 1
            return candidate
        return int(raw)

    def _node_lifecycle_metadata(self, payload: Dict[str, Any]) -> Dict[str, Any]:
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
