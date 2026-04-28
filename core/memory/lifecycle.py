from __future__ import annotations

from typing import Optional

from .types import KeyMemory


def can_inject_memory(memory: KeyMemory, current_turn_id: str) -> bool:
    """Return True if *memory* may be injected into the prompt for *current_turn_id*.

    Rules:
    1. Only committed memories may be injected.
    2. Memories created in the current turn are not eligible.
    """
    return (
        memory.status == "committed"
        and memory.created_turn_id is not None
        and memory.created_turn_id != current_turn_id
    )


class MemoryLifecycle:
    """Enforces memory lifecycle rules and provides validation helpers."""

    @staticmethod
    def validate_injection(memory: KeyMemory, current_turn_id: str) -> tuple[bool, str]:
        """Validate whether a memory can be injected. Returns (ok, reason)."""
        if memory.status != "committed":
            return False, f"status={memory.status} (must be committed)"
        if memory.created_turn_id == current_turn_id:
            return False, "created in current turn"
        return True, "ok"

    @staticmethod
    def default_pinned_and_packable(kind: str) -> tuple[bool, bool]:
        """Return (pinned, packable) defaults for a given memory kind.

        formula / constraint / api_contract  -> pinned=True, packable=False
        timeline_constraint                    -> pinned=False, packable=True (but shown as constraint)
        others                                 -> pinned=False, packable=True
        """
        if kind in ("formula", "constraint", "api_contract"):
            return True, False
        return False, True
