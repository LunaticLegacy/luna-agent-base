"""Failure classification utilities.

Maps arbitrary exceptions to canonical ``FailureClassification`` records
so that the fault-tolerance layer can decide whether to retry, reroute,
or quarantine without parsing free-form error messages.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

FAILURE_KINDS = {
    "unknown_tool",
    "required_tool_failed",
    "optional_tool_failed",
    "output_parse_error",
    "schema_validation_error",
    "model_error",
    "runtime_exception",
    "permission_denied",
    "graph_validation_error",
    "mutation_error",
    "routing_error",
    "invariant_violation",
    "max_retry_exceeded",
    "verifier_failed",
    "timeout",
    "user_cancelled",
    "tool_contract_validation_failed",
    "tool_policy_denied",
    "tool_argument_error",
    "unknown",
}


@dataclass
class FailureClassification:
    """Canonical classification for a runtime failure.

    Attributes:
        failure_kind: Key into FAILURE_KINDS.
        recoverable: Whether the failure can be recovered without user action.
        retryable: Whether a blind retry is likely to succeed.
        suggested_action: Human-readable remediation hint, if any.
        detail: Arbitrary extra context (e.g. tool batch summary).
    """

    failure_kind: str
    recoverable: bool = False
    retryable: bool = False
    suggested_action: Optional[str] = None
    detail: Dict[str, Any] | None = None


def classify_failure(exc: Exception) -> FailureClassification:
    """Classify an exception into a FailureClassification record.

    Checks for an explicit ``failure_kind`` attribute first, then falls
    back to heuristic string matching on the exception name and message.
    """
    explicit = getattr(exc, "failure_kind", None)
    if explicit:
        return _with_defaults(str(explicit), exc)

    text = f"{exc.__class__.__name__}: {exc}".lower()
    if explicit == "tool_policy_denied" or "refuses to run dangerous command" in text or "policy denied command" in text:
        return _with_defaults("tool_policy_denied", exc)
    if isinstance(exc, PermissionError) or "permission denied" in text or "requires capability" in text:
        return _with_defaults("permission_denied", exc)
    if isinstance(exc, TimeoutError) or "timeout" in text or "timed out" in text:
        return _with_defaults("timeout", exc)
    if isinstance(exc, KeyError) and "unknown tool" in text:
        return _with_defaults("unknown_tool", exc)
    if "unknown tool" in text or "unknown tool_name" in text:
        return _with_defaults("unknown_tool", exc)
    if "requires a non-empty" in text or "unsupported operation" in text or "required" in text and "argument" in text:
        return _with_defaults("tool_argument_error", exc)
    if "required tool" in text:
        return _with_defaults("required_tool_failed", exc)
    if "optional tool" in text:
        return _with_defaults("optional_tool_failed", exc)
    if "json" in text and ("parse" in text or "decode" in text):
        return _with_defaults("output_parse_error", exc)
    if "schema" in text and ("invalid" in text or "validation" in text):
        return _with_defaults("schema_validation_error", exc)
    if "route" in text or "next_node" in text:
        return _with_defaults("routing_error", exc)
    if "mutation" in text or "graph transaction" in text or "patch" in text:
        return _with_defaults("mutation_error", exc)
    if "graph" in text and "valid" in text:
        return _with_defaults("graph_validation_error", exc)
    if "invariant" in text or "assert" in text:
        return _with_defaults("invariant_violation", exc)
    if "max retry" in text or "retries exhausted" in text:
        return _with_defaults("max_retry_exceeded", exc)
    if "verifier" in text:
        return _with_defaults("verifier_failed", exc)
    if "cancel" in text or "user stopped" in text:
        return _with_defaults("user_cancelled", exc)
    if "model" in text or "llm" in text or "api" in text:
        return _with_defaults("model_error", exc)
    if isinstance(exc, RuntimeError):
        return _with_defaults("runtime_exception", exc)
    return _with_defaults("unknown", exc)


def failure_detail(exc: Exception) -> Dict[str, Any]:
    """Harvest structured detail from an exception for downstream logging.

    Calls ``to_detail()`` if present, then collects known diagnostic
    attributes (``parser_stage``, ``tool_name``, etc.).
    """
    detail: Dict[str, Any] = {}
    to_detail = getattr(exc, "to_detail", None)
    if callable(to_detail):
        try:
            detail.update(to_detail())
        except Exception:
            pass
    for attr in ("parser_stage", "tool_name", "raw_output_preview", "raw_output_near_error"):
        value = getattr(exc, attr, None)
        if value is not None:
            detail[attr] = value
    batch_result = getattr(exc, "batch_result", None)
    if batch_result is not None:
        detail["tool_batch_summary"] = getattr(batch_result, "summary", {})
    return detail


def _with_defaults(kind: str, exc: Exception) -> FailureClassification:
    """Build a FailureClassification with sensible defaults for *kind*."""
    normalized = kind if kind in FAILURE_KINDS else "unknown"
    retryable = normalized in {"timeout", "model_error", "runtime_exception", "optional_tool_failed", "tool_policy_denied", "tool_argument_error"}
    recoverable = normalized in {
        "output_parse_error",
        "optional_tool_failed",
        "timeout",
        "model_error",
        "required_tool_failed",
        "routing_error",
        "tool_policy_denied",
        "tool_argument_error",
    }
    suggested = {
        "unknown_tool": "Register the tool or remove it from the agent/graph declaration.",
        "tool_contract_validation_failed": "Fix graph and agent tool bindings before starting the run.",
        "required_tool_failed": "Route to a fallback node or repair the required tool call.",
        "output_parse_error": "Use raw_text/json_optional mode or route output through a repairer.",
        "permission_denied": "Grant the required capability only if the tool is trusted.",
        "tool_policy_denied": "Rewrite as safe single-command calls or continue without shell probing.",
        "tool_argument_error": "Rewrite the tool call with the required arguments and valid schema.",
        "routing_error": "Ensure the resolved next node is an allowed outgoing edge.",
        "mutation_error": "Validate the architecture patch and retry transactionally.",
    }.get(normalized)
    return FailureClassification(
        failure_kind=normalized,
        recoverable=recoverable,
        retryable=retryable,
        suggested_action=suggested,
        detail=failure_detail(exc),
    )
