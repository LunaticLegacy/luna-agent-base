from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

from .types import KeyMemory, MemoryUsageTrace


class UsageTraceTracker:
    """Tracks and verifies memory usage within a single round."""

    def __init__(
        self,
        injected_memory_ids: List[str],
        memory_lookup: Dict[str, KeyMemory],
        current_turn_id: str,
    ) -> None:
        self.injected_memory_ids = list(injected_memory_ids)
        self.memory_lookup = dict(memory_lookup)
        self.current_turn_id = current_turn_id
        self.declared_used_memory_ids: List[str] = []
        self.verified_used_memory_ids: List[str] = []
        self.invalid_memory_refs: List[str] = []
        self.unused_injected_memory_ids: List[str] = []
        self.verification_notes: Dict[str, Any] = {}

    def record_declaration(self, memory_id: str, usage_statement: str = "") -> None:
        """Record that the agent declared using a memory."""
        if memory_id not in self.declared_used_memory_ids:
            self.declared_used_memory_ids.append(memory_id)
        self.verification_notes[memory_id] = {
            "usage_statement": usage_statement,
        }

    def verify_all(self, answer_text: str) -> MemoryUsageTrace:
        """Run MVP verification against the final answer text."""
        answer_lower = answer_text.lower()

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

        # Detect injected but neither declared nor verified
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
        # 1. memory_id must exist
        mem = self.memory_lookup.get(memory_id)
        if mem is None:
            return False, "memory_id does not exist"

        # 2. memory_id must be in injected_memory_ids
        if memory_id not in self.injected_memory_ids:
            return False, "memory was not injected this round"

        # 3. memory cannot be current-turn candidate
        if mem.created_turn_id == self.current_turn_id and mem.status == "candidate":
            return False, "current-turn candidate memory cannot be used"

        # 4. answer must contain keywords, tags, or canonical phrase
        if self._content_match(mem, answer_lower):
            return True, "content match"

        return False, "no content match in answer"

    def _content_match(self, mem: KeyMemory, answer_lower: str) -> bool:
        # Try content keywords (skip very short words)
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
        # Try a simple phrase extraction for longer memories
        phrases = re.findall(r"[\u4e00-\u9fff]{2,}", mem.content)
        for ph in phrases[:4]:
            if ph.lower() in answer_lower:
                return True
        return False

    @staticmethod
    def parse_declarations(text: str) -> Dict[str, str]:
        """Parse memory usage declarations from agent text.

        Expected format (loose):
        M0 -> 用于解释词源
        M3 -> 用于说明互联网和轻小说改变文化生态

        Returns {memory_id: usage_statement}.
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
