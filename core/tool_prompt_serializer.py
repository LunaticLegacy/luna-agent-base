from __future__ import annotations

import json
from typing import Any, Dict, Iterable, Literal


ToolContractPromptMode = Literal["off", "compact", "auto"]


def serialize_tool_contracts(
    tools: Iterable[Any],
    *,
    mode: ToolContractPromptMode = "auto",
) -> str:
    """Serialize bound tool schemas into a prompt-safe JSON contract block."""
    normalized_mode = str(mode or "auto").strip().lower()
    if normalized_mode == "off":
        return ""

    contracts: list[Dict[str, Any]] = []
    for tool in tools or []:
        schema_getter = getattr(tool, "get_openai_schema", None)
        schema = schema_getter() if callable(schema_getter) else None
        if isinstance(schema, dict):
            function_schema = schema.get("function") if schema.get("type") == "function" else schema
            if isinstance(function_schema, dict):
                contract = {
                    "tool_name": function_schema.get("name") or getattr(tool, "tool_name", ""),
                    "description": function_schema.get("description") or getattr(tool, "description", ""),
                    "parameters": function_schema.get("parameters") or {},
                }
            else:
                contract = _fallback_contract(tool)
        else:
            contract = _fallback_contract(tool)
        if str(contract.get("tool_name") or "").strip():
            contracts.append(contract)

    if not contracts:
        return ""

    payload: Dict[str, Any] = {
        "available_tools": contracts,
        "tool_call_rules": [
            "Use the bound function-calling interface only.",
            "Do not write JSON tool envelopes in assistant text.",
            "Each tool call must satisfy the parameters schema for that tool.",
            "If a tool call is rejected, rewrite it using the error detail and schema.",
        ],
    }
    if normalized_mode == "compact":
        for contract in payload["available_tools"]:
            parameters = contract.get("parameters")
            if isinstance(parameters, dict) and isinstance(parameters.get("properties"), dict):
                contract["required"] = list(parameters.get("required", []) or [])
                contract["properties"] = sorted(parameters["properties"].keys())
                contract.pop("parameters", None)
    return (
        "## Runtime Tool Contracts\n\n"
        "The following JSON is generated from the currently bound ToolDefinition schemas. "
        "Treat it as the source of truth for tool names and arguments.\n\n"
        "```json\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)}\n"
        "```"
    )


def _fallback_contract(tool: Any) -> Dict[str, Any]:
    return {
        "tool_name": getattr(tool, "tool_name", ""),
        "description": getattr(tool, "description", ""),
        "parameters": getattr(tool, "schema", {}) or {},
    }
