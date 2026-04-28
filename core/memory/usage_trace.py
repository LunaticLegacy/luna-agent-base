"""Memory usage tracing and verification for a single agent round.

Tracks which injected memories the agent *declared* it used and then
heuristically verifies those declarations against the actual assistant
output.  Undeclared but implicitly used memories are also detected via
content matching so that the trace remains accurate even when the agent
forgets to cite a source.

Exports:
    - :class:`UsageTraceTracker`
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

from .types import KeyMemory, MemoryUsageTrace


class UsageTraceTracker:
    """Tracks and verifies memory usage within a single round.

    Attributes:
        injected_memory_ids: Ordered list of memory IDs that were injected.
        memory_lookup: Map from memory ID to the :class:`KeyMemory` object.
        current_turn_id: Turn identifier used to reject candidate-memory self-refs.
        declared_used_memory_ids: IDs the agent explicitly claimed to use.
        verified_used_memory_ids: IDs that passed heuristic verification.
        invalid_memory_refs: IDs that were declared but could not be verified.
        unused_injected_memory_ids: IDs that were injected but never used.
        verification_notes: Per-memory diagnostic dict.
    """

    def __init__(
        self,
        injected_memory_ids: List[str],
        memory_lookup: Dict[str, KeyMemory],
        current_turn_id: str,
    ) -> None:
        """Initialise the tracker for one round.

        Args:
            injected_memory_ids: Ordered list of memory IDs present in the prompt.
            memory_lookup: Map from memory ID to :class:`KeyMemory`.
            current_turn_id: Identifier of the turn being executed.
        """
        self.injected_memory_ids = list(injected_memory_ids)
        self.memory_lookup = dict(memory_lookup)
        self.current_turn_id = current_turn_id
        self.declared_used_memory_ids: List[str] = []
        self.verified_used_memory_ids: List[str] = []
        self.invalid_memory_refs: List[str] = []
        self.unused_injected_memory_ids: List[str] = []
        self.verification_notes: Dict[str, Any] = {}

    def record_declaration(self, memory_id: str, usage_statement: str = "") -> None:
        """Record that the agent declared using a memory.

        Args:
            memory_id: The memory ID cited by the agent.
            usage_statement: Optional free-text explanation provided by the agent.
        """
        if memory_id not in self.declared_used_memory_ids:
            self.declared_used_memory_ids.append(memory_id)
        self.verification_notes[memory_id] = {
            "usage_statement": usage_statement,
        }

    def verify_all(self, answer_text: str) -> MemoryUsageTrace:
        """Run MVP verification against the final answer text.

        The verification pipeline is:

        1. For every *declared* memory, run :meth:`_verify_single`.
        2. For injected memories that were neither declared nor verified,
           run a content heuristic (:meth:`_content_match`) to detect
           implicit usage.
        3. Anything still unmatched is recorded as unused.

        Args:
            answer_text: The raw assistant output for this round.

        Returns:
            A populated :class:`MemoryUsageTrace` summarising the audit.
        """
        answer_lower = answer_text.lower()

        # Phase 1 — verify explicit declarations
        for memory_id in self.declared_used_memory_ids:
            ok, reason = self._verify_single(memory_id, answer_lower)
            note = self.verification_notes.get(memory_id, {})
            note["verified"] = ok
            note["reason"] = reason
            self.verification_notes[memory_id] = note
            if ok:
                if memory_id not in self.verified_used_memory_ids:
                    self.verified_used_memory_ids.append(memory_id)
            else:
                if memory_id not in self.invalid_memory_refs:
                    self.invalid_memory_refs.append(memory_id)

        # Phase 2 — detect injected but neither declared nor verified
        declared_and_verified = set(self.verified_used_memory_ids) | set(self.invalid_memory_refs)
        for mid in self.injected_memory_ids:
            if mid not in declared_and_verified:
                # Also run content heuristic to see if it was implicitly used
                mem = self.memory_lookup.get(mid)
                if mem and self._content_match(mem, answer_lower):
                    if mid not in self.verified_used_memory_ids:
                        self.verified_used_memory_ids.append(mid)
                else:
                    if mid not in self.unused_injected_memory_ids:
                        self.unused_injected_memory_ids.append(mid)

        return MemoryUsageTrace(
            injected_memory_ids=list(self.injected_memory_ids),
            declared_used_memory_ids=list(self.declared_used_memory_ids),
            verified_used_memory_ids=list(self.verified_used_memory_ids),
            invalid_memory_refs=list(self.invalid_memory_refs),
            unused_injected_memory_ids=list(self.unused_injected_memory_ids),
            verification_notes=dict(self.verification_notes),
        )

    def _verify_single(self, memory_id: str, answer_lower: str) -> tuple[bool, str]:
        """Verify one memory against four hard rules.

        Args:
            memory_id: The memory ID to verify.
            answer_lower: Lower-cased assistant output for substring matching.

        Returns:
            ``(True, reason)`` if the memory passes all checks,
            ``(False, reason)`` otherwise.
        """
        # 1. memory_id must exist in the lookup
        mem = self.memory_lookup.get(memory_id)
        if mem is None:
            return False, "memory_id does not exist"

        # 2. memory_id must have been injected this round
        if memory_id not in self.injected_memory_ids:
            return False, "memory was not injected this round"

        # 3. Candidate memories created in the current turn cannot be cited yet
        if mem.created_turn_id == self.current_turn_id and mem.status == "candidate":
            return False, "current-turn candidate memory cannot be used"

        # 4. answer must contain keywords, tags, or canonical phrase
        if self._content_match(mem, answer_lower):
            return True, "content match"

        return False, "no content match in answer"

    def _content_match(self, mem: KeyMemory, answer_lower: str) -> bool:
        """Heuristic content match between a memory and the assistant answer.

        Checks, in order of priority:

        1. Substantive words (>= 4 chars) from the memory content.
        2. Any of the memory's tags.
        3. The memory's canonical key (if set).
        4. Chinese-character phrases (2+ chars) for CJK content.

        Args:
            mem: The memory to match.
            answer_lower: Lower-cased assistant output.

        Returns:
            ``True`` if any heuristic signals a match.
        """
        # Try content keywords (skip very short words to reduce false positives)
        content_words = [w for w in mem.content.lower().split() if len(w) >= 4]
        for w in content_words[:6]:
            if w in answer_lower:
                return True
        # Try tags
        for tag in mem.tags:
            if tag.lower() in answer_lower:
                return True
        # Try canonical key
        if mem.canonical_key and mem.canonical_key.lower() in answer_lower:
            return True
        # Try a simple phrase extraction for longer memories (CJK support)
        phrases = re.findall(r"[\u4e00-\u9fff]{2,}", mem.content)
        for ph in phrases[:4]:
            if ph.lower() in answer_lower:
                return True
        return False

    @staticmethod
    def parse_declarations(text: str) -> Dict[str, str]:
        """Parse memory usage declarations from agent text.

        Expected format (loose)::

            M0 -> 用于解释词源
            M3 -> 用于说明互联网和轻小说改变文化生态

        Args:
            text: The raw assistant output.

        Returns:
            Mapping ``{memory_id: usage_statement}`` for every declaration found.
        """
        declarations: Dict[str, str] = {}
        # Match lines like "M0 -> ..." or "[M0] -> ..."
        pattern = re.compile(r"\[?M(\w+)\]?\s*[:\-–>]\s*(.+)")
        for line in text.splitlines():
            line = line.strip()
            m = pattern.match(line)
            if m:
                mem_id = m.group(1).strip()
                statement = m.group(2).strip()
                declarations[mem_id] = statement
        return declarations
