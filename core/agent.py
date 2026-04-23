from __future__ import annotations

import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from modules.llm_fetcher import LLMContext, LLMFetcher

from .cognitive import (
    CognitiveGraph,
    CognitiveNode,
    CognitiveEdge,
    CognitiveNodeType,
    CognitiveRelationType,
    extract_cognitive_graph_from_text,
    strip_cognitive_graph_tags,
)
from .results import AgentContextSnapshot, AgentRoundResult


@dataclass
class AgentContext:
    """Isolated per-agent context storage."""

    messages: List[Dict[str, str]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class Agent:
    """Runtime agent with isolated context and one LLM backend."""

    def __init__(
        self,
        agent_id: str,
        llm_handler: LLMFetcher,
        character_prompt: str,
        name: Optional[str] = None,
        tools: Optional[List[Any]] = None,
        core: Optional[Any] = None,
        max_tool_rounds: int = 5,
        cognitive_graph: Optional[CognitiveGraph] = None,
        workspace_mode: str = "workspace",
        workspace_root: Optional[Path] = None,
    ) -> None:
        self.agent_id = agent_id
        self.name = name or agent_id
        self.llm_handler = llm_handler
        self.character_prompt = character_prompt
        self._context = AgentContext()
        self.tools = tools or []
        self.core = core
        self.max_tool_rounds = max_tool_rounds
        self.cognitive_graph = cognitive_graph or CognitiveGraph(graph_id=f"agent_{agent_id}")
        self.workspace_mode = workspace_mode
        self.workspace_root = Path(workspace_root).resolve() if workspace_root is not None else None
        self.current_run_id: Optional[str] = None

    def append_context(self, role: str, content: str) -> None:
        """Append one message into the agent-local context."""
        self._context.messages.append({"role": role, "content": content})

    def get_context_snapshot(self) -> AgentContextSnapshot:
        """Return a safe snapshot of the agent context."""
        return AgentContextSnapshot(
            messages=[dict(item) for item in self._context.messages],
            metadata=dict(self._context.metadata),
        )

    def reset_context(self) -> None:
        """Clear the isolated agent context."""
        self._context.messages.clear()
        self._context.metadata.clear()

    def reset_runtime_state(self) -> None:
        """Clear per-run state so a fresh graph run starts without residue."""
        self.reset_context()
        self.cognitive_graph = CognitiveGraph(graph_id=f"agent_{self.agent_id}")
        self.current_run_id = None

    def set_run_id(self, run_id: Optional[str]) -> None:
        """Attach this agent to the current graph run."""
        self.current_run_id = str(run_id).strip() if run_id else None

    @property
    def private_workspace_dir(self) -> Path:
        """Directory for this agent's private, non-shared runtime artifacts."""
        root = self.workspace_root or Path.cwd()
        if self.current_run_id:
            return root / ".angelus_private" / "runs" / self.current_run_id / self.agent_id
        return root / ".angelus_private" / "manual" / self.agent_id

    def summarize_private_workspace(self, *, max_files: int = 8, max_chars: int = 1200) -> str:
        """Return a compact summary of private workspace artifacts for prompting."""
        workspace_dir = self.private_workspace_dir
        if not workspace_dir.exists():
            return "No private workspace artifacts recorded."

        files = sorted(
            [path for path in workspace_dir.rglob("*") if path.is_file()],
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )[:max_files]
        if not files:
            return "No private workspace artifacts recorded."

        lines = [f"Private workspace: {workspace_dir}"]
        remaining = max_chars
        for path in files:
            rel_path = path.relative_to(workspace_dir)
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                lines.append(f"- {rel_path}: unreadable")
                continue
            snippet = text.strip().replace("\n", " ")
            if len(snippet) > remaining:
                snippet = snippet[:remaining].rstrip() + "..."
            lines.append(f"- {rel_path}: {snippet or '[empty]'}")
            remaining -= len(snippet)
            if remaining <= 0:
                break
        return "\n".join(lines)

    def persist_private_thought_snapshot(self) -> None:
        """Persist private thought state inside the agent workspace."""
        workspace_dir = self.private_workspace_dir
        workspace_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = workspace_dir / "cognitive_graph_snapshot.json"
        snapshot_path.write_text(
            json.dumps(self.cognitive_graph.snapshot(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _build_system_prompt(self, additional_prompt: Optional[str] = None) -> str:
        prompts = [self.character_prompt.strip()]
        if additional_prompt:
            prompts.append(additional_prompt.strip())
        return "\n\n".join(prompt for prompt in prompts if prompt)

    def _extract_assistant_message(self, response: Any) -> Optional[str]:
        choices = getattr(response, "choices", None)
        if not choices:
            return None
        first_choice = choices[0]
        message = getattr(first_choice, "message", None)
        if message is None and isinstance(first_choice, dict):
            message = first_choice.get("message")
        if message is None:
            return None
        return getattr(message, "content", None) if not isinstance(message, dict) else message.get("content")

    def _extract_message_and_tool_calls(self, response: Any):
        """Extract content and tool_calls from an LLM response."""
        choices = getattr(response, "choices", None)
        if not choices:
            return None, None
        first_choice = choices[0]
        message = getattr(first_choice, "message", None)
        if message is None and isinstance(first_choice, dict):
            message = first_choice.get("message")
        if message is None:
            return None, None

        content = getattr(message, "content", None)
        if isinstance(message, dict):
            content = message.get("content")

        tool_calls = getattr(message, "tool_calls", None)
        if isinstance(message, dict):
            tool_calls = message.get("tool_calls")

        return content, tool_calls

    async def _execute_tool_call(self, tool_call: Any) -> str:
        """Execute a single tool call from the LLM response."""
        if self.core is None:
            return json.dumps({"error": "Agent has no core reference; cannot execute tools."})

        if hasattr(tool_call, "function"):
            tool_name = getattr(tool_call.function, "name", None)
            arguments_str = getattr(tool_call.function, "arguments", "{}")
        elif isinstance(tool_call, dict):
            tool_name = tool_call.get("function", {}).get("name")
            arguments_str = tool_call.get("function", {}).get("arguments", "{}")
        else:
            return json.dumps({"error": "Unrecognized tool_call format."})

        try:
            tool = self.core.get_tool(str(tool_name))
        except KeyError:
            return json.dumps({"error": f"Tool '{tool_name}' not found."})

        try:
            arguments = json.loads(arguments_str) if isinstance(arguments_str, str) else arguments_str
        except json.JSONDecodeError:
            return json.dumps({"error": f"Invalid JSON arguments for tool '{tool_name}': {arguments_str}"})

        from .toodefl import ToolContext

        get_capabilities = getattr(self.core, "get_tool_capabilities", None)
        capabilities = get_capabilities(str(tool_name)) if callable(get_capabilities) else set()
        context = ToolContext(
            agent_id=self.agent_id,
            node_id=None,
            rounds=0,
            workspace_mode=self.workspace_mode,
            workspace_root=self.workspace_root,
            metadata={},
            core=self.core,
            graph=None,
            capabilities=capabilities,
        )

        try:
            result = await tool.execute(arguments, context=context)
            if isinstance(result, dict):
                return json.dumps(result, ensure_ascii=False)
            return str(result)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    async def round_call(
        self,
        rounds: int,
        user_message: str,
        additional_prompt: Optional[str] = None,
    ) -> AgentRoundResult:
        """Execute one agent round with isolated context.

        If the agent has bound tools, this method enters a ReAct loop:
        LLM -> tool_calls -> execute tools -> results back to context -> LLM again.
        """
        self.append_context("user", user_message)
        system_prompt = self._build_system_prompt(additional_prompt)
        prev_messages = [LLMContext(role=item["role"], content=item["content"]) for item in self._context.messages[:-1]]

        # Prepare tool schemas if tools are bound
        tools_schemas = None
        if self.tools:
            schemas = [t.get_openai_schema() for t in self.tools if getattr(t, "get_openai_schema", None) and t.get_openai_schema()]
            if schemas:
                tools_schemas = schemas

        assistant_message = None
        raw_response = None

        for tool_round in range(self.max_tool_rounds):
            raw_response = await self.llm_handler.fetch(
                msg=user_message if tool_round == 0 else "",
                system_prompt=system_prompt or None,
                prev_messages=prev_messages or None,
                tools=tools_schemas,
            )

            content, tool_calls = self._extract_message_and_tool_calls(raw_response)

            if content:
                self.append_context("assistant", content)
            elif tool_calls:
                tool_names = []
                for tc in tool_calls:
                    if hasattr(tc, "function"):
                        tool_names.append(getattr(tc.function, "name", "?"))
                    elif isinstance(tc, dict):
                        tool_names.append(tc.get("function", {}).get("name", "?"))
                self.append_context("assistant", f"[Calling tools: {tool_names}]")

            if not tool_calls:
                assistant_message = content
                break

            # Execute tool calls and feed results back into context
            for tc in tool_calls:
                result = await self._execute_tool_call(tc)
                self.append_context("tool", result)
                self._record_tool_call_in_cognitive_graph(tc, result)

            # Refresh prev_messages for the next LLM call
            prev_messages = [LLMContext(role=item["role"], content=item["content"]) for item in self._context.messages]

        if assistant_message is None:
            assistant_message = content or "[Agent reached max tool rounds without final response]"

        self._context.metadata["last_round"] = rounds
        self._context.metadata["turns"] = len(self._context.messages)

        # Extract cognitive graph from the final assistant message
        cg = extract_cognitive_graph_from_text(assistant_message, source_agent_id=self.agent_id)
        if cg is not None:
            for node in cg.nodes.values():
                if not node.source:
                    node.source = self.agent_id
                self.cognitive_graph.add_node(node)
            for edge in cg.edges:
                self.cognitive_graph.add_edge(edge)
            assistant_message = strip_cognitive_graph_tags(assistant_message)
            self.persist_private_thought_snapshot()

        return AgentRoundResult(
            rounds=rounds,
            user_message=user_message,
            assistant_message=assistant_message,
            raw_response=raw_response,
            additional_prompt=additional_prompt,
            cognitive_graph_snapshot=self.cognitive_graph.snapshot(),
        )

    def _record_tool_call_in_cognitive_graph(self, tool_call: Any, result: str) -> None:
        """Auto-graphify a tool call and its result into the agent's cognitive graph."""
        # Extract tool name and arguments
        if hasattr(tool_call, "function"):
            tool_name = getattr(tool_call.function, "name", "unknown")
            arguments_str = getattr(tool_call.function, "arguments", "{}")
        elif isinstance(tool_call, dict):
            tool_name = tool_call.get("function", {}).get("name", "unknown")
            arguments_str = tool_call.get("function", {}).get("arguments", "{}")
        else:
            return

        try:
            arguments = json.loads(arguments_str) if isinstance(arguments_str, str) else arguments_str
        except Exception:
            arguments = {}

        query = arguments.get("query", "") or arguments.get("input", "") or str(arguments)[:120]

        # Create TOOL_RESULT node
        tool_node = CognitiveNode(
            node_type=CognitiveNodeType.TOOL_RESULT,
            content=f"Tool '{tool_name}' called with: {query}",
            source=self.agent_id,
            metadata={"tool_name": tool_name, "arguments": arguments},
        )
        self.cognitive_graph.add_node(tool_node)

        # Create EVIDENCE node from result (truncate for brevity)
        result_summary = result[:500] if len(result) > 500 else result
        evidence_node = CognitiveNode(
            node_type=CognitiveNodeType.EVIDENCE,
            content=f"Result from {tool_name}: {result_summary}",
            source=self.agent_id,
            metadata={"tool_name": tool_name, "result_truncated": len(result) > 500},
        )
        self.cognitive_graph.add_node(evidence_node)

        # Link: tool call leads_to evidence
        self.cognitive_graph.add_edge(
            CognitiveEdge(
                source_id=tool_node.node_id,
                target_id=evidence_node.node_id,
                relation=CognitiveRelationType.LEADS_TO,
                strength=1.0,
                description=f"Output of {tool_name}",
            )
        )
        # Link latest evidence to any existing REASONING node (heuristic: connect to most recent)
        recent_reasoning = [
            n for n in self.cognitive_graph.nodes.values()
            if n.node_type == CognitiveNodeType.REASONING
        ]
        if recent_reasoning:
            # Sort by created_at descending (newest first)
            recent_reasoning.sort(key=lambda n: n.created_at, reverse=True)
            self.cognitive_graph.add_edge(
                CognitiveEdge(
                    source_id=evidence_node.node_id,
                    target_id=recent_reasoning[0].node_id,
                    relation=CognitiveRelationType.EVIDENCE_FOR,
                    strength=0.9,
                    description="Supports recent reasoning",
                )
            )
        self.persist_private_thought_snapshot()
