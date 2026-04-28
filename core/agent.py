"""Agent runtime implementation.

Provides ``Agent``, the primary per-agent runtime object, together with
``ManagedAgentContext`` (tiered memory: active window + compressed blocks)
and ``RecallContextTool`` (built-in archive search).

An agent owns:
    * One LLM backend (via LLMFetcher).
    * A private cognitive graph (thought state).
    * An isolated workspace directory.
    * Optional tool bindings and memory runtime hooks.

The ``round_call`` method implements the ReAct loop: LLM → tool_calls →
tool execution → results back to context → LLM again, until the assistant
produces a final message or an external tool request is emitted.
"""

from __future__ import annotations

import json
import re
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
from .results import AgentContextSnapshot, AgentRoundResult, ToolRequest
from .memory.runtime import AgentMemoryRuntime
from .tool_prompt_serializer import serialize_tool_contracts


@dataclass
class ContextBlock:
    """One compressed block of archived conversation history.

    Attributes:
        block_id: Unique identifier for this block.
        summary: Condensed text of the archived messages.
        keywords: Indexed tokens for fast retrieval.
        archived_messages: Original message dicts (preserved for full recall).
    """

    block_id: str
    summary: str
    keywords: List[str]
    archived_messages: List[Dict[str, str]]

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict."""
        return {
            "block_id": self.block_id,
            "summary": self.summary,
            "keywords": list(self.keywords),
            "archived_messages": [dict(m) for m in self.archived_messages],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContextBlock":
        """Deserialise from a plain dict."""
        return cls(
            block_id=str(data.get("block_id", "")),
            summary=str(data.get("summary", "")),
            keywords=list(data.get("keywords", []) or []),
            archived_messages=[dict(m) for m in data.get("archived_messages", []) or []],
        )


class ManagedAgentContext:
    """Tiered agent context: active window + compressed blocks + archive.

    Active messages are kept verbatim.  When the total message count
    exceeds ``COMPRESSION_THRESHOLD`` and the active window is larger
    than ``ACTIVE_WINDOW_SIZE``, older messages are compressed into a
    ``ContextBlock``.
    """

    ACTIVE_WINDOW_SIZE = 6
    COMPRESSION_THRESHOLD = 10

    def __init__(self) -> None:
        self.active_messages: List[Dict[str, str]] = []
        self.compressed_blocks: List[ContextBlock] = []
        self.metadata: Dict[str, Any] = {}

    def append(self, role: str, content: str) -> None:
        """Append one message and trigger compression if needed."""
        self.active_messages.append({"role": role, "content": content})
        self._maybe_compress()

    def _maybe_compress(self) -> None:
        total = len(self.active_messages) + sum(
            len(b.archived_messages) for b in self.compressed_blocks
        )
        if total > self.COMPRESSION_THRESHOLD and len(self.active_messages) > self.ACTIVE_WINDOW_SIZE:
            to_compress = self.active_messages[:-self.ACTIVE_WINDOW_SIZE]
            self.active_messages = self.active_messages[-self.ACTIVE_WINDOW_SIZE:]
            block = self._compress(to_compress)
            self.compressed_blocks.append(block)

    def _compress(self, messages: List[Dict[str, str]]) -> ContextBlock:
        summary_lines: List[str] = []
        for msg in messages:
            prefix = msg["role"].upper()
            text = msg["content"]
            if len(text) > 300:
                text = text[:300] + "..."
            summary_lines.append(f"[{prefix}] {text}")
        summary = "\n".join(summary_lines)

        keywords = self._extract_keywords(
            "\n".join(m["content"] for m in messages)
        )

        return ContextBlock(
            block_id=f"ctx_{len(self.compressed_blocks)}",
            summary=summary,
            keywords=keywords,
            archived_messages=[dict(m) for m in messages],
        )

    @staticmethod
    def _extract_keywords(text: str) -> List[str]:
        """Extract alphanumeric/CJK tokens, deduplicated, capped at 12."""
        tokens = re.findall(r"[a-zA-Z]{3,}|[\u4e00-\u9fff]{2,}", text.lower())
        seen: set[str] = set()
        result: List[str] = []
        for t in tokens:
            if t not in seen:
                seen.add(t)
                result.append(t)
        return result[:12]

    def retrieve(self, query: str) -> List[Dict[str, str]]:
        """Search archived messages by query match against summary/keywords/content."""
        query_lower = query.lower()
        results: List[Dict[str, str]] = []
        for block in self.compressed_blocks:
            if query_lower in block.summary.lower():
                results.extend(block.archived_messages)
                continue
            if any(query_lower in kw.lower() for kw in block.keywords):
                results.extend(block.archived_messages)
                continue
            for msg in block.archived_messages:
                if query_lower in msg["content"].lower():
                    results.append(dict(msg))
        return results

    def build_messages(self) -> List[Dict[str, str]]:
        """Build the full message list for LLM submission.

        Compressed blocks are injected as lightweight system hints;
        active messages follow in full.
        """
        messages: List[Dict[str, str]] = []
        for block in self.compressed_blocks:
            header = (
                f"[ARCHIVED CONTEXT {block.block_id}] "
                f"Keywords: {', '.join(block.keywords[:8])}"
            )
            summary = block.summary[:400]
            messages.append({
                "role": "system",
                "content": f"{header}\n{summary}",
            })
        messages.extend(self.active_messages)
        return messages

    def clear(self) -> None:
        """Reset all context tiers."""
        self.active_messages.clear()
        self.compressed_blocks.clear()
        self.metadata.clear()


class RecallContextTool:
    """Built-in tool allowing an agent to retrieve archived context on demand."""

    tool_name = "recall_context"
    description = (
        "Search archived conversation history by query. "
        "Use this when you need details not present in the active window or compressed summaries."
    )
    schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Keywords or phrase to search for in archived context",
            },
        },
        "required": ["query"],
    }

    def get_openai_schema(self) -> Optional[Dict[str, Any]]:
        """Return the OpenAI function-calling schema for this tool."""
        return {
            "type": "function",
            "function": {
                "name": self.tool_name,
                "description": self.description,
                "parameters": self.schema,
            },
        }


class Agent:
    """Runtime agent with isolated context and one LLM backend.

    Attributes:
        agent_id: Canonical identifier.
        name: Display name (falls back to agent_id).
        llm_handler: Backend fetcher for LLM calls.
        character_prompt: Base system prompt.
        tools: Bound tool instances (RecallContextTool auto-injected).
        core: Optional back-reference to the runtime Core.
        cognitive_graph: Private thought graph for this agent.
        workspace_mode: Workspace isolation level.
        workspace_root: Filesystem root for workspace artifacts.
        swarm_name: Swarm affiliation.
        current_run_id: Run the agent is currently attached to.
        tool_execution_mode: ``"internal"``, ``"external"``, or ``"disabled"``.
        tool_contract_prompt_mode: How tool schemas are injected into prompts.
        memory_runtime: Optional memory subsystem hook.
    """

    def __init__(
        self,
        agent_id: str,
        llm_handler: LLMFetcher,
        character_prompt: str,
        name: Optional[str] = None,
        tools: Optional[List[Any]] = None,
        core: Optional[Any] = None,
        cognitive_graph: Optional[CognitiveGraph] = None,
        workspace_mode: str = "workspace",
        workspace_root: Optional[Path] = None,
        swarm_name: Optional[str] = None,
        tool_execution_mode: str = "internal",
        memory_runtime: Optional[AgentMemoryRuntime] = None,
        tool_contract_prompt_mode: str = "auto",
    ) -> None:
        self.agent_id = agent_id
        self.name = name or agent_id
        self.llm_handler = llm_handler
        self.character_prompt = character_prompt
        self._context = ManagedAgentContext()
        self.tools = list(tools or [])
        # Auto-inject recall_context tool for on-demand archive retrieval
        if not any(getattr(t, "tool_name", None) == "recall_context" for t in self.tools):
            self.tools.append(RecallContextTool())
        self.core = core
        self.cognitive_graph = cognitive_graph or CognitiveGraph(graph_id=f"agent_{agent_id}")
        self.workspace_mode = workspace_mode
        self.workspace_root = Path(workspace_root).resolve() if workspace_root is not None else None
        self.swarm_name = swarm_name
        self.current_run_id: Optional[str] = None
        self.tool_execution_mode = tool_execution_mode
        self.tool_contract_prompt_mode = tool_contract_prompt_mode
        self.memory_runtime = memory_runtime

    def append_context(self, role: str, content: str) -> None:
        """Append one message into the agent-local context."""
        self._context.append(role, content)

    def get_context_snapshot(self) -> AgentContextSnapshot:
        """Return a safe snapshot of the agent context."""
        return AgentContextSnapshot(
            messages=[dict(item) for item in self._context.active_messages],
            compressed_blocks=[b.to_dict() for b in self._context.compressed_blocks],
            metadata=dict(self._context.metadata),
        )

    def reset_context(self) -> None:
        """Clear the isolated agent context."""
        self._context.clear()

    def recall_context(self, query: str) -> List[Dict[str, str]]:
        """Return archived context matches for built-in recall_context calls."""
        return self._context.retrieve(query)

    def reset_runtime_state(self) -> None:
        """Clear per-run state so a fresh graph run starts without residue."""
        self.reset_context()
        self.cognitive_graph = CognitiveGraph(graph_id=f"agent_{self.agent_id}")
        self.current_run_id = None

    def set_run_id(self, run_id: Optional[str]) -> None:
        """Attach this agent to the current graph run."""
        self.current_run_id = str(run_id).strip() if run_id else None

    def clone_for_runtime(self) -> "Agent":
        """Create a fresh runtime instance from the same agent blueprint.

        The cloned agent shares the same backend and tools but starts with
        a blank cognitive graph and no run binding.
        """
        cloned = Agent(
            agent_id=self.agent_id,
            llm_handler=self.llm_handler,
            character_prompt=self.character_prompt,
            name=self.name,
            tools=list(self.tools),
            core=self.core,
            cognitive_graph=CognitiveGraph(graph_id=f"agent_{self.agent_id}"),
            workspace_mode=self.workspace_mode,
            workspace_root=self.workspace_root,
            swarm_name=self.swarm_name,
            tool_execution_mode=self.tool_execution_mode,
            memory_runtime=self.memory_runtime,
            tool_contract_prompt_mode=self.tool_contract_prompt_mode,
        )
        cloned.set_run_id(self.current_run_id)
        return cloned

    @property
    def private_workspace_dir(self) -> Path:
        """Directory for this agent's private, non-shared runtime artifacts.

        Organised by swarm so that state from different swarms never collides.
        """
        root = self.workspace_root or Path.cwd()
        swarm_segment = self.swarm_name or "unknown"
        if self.current_run_id:
            return root / ".angelus_private" / "swarms" / swarm_segment / "runs" / self.current_run_id / self.agent_id
        return root / ".angelus_private" / "swarms" / swarm_segment / "manual" / self.agent_id

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

    @staticmethod
    def _merge_cognitive_graphs(target: CognitiveGraph, source: CognitiveGraph) -> None:
        """Deep-copy all nodes and edges from *source* into *target*."""
        for node in source.nodes.values():
            target.add_node(node)
        for edge in source.edges:
            target.add_edge(edge)

    def _build_system_prompt(self, additional_prompt: Optional[str] = None) -> str:
        """Compose the system prompt from character, extras, and tool contracts."""
        prompts = [self.character_prompt.strip()]
        if additional_prompt:
            prompts.append(additional_prompt.strip())
        if self.tool_execution_mode != "disabled":
            tool_contract_prompt = serialize_tool_contracts(
                self.tools,
                mode=self.tool_contract_prompt_mode,
            )
            if tool_contract_prompt:
                prompts.append(tool_contract_prompt)
        return "\n\n".join(prompt for prompt in prompts if prompt)

    def _extract_assistant_message(self, response: Any) -> Optional[str]:
        """Safely extract the assistant text from an LLM response object."""
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
        """Execute a single tool call from the LLM response.

        Handles the built-in ``recall_context`` locally; all other tools
        are dispatched through the core tool registry.
        """
        if hasattr(tool_call, "function"):
            tool_name = getattr(tool_call.function, "name", None)
            arguments_str = getattr(tool_call.function, "arguments", "{}")
        elif isinstance(tool_call, dict):
            tool_name = tool_call.get("function", {}).get("name")
            arguments_str = tool_call.get("function", {}).get("arguments", "{}")
        else:
            return json.dumps({"error": "Unrecognized tool_call format."})

        try:
            arguments = json.loads(arguments_str) if isinstance(arguments_str, str) else arguments_str
        except json.JSONDecodeError:
            return json.dumps({"error": f"Invalid JSON arguments for tool '{tool_name}': {arguments_str}"})

        # Built-in recall_context does not need the core tool registry
        if str(tool_name) == "recall_context":
            query = arguments.get("query", "")
            messages = self._context.retrieve(query)
            return json.dumps(
                {"found": len(messages), "messages": messages},
                ensure_ascii=False,
            )

        if self.core is None:
            return json.dumps({"error": "Agent has no core reference; cannot execute tools."})

        try:
            tool = self.core.get_tool(str(tool_name))
        except KeyError:
            return json.dumps({"error": f"Tool '{tool_name}' not found."})

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

        Args:
            rounds: Round counter (for bookkeeping).
            user_message: The user's input text.
            additional_prompt: Extra system prompt appended for this round only.

        Returns:
            An AgentRoundResult containing the final assistant message,
            cognitive graph deltas, tool requests, and LLM input snapshot.
        """
        self.append_context("user", user_message)
        system_prompt = self._build_system_prompt(additional_prompt)

        # 1. Prepare inputs --------------------------------------------------
        memory_plan, prev_messages, tools_schemas, llm_input, runtime_prev_messages = await self._prepare_round_inputs(
            rounds, user_message, system_prompt
        )

        # 2. ReAct loop ------------------------------------------------------
        assistant_message, raw_response, tool_requests, round_cognitive_graph, last_content = await self._run_react_loop(
            user_message, system_prompt, prev_messages, tools_schemas, runtime_prev_messages
        )

        # 3. Finalize and return ---------------------------------------------
        return await self._finalize_round(
            rounds=rounds,
            user_message=user_message,
            additional_prompt=additional_prompt,
            assistant_message=assistant_message,
            raw_response=raw_response,
            tool_requests=tool_requests,
            memory_plan=memory_plan,
            llm_input=llm_input,
            round_cognitive_graph=round_cognitive_graph,
            last_content=last_content,
        )

    async def _prepare_round_inputs(
        self,
        rounds: int,
        user_message: str,
        system_prompt: str,
    ) -> tuple:
        """Prepare all inputs needed for the ReAct loop.

        Handles the memory-runtime ``before_round`` hook, builds message
        history, serialises tool schemas, and captures the LLM input snapshot.

        Args:
            rounds: Round counter.
            user_message: Raw user input text.
            system_prompt: Composed system prompt for this round.

        Returns:
            A tuple of *(memory_plan, prev_messages, tools_schemas, llm_input, runtime_prev_messages)*.
        """
        memory_plan = None
        runtime_prev_messages: Optional[List[LLMContext]] = None
        if self.memory_runtime is not None and self.memory_runtime.config.enabled:
            memory_plan = await self.memory_runtime.before_round(
                agent_id=self.agent_id,
                swarm_name=self.swarm_name or "",
                run_id=self.current_run_id,
                user_message=user_message,
            )
            runtime_prev_messages = [
                LLMContext(role=m["role"], content=m["content"])
                for m in memory_plan.prompt_messages
            ]

        if runtime_prev_messages is not None:
            prev_messages = runtime_prev_messages
        else:
            context_messages = self._context.build_messages()
            prev_messages = [
                LLMContext(role=msg["role"], content=msg["content"])
                for msg in context_messages[:-1]
            ]

        tools_schemas = None
        if self.tool_execution_mode != "disabled" and self.tools:
            schemas = [
                t.get_openai_schema()
                for t in self.tools
                if getattr(t, "get_openai_schema", None) and t.get_openai_schema()
            ]
            if schemas:
                tools_schemas = schemas

        llm_input: Dict[str, Any] = {
            "system": system_prompt,
            "user": user_message,
            "prev_messages": [
                {"role": m.role, "content": m.content}
                for m in (prev_messages or [])
            ],
            "tools": tools_schemas,
        }
        if memory_plan is not None:
            llm_input["memory_context_plan"] = memory_plan.to_dict()

        return memory_plan, prev_messages, tools_schemas, llm_input, runtime_prev_messages

    async def _run_react_loop(
        self,
        user_message: str,
        system_prompt: str,
        prev_messages: List[LLMContext],
        tools_schemas: Optional[List[Dict[str, Any]]],
        runtime_prev_messages: Optional[List[LLMContext]],
    ) -> tuple:
        """Run the ReAct loop: LLM -> tools -> LLM until no more tool calls.

        Supports both ``internal`` and ``external`` tool execution modes.

        Args:
            user_message: The original user message (needed for runtime history).
            system_prompt: System prompt for LLM calls.
            prev_messages: Initial message history for the first LLM call.
            tools_schemas: OpenAI-style tool schemas (None if disabled).
            runtime_prev_messages: Optional memory-managed message list.

        Returns:
            A tuple of *(assistant_message, raw_response, tool_requests,
            round_cognitive_graph, last_content)*.
        """
        assistant_message = None
        raw_response = None
        tool_requests = None
        round_cognitive_graph = CognitiveGraph(graph_id=f"agent_{self.agent_id}_round_{0}")
        tool_round = 0
        last_content = None

        while True:
            raw_response = await self.llm_handler.fetch(
                msg=user_message if tool_round == 0 else "",
                system_prompt=system_prompt or None,
                prev_messages=prev_messages or None,
                tools=tools_schemas,
            )

            content, tool_calls = self._extract_message_and_tool_calls(raw_response)
            last_content = content

            self._update_context_from_response(
                content=content,
                tool_calls=tool_calls,
                tool_round=tool_round,
                runtime_prev_messages=runtime_prev_messages,
                user_message=user_message,
            )

            if not tool_calls:
                assistant_message = content
                break

            if self.tool_execution_mode == "external":
                tool_requests = self._build_external_tool_requests(tool_calls)
                assistant_message = content or f"[External tool requests: {len(tool_requests)}]"
                break

            await self._execute_internal_tool_round(
                tool_calls=tool_calls,
                runtime_prev_messages=runtime_prev_messages,
                round_cognitive_graph=round_cognitive_graph,
            )

            # Refresh prev_messages for the next LLM call
            if runtime_prev_messages is not None:
                prev_messages = runtime_prev_messages
            else:
                context_messages = self._context.build_messages()
                prev_messages = [
                    LLMContext(role=msg["role"], content=msg["content"])
                    for msg in context_messages
                ]
            tool_round += 1

        return assistant_message, raw_response, tool_requests, round_cognitive_graph, last_content

    def _update_context_from_response(
        self,
        content: Optional[str],
        tool_calls: Optional[List[Any]],
        tool_round: int,
        runtime_prev_messages: Optional[List[LLMContext]],
        user_message: str,
    ) -> None:
        """Append the LLM response (content or tool-calls placeholder) to context.

        Also synchronises the runtime-managed message list if one exists.
        """
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

        # Ensure the user message is included in runtime history for subsequent fetches
        if tool_round == 0 and runtime_prev_messages is not None:
            runtime_prev_messages.append(LLMContext(role="user", content=user_message))

        if runtime_prev_messages is not None:
            if content:
                runtime_prev_messages.append(LLMContext(role="assistant", content=content))
            elif tool_calls:
                runtime_prev_messages.append(
                    LLMContext(role="assistant", content=f"[Calling tools: {tool_names}]")
                )

    def _build_external_tool_requests(
        self,
        tool_calls: List[Any],
    ) -> List[ToolRequest]:
        """Build :class:`ToolRequest` objects from raw LLM tool_calls for external mode.

        Args:
            tool_calls: Raw tool_call objects from the LLM response.

        Returns:
            List of ToolRequest records.
        """
        tool_requests: List[ToolRequest] = []
        for tc in tool_calls:
            tool_name = (
                getattr(tc.function, "name", None)
                if hasattr(tc, "function")
                else tc.get("function", {}).get("name")
            )
            arguments_str = (
                getattr(tc.function, "arguments", "{}")
                if hasattr(tc, "function")
                else tc.get("function", {}).get("arguments", "{}")
            )
            try:
                args = json.loads(arguments_str) if isinstance(arguments_str, str) else arguments_str
            except json.JSONDecodeError:
                args = {"error": f"Invalid JSON arguments for tool '{tool_name}': {arguments_str}"}
            tool_requests.append(
                ToolRequest(
                    id=getattr(tc, "id", f"tc-{len(tool_requests)}"),
                    tool=tool_name,
                    args=args,
                    on_success="continue",
                    on_failure="return_to_agent",
                )
            )
        return tool_requests

    async def _execute_internal_tool_round(
        self,
        tool_calls: List[Any],
        runtime_prev_messages: Optional[List[LLMContext]],
        round_cognitive_graph: CognitiveGraph,
    ) -> None:
        """Execute all tool calls in ``internal`` mode and update context + cognitive graph.

        Args:
            tool_calls: Raw tool_call objects from the LLM response.
            runtime_prev_messages: Optional memory-managed message list.
            round_cognitive_graph: Cognitive graph for this round (accumulates tool nodes).
        """
        for tc in tool_calls:
            result = await self._execute_tool_call(tc)
            self.append_context("tool", result)
            if runtime_prev_messages is not None:
                runtime_prev_messages.append(LLMContext(role="tool", content=result))
            self._record_tool_call_in_cognitive_graph(tc, result, round_cognitive_graph)

    async def _finalize_round(
        self,
        *,
        rounds: int,
        user_message: str,
        additional_prompt: Optional[str],
        assistant_message: Optional[str],
        raw_response: Any,
        tool_requests: Optional[List[ToolRequest]],
        memory_plan: Any,
        llm_input: Dict[str, Any],
        round_cognitive_graph: CognitiveGraph,
        last_content: Optional[str],
    ) -> AgentRoundResult:
        """Finalize a completed round: extract cognitive graph, merge state, run after_round hook.

        Args:
            rounds: Round counter.
            user_message: Original user message.
            additional_prompt: Extra system prompt used this round.
            assistant_message: Final assistant text (may be None if loop exited abnormally).
            raw_response: Last raw LLM response object.
            tool_requests: External tool requests (None in internal mode).
            memory_plan: Memory context plan from before_round (None if disabled).
            llm_input: Snapshot of the LLM input for this round.
            round_cognitive_graph: Cognitive graph accumulated during the round.
            last_content: The content field from the last LLM response.

        Returns:
            Populated :class:`AgentRoundResult`.
        """
        if assistant_message is None:
            assistant_message = last_content or "[Agent did not produce a final response]"

        self._context.metadata["last_round"] = rounds
        self._context.metadata["turns"] = len(self._context.active_messages) + sum(
            len(b.archived_messages) for b in self._context.compressed_blocks
        )

        # Extract cognitive graph from the final assistant message
        cg = extract_cognitive_graph_from_text(assistant_message, source_agent_id=self.agent_id)
        if cg is not None:
            for node in cg.nodes.values():
                if not node.source:
                    node.source = self.agent_id
                round_cognitive_graph.add_node(node)
            for edge in cg.edges:
                round_cognitive_graph.add_edge(edge)
            assistant_message = strip_cognitive_graph_tags(assistant_message)

        self._merge_cognitive_graphs(self.cognitive_graph, round_cognitive_graph)
        if round_cognitive_graph.nodes or round_cognitive_graph.edges:
            self.persist_private_thought_snapshot()

        # Memory runtime hook: finalize after the round
        if memory_plan is not None and self.memory_runtime is not None:
            await self.memory_runtime.after_round(
                agent_id=self.agent_id,
                swarm_name=self.swarm_name or "",
                run_id=self.current_run_id,
                user_message=user_message,
                assistant_message=assistant_message or "",
                context_plan=memory_plan,
            )

        return AgentRoundResult(
            rounds=rounds,
            user_message=user_message,
            assistant_message=assistant_message,
            raw_response=raw_response,
            additional_prompt=additional_prompt,
            cognitive_graph_snapshot=self.cognitive_graph.snapshot(),
            cognitive_graph_delta=round_cognitive_graph.snapshot(),
            tool_requests=tool_requests if self.tool_execution_mode == "external" else None,
            llm_input=llm_input,
        )


    def _record_tool_call_in_cognitive_graph(
        self,
        tool_call: Any,
        result: str,
        target_graph: CognitiveGraph,
    ) -> None:
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
        target_graph.add_node(tool_node)

        # Create EVIDENCE node from result (truncate for brevity)
        result_summary = result[:500] if len(result) > 500 else result
        evidence_node = CognitiveNode(
            node_type=CognitiveNodeType.EVIDENCE,
            content=f"Result from {tool_name}: {result_summary}",
            source=self.agent_id,
            metadata={"tool_name": tool_name, "result_truncated": len(result) > 500},
        )
        target_graph.add_node(evidence_node)

        # Link: tool call leads_to evidence
        target_graph.add_edge(
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
            n for n in target_graph.nodes.values()
            if n.node_type == CognitiveNodeType.REASONING
        ]
        if recent_reasoning:
            # Sort by created_at descending (newest first)
            recent_reasoning.sort(key=lambda n: n.created_at, reverse=True)
            target_graph.add_edge(
                CognitiveEdge(
                    source_id=evidence_node.node_id,
                    target_id=recent_reasoning[0].node_id,
                    relation=CognitiveRelationType.EVIDENCE_FOR,
                    strength=0.9,
                    description="Supports recent reasoning",
                )
            )
