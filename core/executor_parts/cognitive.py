from __future__ import annotations

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core import Core
    from ..policy import AgentNode


class CognitiveContextMixin:
    """Inject shared cognitive context into agent prompts."""

    def _inject_cognitive_context(self, core: "Core", node: "AgentNode") -> Optional[str]:
        try:
            build_context = getattr(core, "build_thought_context_export", None)
            if callable(build_context):
                cg_export = build_context(
                    agent_id=node.agent_id,
                    query=f"{node.node_name} {node.additional_prompt or ''}",
                    purpose=f"Support execution node {node.node_name}",
                    max_nodes=12,
                )
            else:
                cg_export = core.get_cognitive_graph_export(max_nodes=12)
        except Exception:
            return None
        if not cg_export or cg_export.endswith("nodes=0, edges=0):"):
            return None
        return cg_export

