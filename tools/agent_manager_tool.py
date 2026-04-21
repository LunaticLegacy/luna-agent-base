from __future__ import annotations

import json
from typing import Any, Dict, Optional

from core.toodefl import ToolContext, ToolDefinition


class AgentManagerTool(ToolDefinition):
    """Create or destroy runtime agents during execution."""

    def __init__(self) -> None:
        super().__init__(
            tool_name="agent_manager",
            description="Create or destroy runtime agents.",
        )

    async def execute(
        self,
        arguments: Dict[str, Any],
        *,
        context: Optional[ToolContext] = None,
    ) -> Any:
        if context is None or context.core is None:
            raise ValueError("agent_manager requires a runtime core context.")

        normalized = self._normalize_arguments(arguments)
        runtime_metadata = dict((context.metadata or {}))
        action = str(
            normalized.get("action")
            or normalized.get("operation")
            or normalized.get("mode")
            or self._derive_action_from_payload(normalized, runtime_metadata)
            or ""
        ).strip().lower()
        if not action:
            raise ValueError("agent_manager requires an action.")

        content_passthrough = self._extract_content_passthrough(normalized)
        control_source = self._resolve_control_source(normalized, runtime_metadata)
        metadata_patch: Dict[str, Any] = {
            "agent_action": action,
        }

        if action in {"create", "create_agent", "spawn", "spawn_agent"}:
            agent_id = str(self._pick_value(control_source, runtime_metadata, "agent_id"))
            name = self._pick_optional_value(control_source, runtime_metadata, "name", agent_id)
            skill_name = self._pick_optional_value(control_source, runtime_metadata, "skill_name")
            character_prompt = self._pick_optional_value(control_source, runtime_metadata, "character_prompt")
            prompt_text = self._compose_prompt(
                context,
                skill_name=skill_name,
                character_prompt=character_prompt,
                extra_prompt=self._pick_optional_value(control_source, runtime_metadata, "additional_prompt"),
            )
            replace_existing = bool(
                self._pick_optional_value(control_source, runtime_metadata, "replace_existing", False)
            )
            if replace_existing and agent_id in context.core.agents:
                context.core.destroy_agent(agent_id)

            agent = context.core.create_agent(
                agent_id=agent_id,
                character_prompt=prompt_text,
                name=str(name) if name is not None else None,
            )

            node_id = self._pick_optional_value(control_source, runtime_metadata, "node_id")
            next_node_ids = self._coerce_node_id_list(
                self._pick_optional_value(control_source, runtime_metadata, "next_node_ids") or []
            )
            metadata_patch.update(
                {
                    "spawned_agent_id": agent.agent_id,
                    "spawned_agent_name": agent.name,
                    "spawned_agent_prompt": prompt_text,
                    "spawned_agent_skill": skill_name,
                    "spawned_agent_node_id": node_id,
                    "spawned_agent_next_node_ids": list(next_node_ids),
                    "next_node_id": node_id,
                }
            )
            return {
                "success": True,
                "action": "create_agent",
                "agent_id": agent.agent_id,
                "agent_name": agent.name,
                "content": content_passthrough,
                "metadata_patch": metadata_patch,
                "next_node_id": node_id,
            }

        if action in {"destroy", "destroy_agent", "remove", "remove_agent", "delete", "delete_agent"}:
            agent_id = self._pick_optional_value(control_source, runtime_metadata, "agent_id")
            if agent_id is None:
                agent_id = runtime_metadata.get("spawned_agent_id")
            if agent_id is None:
                raise ValueError("agent_manager destroy requires 'agent_id'.")
            agent_id = str(agent_id)
            agent = context.core.agents.get(agent_id)
            context.core.destroy_agent(agent_id)
            metadata_patch.update(
                {
                    "deleted_agent_id": agent_id,
                    "deleted_agent_name": getattr(agent, "name", agent_id) if agent is not None else agent_id,
                }
            )
            return {
                "success": True,
                "action": "destroy_agent",
                "agent_id": agent_id,
                "content": content_passthrough,
                "metadata_patch": metadata_patch,
                "next_node_id": self._pick_optional_value(control_source, runtime_metadata, "next_node_id"),
            }

        raise ValueError(f"Unknown agent_manager action: {action}")

    def _normalize_arguments(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if "action" in arguments or "operation" in arguments or "mode" in arguments:
            return dict(arguments)

        raw_input = arguments.get("input")
        if isinstance(raw_input, dict):
            return dict(raw_input)
        if isinstance(raw_input, str) and raw_input.strip():
            try:
                parsed = json.loads(raw_input)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "agent_manager expected JSON input when no direct action was provided."
                ) from exc
            if not isinstance(parsed, dict):
                raise ValueError("agent_manager JSON input must decode to an object.")
            return parsed
        raise ValueError("agent_manager requires either direct arguments or JSON input.")

    def _resolve_control_source(
        self,
        normalized: Dict[str, Any],
        runtime_metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        for key in ("agent", "spawn", "destroy", "cleanup", "control"):
            candidate = normalized.get(key)
            if isinstance(candidate, dict):
                return candidate
        for key in ("agent", "spawn", "destroy", "cleanup", "control"):
            candidate = runtime_metadata.get(key)
            if isinstance(candidate, dict):
                return candidate
        return normalized or runtime_metadata

    def _derive_action_from_payload(
        self,
        normalized: Dict[str, Any],
        runtime_metadata: Dict[str, Any],
    ) -> Optional[str]:
        for key in ("agent", "spawn", "destroy", "cleanup"):
            if isinstance(normalized.get(key), dict):
                return "create_agent" if key in {"agent", "spawn"} else "destroy_agent"
        if runtime_metadata.get("spawned_agent_id") and not runtime_metadata.get("deleted_agent_id"):
            return "destroy_agent"
        return None

    def _extract_content_passthrough(self, normalized: Dict[str, Any]) -> Optional[str]:
        content = normalized.get("content")
        if content is not None:
            return str(content)
        raw_input = normalized.get("input")
        if raw_input is None:
            return None
        return str(raw_input)

    def _pick_value(
        self,
        control_source: Dict[str, Any],
        runtime_metadata: Dict[str, Any],
        key: str,
    ) -> Any:
        value = self._pick_optional_value(control_source, runtime_metadata, key)
        if value is None:
            raise ValueError(f"agent_manager requires '{key}'.")
        return value

    def _pick_optional_value(
        self,
        control_source: Dict[str, Any],
        runtime_metadata: Dict[str, Any],
        key: str,
        default: Any = None,
    ) -> Any:
        for candidate_key in self._alias_keys(key):
            if candidate_key in control_source and control_source[candidate_key] is not None:
                return control_source[candidate_key]
            if candidate_key in runtime_metadata and runtime_metadata[candidate_key] is not None:
                return runtime_metadata[candidate_key]
        return default

    def _coerce_node_id_list(self, raw: Any) -> list[int]:
        if raw is None:
            return []
        if isinstance(raw, list):
            return [int(item) for item in raw]
        return [int(raw)]

    def _compose_prompt(
        self,
        context: ToolContext,
        *,
        skill_name: Any = None,
        character_prompt: Any = None,
        extra_prompt: Any = None,
    ) -> str:
        prompt_parts: list[str] = []

        if skill_name:
            skill = context.core.get_skill(str(skill_name))
            prompt_parts.append(skill.content)
        if character_prompt:
            prompt_parts.append(str(character_prompt).strip())
        if extra_prompt:
            prompt_parts.append(str(extra_prompt).strip())

        if not prompt_parts:
            raise ValueError("agent_manager create requires a prompt or skill_name.")
        return "\n\n".join(part for part in prompt_parts if part).strip()

    def _alias_keys(self, key: str) -> list[str]:
        alias_map = {
            "agent_id": ["agent_id", "spawned_agent_id", "deleted_agent_id"],
            "name": ["name", "spawned_agent_name", "deleted_agent_name"],
            "skill_name": ["skill_name", "spawned_agent_skill"],
            "character_prompt": ["character_prompt", "spawned_agent_prompt"],
            "additional_prompt": ["additional_prompt"],
            "node_id": ["node_id", "spawned_agent_node_id", "cleanup_node_id"],
            "next_node_ids": ["next_node_ids", "spawned_agent_next_node_ids"],
            "replace_existing": ["replace_existing"],
        }
        return alias_map.get(key, [key])


TOOL = AgentManagerTool()
