from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Optional

from .errors import ToolContractError
from .policy import AgentNode, ExecutionGraph, ToolNode, _node_is_transient


DEFAULT_TOOL_ALIASES: Dict[str, str] = {
    "bash": "command_runner",
    "shell": "command_runner",
    "read_file": "file_reader",
    "grep": "search",
}


@dataclass
class ToolContractIssue:
    severity: Literal["error", "warning"]
    agent_id: Optional[str]
    node_id: Optional[int]
    tool_name: str
    issue_kind: str
    message: str
    suggested_fix: Optional[str] = None


@dataclass
class ToolContractReport:
    ok: bool
    errors: list[ToolContractIssue] = field(default_factory=list)
    warnings: list[ToolContractIssue] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": [issue.__dict__ for issue in self.errors],
            "warnings": [issue.__dict__ for issue in self.warnings],
        }

    def raise_if_failed(self) -> None:
        if not self.ok:
            raise ToolContractError(self, self.summary())

    def summary(self) -> str:
        if self.ok:
            return "tool contract validation passed"
        return "; ".join(issue.message for issue in self.errors) or "tool_contract_validation_failed"


class ToolContractValidator:
    """Validate graph node bindings and externally exposed agent tools."""

    def __init__(self, aliases: Optional[Dict[str, str]] = None) -> None:
        self.aliases = dict(DEFAULT_TOOL_ALIASES)
        if aliases:
            self.aliases.update(aliases)

    def validate(self, core: Any, graph: Optional[ExecutionGraph] = None) -> ToolContractReport:
        target_graph = graph or getattr(core, "get_execution_graph", lambda: None)()
        errors: list[ToolContractIssue] = []
        warnings: list[ToolContractIssue] = []

        if target_graph is not None:
            for node in target_graph.nodes.values():
                if isinstance(node, ToolNode):
                    self._validate_tool_node(core, node, errors, warnings)
                elif isinstance(node, AgentNode):
                    self._validate_agent_node(core, node, errors, warnings)

        agents = getattr(core, "agent_blueprints", {}) or {}
        all_agents = dict(getattr(core, "agents", {}) or {})
        all_agents.update(agents)
        for agent_id, agent in all_agents.items():
            self._validate_agent_tools(core, str(agent_id), agent, None, errors, warnings)

        return ToolContractReport(ok=not errors, errors=errors, warnings=warnings)

    def _validate_tool_node(
        self,
        core: Any,
        node: ToolNode,
        errors: list[ToolContractIssue],
        warnings: list[ToolContractIssue],
    ) -> None:
        tool_name = self.resolve_alias(node.tool_name)
        if not tool_name:
            errors.append(self._issue("error", None, node.node_id, node.tool_name, "missing_tool_name", "ToolNode has no tool_name."))
            return
        if tool_name not in getattr(core, "tools", {}):
            severity = "warning" if _node_is_transient(node.metadata) else "error"
            issue = self._issue(
                severity,
                None,
                node.node_id,
                node.tool_name,
                "unknown_tool",
                f"ToolNode {node.node_id} references unknown tool '{node.tool_name}'.",
                "Register the tool or update the graph node tool_name.",
            )
            (warnings if severity == "warning" else errors).append(issue)
        elif tool_name != node.tool_name:
            node.metadata.setdefault("tool_aliases", {})[node.tool_name] = tool_name

    def _validate_agent_node(
        self,
        core: Any,
        node: AgentNode,
        errors: list[ToolContractIssue],
        warnings: list[ToolContractIssue],
    ) -> None:
        blueprint_ref = str(node.blueprint_ref or "").strip()
        if not blueprint_ref:
            errors.append(self._issue("error", None, node.node_id, "", "missing_blueprint_ref", f"AgentNode {node.node_id} has no blueprint_ref."))
            return
        has_blueprint = getattr(core, "has_agent_blueprint", None)
        exists = bool(has_blueprint(blueprint_ref)) if callable(has_blueprint) else blueprint_ref in getattr(core, "agents", {})
        if not exists:
            severity = "warning" if _node_is_transient(node.metadata) else "error"
            issue = self._issue(
                severity,
                blueprint_ref,
                node.node_id,
                "",
                "unknown_agent_blueprint",
                f"AgentNode {node.node_id} references unknown agent blueprint '{blueprint_ref}'.",
                "Register the agent blueprint or update blueprint_ref.",
            )
            (warnings if severity == "warning" else errors).append(issue)
            return
        get_blueprint = getattr(core, "get_agent_blueprint", None)
        agent = get_blueprint(blueprint_ref) if callable(get_blueprint) else getattr(core, "agents", {}).get(blueprint_ref)
        if agent is not None:
            self._validate_agent_tools(core, blueprint_ref, agent, node.node_id, errors, warnings)

    def _validate_agent_tools(
        self,
        core: Any,
        agent_id: str,
        agent: Any,
        node_id: Optional[int],
        errors: list[ToolContractIssue],
        warnings: list[ToolContractIssue],
    ) -> None:
        mode = str(getattr(agent, "tool_execution_mode", "internal") or "internal").strip().lower()
        if mode != "external":
            return
        for tool in getattr(agent, "tools", []) or []:
            raw_name = getattr(tool, "tool_name", None) or str(tool or "")
            tool_name = self.resolve_alias(raw_name)
            if raw_name == "recall_context":
                warnings.append(self._issue(
                    "warning",
                    agent_id,
                    node_id,
                    raw_name,
                    "external_builtin_tool_scheduler_handled",
                    "External mode agent exposes built-in recall_context; ToolScheduler will handle it directly.",
                    None,
                ))
                continue
            if tool_name not in getattr(core, "tools", {}):
                errors.append(self._issue(
                    "error",
                    agent_id,
                    node_id,
                    raw_name,
                    "unknown_tool",
                    f"External mode agent '{agent_id}' exposes unknown tool '{raw_name}'.",
                    "Register the tool in core.tools or remove it from the agent.",
                ))

    def resolve_alias(self, tool_name: str) -> str:
        name = str(tool_name or "").strip()
        return self.aliases.get(name, name)

    def _issue(
        self,
        severity: Literal["error", "warning"],
        agent_id: Optional[str],
        node_id: Optional[int],
        tool_name: str,
        issue_kind: str,
        message: str,
        suggested_fix: Optional[str] = None,
    ) -> ToolContractIssue:
        return ToolContractIssue(
            severity=severity,
            agent_id=agent_id,
            node_id=node_id,
            tool_name=tool_name,
            issue_kind=issue_kind,
            message=message,
            suggested_fix=suggested_fix,
        )
