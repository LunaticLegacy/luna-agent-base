"""Memory lifecycle rules and validation helpers for the Angelus memory subsystem.

This module enforces the state machine around :class:`KeyMemory` objects:
only *committed* memories may be injected into prompts, and memories created
in the current turn are ineligible for injection to avoid self-referential
loops.  It also provides defaults for ``pinned`` and ``packable`` flags based
on the semantic kind of a memory (e.g. formulas are pinned and never packed).

Exports:
    - :func:`can_inject_memory`
    - :class:`MemoryLifecycle`
"""

from __future__ import annotations

from typing import Optional

from .types import KeyMemory


def can_inject_memory(memory: KeyMemory, current_turn_id: str) -> bool:
    """Return True if *memory* may be injected into the prompt for *current_turn_id*.

    Rules:
        1. Only committed memories may be injected.
        2. Memories created in the current turn are not eligible.

    Args:
        memory: The candidate memory to evaluate.
        current_turn_id: The identifier of the turn that is currently executing.

    Returns:
        Whether the memory satisfies both injection rules.
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
        """Validate whether a memory can be injected. Returns (ok, reason).

        Args:
            memory: The candidate memory to evaluate.
            current_turn_id: The identifier of the turn that is currently executing.

        Returns:
            A tuple where the first element indicates success and the second
            element is a human-readable reason string.
        """
        if memory.status != "committed":
            return False, f"status={memory.status} (must be committed)"
        if memory.created_turn_id == current_turn_id:
            return False, "created in current turn"
        return True, "ok"

    @staticmethod
    def default_pinned_and_packable(kind: str) -> tuple[bool, bool]:
        """Return (pinned, packable) defaults for a given memory kind.

        The policy distinguishes precise/structural information from soft facts:

        - ``formula`` / ``constraint`` / ``api_contract`` → pinned=True, packable=False
          (precise information must survive compression and be always-visible).
        - ``timeline_constraint`` → pinned=False, packable=True (shown as constraint).
        - others → pinned=False, packable=True (ordinary soft facts).

        Args:
            kind: The semantic kind of the memory (e.g. ``"formula"``, ``"fact"``).

        Returns:
            A tuple ``(pinned, packable)`` reflecting the default policy for *kind*.
        """
        if kind in ("formula", "constraint", "api_contract"):
            return True, False
        return False, True
