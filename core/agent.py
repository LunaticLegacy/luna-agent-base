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


@dataclass
class ContextBlock:
    """One compressed block of archived conversation history."""

    block_id: str
    summary: str
    keywords: List[str]
    archived_messages: List[Dict[str, str]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "block_id": self.block_id,
            "summary": self.summary,
            "keywords": list(self.keywords),
            "archived_messages": [dict(m) for m in self.archived_messages],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContextBlock":
        return cls(
            block_id=str(data.get("block_id", "")),
            summary=str(data.get("summary", "")),
            keywords=list(data.get("keywords", []) or []),
            archived_messages=[dict(m) for m in data.get("archived_messages", []) or []],
        )


class ManagedAgentContext:
    """Tiered agent context: active window + compressed blocks + archive."""

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
        return {
            "type": "function",
            "function": {
                "name": self.tool_name,
                "description": self.description,
                "parameters": self.schema,
            },
        }


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
        cognitive_graph: Optional[CognitiveGraph] = None,
        workspace_mode: str = "workspace",
        workspace_root: Optional[Path] = None,
        swarm_name: Optional[str] = None,
        tool_execution_mode: str = "internal",
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

    def reset_runtime_state(self) -> None:
        """Clear per-run state so a fresh graph run starts without residue."""
        self.reset_context()
        self.cognitive_graph = CognitiveGraph(graph_id=f"agent_{self.agent_id}")
        self.current_run_id = None

    def set_run_id(self, run_id: Optional[str]) -> None:
        """Attach this agent to the current graph run."""
        self.current_run_id = str(run_id).strip() if run_id else None

    def clone_for_runtime(self) -> "Agent":
        """Create a fresh runtime instance from the same agent blueprint."""
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
        for node in source.nodes.values():
            target.add_node(node)
        for edge in source.edges:
            target.add_edge(edge)

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
        """
        self.append_context("user", user_message)
        system_prompt = self._build_system_prompt(additional_prompt)
        context_messages = self._context.build_messages()
        prev_messages = [LLMContext(role=msg["role"], content=msg["content"]) for msg in context_messages[:-1]]

        # Prepare tool schemas if tools are bound
        tools_schemas = None
        if self.tool_execution_mode != "disabled" and self.tools:
            schemas = [t.get_openai_schema() for t in self.tools if getattr(t, "get_openai_schema", None) and t.get_openai_schema()]
            if schemas:
                tools_schemas = schemas

        assistant_message = None
        raw_response = None
        tool_requests: Optional[List[ToolRequest]] = None
        round_cognitive_graph = CognitiveGraph(graph_id=f"agent_{self.agent_id}_round_{rounds}")

        # Capture the LLM input for this round (initial call, before tool loop mutations).
        llm_input: Dict[str, Any] = {
            "system": system_prompt,
            "user": user_message,
            "prev_messages": [
                {"role": m.role, "content": m.content}
                for m in (prev_messages or [])
            ],
            "tools": tools_schemas,
        }

        tool_round = 0
        while True:
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

            if self.tool_execution_mode == "external":
                tool_requests = []
                for tc in tool_calls:
                    tool_name = getattr(tc.function, "name", None) if hasattr(tc, "function") else tc.get("function", {}).get("name")
                    arguments_str = getattr(tc.function, "arguments", "{}") if hasattr(tc, "function") else tc.get("function", {}).get("arguments", "{}")
                    args = json.loads(arguments_str) if isinstance(arguments_str, str) else arguments_str
                    tool_requests.append(ToolRequest(
                        id=getattr(tc, "id", f"tc-{len(tool_requests)}"),
                        tool=tool_name,
                        args=args,
                        on_success="continue",
                        on_failure="return_to_agent",
                    ))
                assistant_message = content or f"[External tool requests: {len(tool_requests)}]"
                break

            # Execute tool calls and feed results back into context
            for tc in tool_calls:
                result = await self._execute_tool_call(tc)
                self.append_context("tool", result)
                self._record_tool_call_in_cognitive_graph(tc, result, round_cognitive_graph)

            # Refresh prev_messages for the next LLM call
            context_messages = self._context.build_messages()
            prev_messages = [LLMContext(role=msg["role"], content=msg["content"]) for msg in context_messages]
            tool_round += 1

        if assistant_message is None:
            assistant_message = content or "[Agent did not produce a final response]"

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
