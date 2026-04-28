"""运行时 Agent 生命周期管理工具。

本模块提供 ``AgentManagerTool``，用于在任务执行期间动态创建或销毁 Agent。
支持通过多种参数别名解析用户输入，并在创建/销毁后自动校验执行图一致性。

主要导出内容：
    - :class:`AgentManagerTool`: Agent 生命周期管理工具定义。
    - ``TOOL``: 模块级单例实例。
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from core.toodefl import ToolContext, ToolDefinition, require_tool_capability


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
        """执行 Agent 创建或销毁操作。

        先对入参做规范化与来源解析，再根据解析出的 action 分发到
        create_agent 或 destroy_agent 分支，最后返回带有 metadata_patch
        的标准结果字典。

        Args:
            arguments: 工具调用入参字典。
            context: 当前工具执行上下文，包含运行时核心与元数据。

        Returns:
            Dict[str, Any]: 包含 success、action、agent_id 及 metadata_patch 的结果。

        Raises:
            ValueError: 缺少必要参数或 action 未知时抛出。
            PermissionError: 尝试将 workspace_mode 提升到 full_access 时抛出。
        """
        require_tool_capability(context, "agent_lifecycle", self.tool_name)
        if context is None or context.core is None:
            raise ValueError("agent_manager requires a runtime core context.")

        normalized = self._normalize_arguments(arguments)
        runtime_metadata = dict((context.metadata or {}))
        # 兼容多种可能表示动作意图的键名，降低调用方误用成本
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
            workspace_mode = str(
                self._pick_optional_value(control_source, runtime_metadata, "workspace_mode", "workspace")
            ).strip() or "workspace"
            # 禁止通过子 Agent 提升权限，避免沙箱逃逸
            if context.workspace_mode != "full_access" and workspace_mode == "full_access":
                raise PermissionError("agent_manager cannot escalate spawned agents to full_access.")
            workspace_root_value = self._pick_optional_value(control_source, runtime_metadata, "workspace_root")
            workspace_root = str(workspace_root_value).strip() if workspace_root_value is not None else None
            if workspace_root == "":
                workspace_root = None
            prompt_text = self._compose_prompt(
                context,
                skill_name=skill_name,
                context_content=content_passthrough,
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
                workspace_mode=workspace_mode,
                workspace_root=workspace_root,
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
                }
            )
            self._validate_runtime_graph(context)
            return {
                "success": True,
                "action": "create_agent",
                "agent_id": agent.agent_id,
                "agent_name": agent.name,
                "content": content_passthrough,
                "metadata_patch": metadata_patch,
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
            self._validate_runtime_graph(context)
            return {
                "success": True,
                "action": "destroy_agent",
                "agent_id": agent_id,
                "content": content_passthrough,
                "metadata_patch": metadata_patch,
                "metadata_clear": self._cleanup_metadata_keys(),
            }

        raise ValueError(f"Unknown agent_manager action: {action}")

    def _normalize_arguments(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """将工具入参规范化成可直接使用的字典。

        优先保留已含 action/operation/mode 的字典；若不存在，
        则尝试从 ``input`` 字段解析 JSON 对象。

        Args:
            arguments: 原始工具入参。

        Returns:
            规范化后的参数字典。

        Raises:
            ValueError: 无法解析出有效字典时抛出。
        """
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
        """确定实际承载控制指令的字典来源。

        先在 normalized 中查找以 agent/spawn/destroy/cleanup/control 为键的子字典；
        找不到时再到 runtime_metadata 中查找，最后回退到顶层字典本身。

        Args:
            normalized: 规范化后的工具入参。
            runtime_metadata: 运行时元数据字典。

        Returns:
            包含控制指令的字典。
        """
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
        """当显式 action 缺失时，根据载荷结构推导默认动作。

        若载荷中包含 agent/spawn 子字典则推断为创建；
        包含 destroy/cleanup 子字典则推断为销毁；
        若运行时元数据中已记录 spawned_agent_id 且未删除，也推断为销毁。

        Args:
            normalized: 规范化后的工具入参。
            runtime_metadata: 运行时元数据。

        Returns:
            推导出的动作字符串，或 None。
        """
        for key in ("agent", "spawn", "destroy", "cleanup"):
            if isinstance(normalized.get(key), dict):
                return "create_agent" if key in {"agent", "spawn"} else "destroy_agent"
        if runtime_metadata.get("spawned_agent_id") and not runtime_metadata.get("deleted_agent_id"):
            return "destroy_agent"
        return None

    def _extract_content_passthrough(self, normalized: Dict[str, Any]) -> Optional[str]:
        """提取需要透传给下游的内容。

        优先取 ``content`` 字段，其次取 ``input`` 字段的字符串形式。

        Args:
            normalized: 规范化后的工具入参。

        Returns:
            透传内容字符串，或 None。
        """
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
        """从 control_source 或 runtime_metadata 中获取必填值。

        Args:
            control_source: 控制指令字典。
            runtime_metadata: 运行时元数据。
            key: 要查找的键。

        Returns:
            找到的非 None 值。

        Raises:
            ValueError: 当键对应值为 None 时抛出。
        """
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
        """按别名链查找可选值。

        先遍历 key 的所有别名，在 control_source 中命中则返回；
        未命中则再到 runtime_metadata 中查找；最终返回 default。

        Args:
            control_source: 控制指令字典。
            runtime_metadata: 运行时元数据。
            key: 主键名。
            default: 默认值。

        Returns:
            查找结果或 default。
        """
        for candidate_key in self._alias_keys(key):
            if candidate_key in control_source and control_source[candidate_key] is not None:
                return control_source[candidate_key]
            if candidate_key in runtime_metadata and runtime_metadata[candidate_key] is not None:
                return runtime_metadata[candidate_key]
        return default

    def _coerce_node_id_list(self, raw: Any) -> list[int]:
        """将原始输入强制转换为整数节点 ID 列表。

        Args:
            raw: 原始输入（None、list 或单个值）。

        Returns:
            整数节点 ID 列表。
        """
        if raw is None:
            return []
        if isinstance(raw, list):
            return [int(item) for item in raw]
        return [int(raw)]

    def _validate_runtime_graph(self, context: ToolContext) -> None:
        """校验当前运行时执行图的一致性。

        Args:
            context: 工具上下文。

        Raises:
            ValueError: 图校验失败时抛出，错误信息以分号拼接。
        """
        graph = context.core.get_execution_graph()
        if graph is None:
            return
        validation = graph.validate(context.core)
        if not validation.is_valid:
            raise ValueError("; ".join(validation.errors))

    def _cleanup_metadata_keys(self) -> list[str]:
        """返回需要在 Agent 销毁后清理的元数据键列表。

        Returns:
            需要清除的键名列表。
        """
        return [
            "agent_action",
            "spawned_agent_id",
            "spawned_agent_name",
            "spawned_agent_prompt",
            "spawned_agent_skill",
            "spawned_agent_node_id",
            "spawned_agent_next_node_ids",
            "deleted_agent_id",
            "deleted_agent_name",
            "next_node_id",
        ]

    def _compose_prompt(
        self,
        context: ToolContext,
        *,
        skill_name: Any = None,
        context_content: Any = None,
        character_prompt: Any = None,
        extra_prompt: Any = None,
    ) -> str:
        """按优先级拼接生成 Agent 角色提示词。

        顺序为：skill 内容 > 当前任务上下文 > character_prompt > extra_prompt。

        Args:
            context: 工具上下文，用于加载 skill。
            skill_name: 可选的 skill 名称。
            context_content: 可选的任务上下文文本。
            character_prompt: 可选的角色设定文本。
            extra_prompt: 可选的附加提示文本。

        Returns:
            拼接后的完整提示词字符串。

        Raises:
            ValueError: 所有部分均为空时抛出。
        """
        prompt_parts: list[str] = []

        if skill_name:
            skill = context.core.get_skill(str(skill_name))
            prompt_parts.append(skill.content)
        if context_content:
            prompt_parts.append(f"Current mission context:\n{str(context_content).strip()}")
        if character_prompt:
            prompt_parts.append(str(character_prompt).strip())
        if extra_prompt:
            prompt_parts.append(str(extra_prompt).strip())

        if not prompt_parts:
            raise ValueError("agent_manager create requires a prompt or skill_name.")
        return "\n\n".join(part for part in prompt_parts if part).strip()

    def _alias_keys(self, key: str) -> list[str]:
        """返回某个键的所有已知别名，用于兼容不同调用约定。

        Args:
            key: 主键名。

        Returns:
            包含主键及别名的列表。
        """
        alias_map = {
            "agent_id": ["agent_id", "spawned_agent_id", "deleted_agent_id"],
            "name": ["name", "spawned_agent_name", "deleted_agent_name"],
            "skill_name": ["skill_name", "spawned_agent_skill"],
            "character_prompt": ["character_prompt", "spawned_agent_prompt"],
            "additional_prompt": ["additional_prompt"],
            "workspace_mode": ["workspace_mode"],
            "workspace_root": ["workspace_root"],
            "node_id": ["node_id", "spawned_agent_node_id", "cleanup_node_id"],
            "next_node_ids": ["next_node_ids", "spawned_agent_next_node_ids"],
            "replace_existing": ["replace_existing"],
        }
        return alias_map.get(key, [key])


TOOL = AgentManagerTool()
